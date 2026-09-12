"""SQLAlchemy repository for Phase 10B Browser Execution Tasks."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.browser_task import BrowserTaskModel


class BrowserTaskRepository:
    """Repository managing browser worker tasks in PostgreSQL."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, task: BrowserTaskModel) -> BrowserTaskModel:
        """Persist a new browser task."""
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_by_id(self, id: int) -> Optional[BrowserTaskModel]:
        """Fetch task by internal integer ID."""
        stmt = select(BrowserTaskModel).where(BrowserTaskModel.id == id)
        return self.db.scalars(stmt).first()

    def get_by_task_id(self, task_id: str) -> Optional[BrowserTaskModel]:
        """Fetch task by canonical task_id."""
        stmt = select(BrowserTaskModel).where(BrowserTaskModel.task_id == task_id)
        return self.db.scalars(stmt).first()

    def get_by_application_id(self, application_id: str) -> Optional[BrowserTaskModel]:
        """Fetch latest task for an application."""
        stmt = (
            select(BrowserTaskModel)
            .where(BrowserTaskModel.application_id == application_id)
            .order_by(BrowserTaskModel.created_at.desc())
        )
        return self.db.scalars(stmt).first()

    def get_by_application_or_job_id(
        self, application_id: str, job_id: Optional[str] = None
    ) -> Optional[BrowserTaskModel]:
        """Fetch latest task matching either application_id or job_id."""
        clauses = [
            BrowserTaskModel.application_id == application_id,
            BrowserTaskModel.job_id == application_id,
        ]
        if job_id:
            clauses.append(BrowserTaskModel.job_id == job_id)
            clauses.append(BrowserTaskModel.application_id == job_id)

        stmt = (
            select(BrowserTaskModel)
            .where(or_(*clauses))
            .order_by(BrowserTaskModel.created_at.desc())
        )
        return self.db.scalars(stmt).first()

    def list_by_status(self, status: BrowserTaskStatus, limit: int = 50) -> List[BrowserTaskModel]:
        """List tasks matching a given state."""
        stmt = (
            select(BrowserTaskModel)
            .where(BrowserTaskModel.status == status)
            .order_by(BrowserTaskModel.created_at.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def update_status(
        self,
        task_id: str,
        status: BrowserTaskStatus,
        pause_reason: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> Optional[BrowserTaskModel]:
        """Update task status and reasons."""
        task = self.get_by_task_id(task_id)
        if not task:
            return None

        task.status = status
        if pause_reason is not None:
            task.pause_reason = pause_reason
        if failure_reason is not None:
            task.failure_reason = failure_reason

        now = datetime.now(timezone.utc)
        if status == BrowserTaskStatus.RUNNING and not task.started_at:
            task.started_at = now
        elif status in (BrowserTaskStatus.COMPLETED, BrowserTaskStatus.FAILED, BrowserTaskStatus.EXPIRED):
            task.completed_at = now

        self.db.commit()
        self.db.refresh(task)
        return task

    def append_audit_event(self, task_id: str, event: dict) -> Optional[BrowserTaskModel]:
        """Append an audit event to the task."""
        task = self.get_by_task_id(task_id)
        if not task:
            return None

        events = list(task.audit_events or [])
        events.append(event)
        task.audit_events = events
        self.db.commit()
        self.db.refresh(task)
        return task

    def set_review_package(
        self,
        task_id: str,
        review_package: dict,
        confirmation_token: Optional[str] = None,
        confirmation_expires_at: Optional[datetime] = None,
    ) -> Optional[BrowserTaskModel]:
        """Attach review package and confirmation token to task."""
        task = self.get_by_task_id(task_id)
        if not task:
            return None

        task.review_package_json = review_package
        if confirmation_token:
            task.confirmation_token = confirmation_token
        if confirmation_expires_at:
            task.confirmation_expires_at = confirmation_expires_at

        self.db.commit()
        self.db.refresh(task)
        return task

    def claim_task(
        self,
        task_id: str,
        expected_status: BrowserTaskStatus,
        new_status: BrowserTaskStatus,
        worker_id: str,
    ) -> bool:
        """
        Atomically claim a task by comparing expected status.
        Guarantees that multiple concurrent workers cannot claim the same task.
        """
        from sqlalchemy import update
        now = datetime.now(timezone.utc)
        stmt = (
            update(BrowserTaskModel)
            .where(
                BrowserTaskModel.task_id == task_id,
                BrowserTaskModel.status == expected_status,
            )
            .values(
                status=new_status,
                worker_id=worker_id,
                attempt_count=BrowserTaskModel.attempt_count + 1,
                updated_at=now,
            )
        )
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount > 0

    def recover_stale_running_tasks(self, timeout_minutes: int = 15) -> int:
        """
        Recover tasks that were running when a previous container/worker crashed or restarted.
        Resets SUBMISSION_RUNNING -> SUBMISSION_AUTHORIZED and RUNNING -> QUEUED if under max attempts.
        """
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        recovered_count = 0

        # 1. Recover stale SUBMISSION_RUNNING tasks
        stale_sub_stmt = (
            select(BrowserTaskModel)
            .where(
                BrowserTaskModel.status == BrowserTaskStatus.SUBMISSION_RUNNING,
                BrowserTaskModel.updated_at < cutoff,
            )
        )
        stale_sub_tasks = list(self.db.scalars(stale_sub_stmt).all())
        for task in stale_sub_tasks:
            events = task.audit_events or []
            has_dispatched_submit = any(e.get("event") == "submit_click_dispatched" for e in events)
            if has_dispatched_submit:
                # Submit was already dispatched to employer before crash/timeout.
                # Outcome is ambiguous; do NOT retry automatically.
                task.status = BrowserTaskStatus.SUBMISSION_UNVERIFIED
                task.pause_reason = "Stale submission recovered after submit click was dispatched. Outcome unverified; do not retry automatically."
                recovered_count += 1
            elif task.attempt_count < task.max_attempts:
                task.status = BrowserTaskStatus.SUBMISSION_AUTHORIZED
                task.pause_reason = "Recovered after worker restart"
                recovered_count += 1
            else:
                task.status = BrowserTaskStatus.FAILED
                task.failure_reason = "Max execution attempts exceeded after multiple crashes"
                recovered_count += 1

        # 2. Recover stale RUNNING tasks
        stale_run_stmt = (
            select(BrowserTaskModel)
            .where(
                BrowserTaskModel.status == BrowserTaskStatus.RUNNING,
                BrowserTaskModel.updated_at < cutoff,
            )
        )
        stale_run_tasks = list(self.db.scalars(stale_run_stmt).all())
        for task in stale_run_tasks:
            if task.attempt_count < task.max_attempts:
                task.status = BrowserTaskStatus.QUEUED
                task.pause_reason = "Recovered after worker restart"
                recovered_count += 1
            else:
                task.status = BrowserTaskStatus.FAILED
                task.failure_reason = "Max execution attempts exceeded after multiple crashes"
                recovered_count += 1

        if recovered_count > 0:
            self.db.commit()

        return recovered_count

