"""SQLAlchemy repository for Phase 10B Browser Execution Tasks."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
import uuid
from sqlalchemy import and_, or_, select, update
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

    def create_task(
        self,
        *,
        application_id: Optional[str] = None,
        job_id: Optional[str] = None,
        target_url: str,
        source: str = "manual",
        task_id: Optional[str] = None,
        status: BrowserTaskStatus = BrowserTaskStatus.QUEUED,
        execution_mode: str = "LOCAL_INTERACTIVE",
        worker_id: Optional[str] = None,
        assigned_device_id: Optional[str] = None,
        attempt_count: int = 0,
        max_attempts: int = 3,
        pause_reason: Optional[str] = None,
        failure_reason: Optional[str] = None,
        confirmation_token: Optional[str] = None,
        confirmation_expires_at: Optional[datetime] = None,
        review_package_json: Optional[dict] = None,
        audit_events: Optional[List[dict]] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        id_prefix: str = "task-bw",
    ) -> BrowserTaskModel:
        """
        Canonical factory for creating and persisting a BrowserTask record.
        Enforces deterministic ID generation, field validation, and state machine defaults.
        """
        if not task_id:
            task_id = f"{id_prefix}-{uuid.uuid4().hex[:8]}"

        task = BrowserTaskModel(
            task_id=task_id,
            application_id=application_id,
            job_id=job_id,
            source=source or "manual",
            target_url=target_url,
            status=status,
            pause_reason=pause_reason,
            failure_reason=failure_reason,
            worker_id=worker_id,
            execution_mode=execution_mode,
            assigned_device_id=assigned_device_id,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
            confirmation_token=confirmation_token,
            confirmation_expires_at=confirmation_expires_at,
            review_package_json=review_package_json if review_package_json is not None else {},
            audit_events=audit_events if audit_events is not None else [],
            started_at=started_at,
            completed_at=completed_at,
        )
        return self.create(task)

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

    def list_by_status(
        self,
        status: BrowserTaskStatus,
        execution_mode: Optional[str] = None,
        limit: int = 50,
    ) -> List[BrowserTaskModel]:
        """List tasks matching a given state and optional execution mode."""
        clauses = [BrowserTaskModel.status == status]
        if execution_mode is not None:
            clauses.append(BrowserTaskModel.execution_mode == execution_mode)

        stmt = (
            select(BrowserTaskModel)
            .where(and_(*clauses))
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
        expected_execution_mode: Optional[str] = None,
    ) -> bool:
        """
        Atomically claim a task by comparing expected status and execution mode.
        Guarantees that multiple concurrent workers / local agents cannot claim the same task.
        """
        from sqlalchemy import update
        now = datetime.now(timezone.utc)
        where_clauses = [
            BrowserTaskModel.task_id == task_id,
            BrowserTaskModel.status == expected_status,
        ]
        if expected_execution_mode is not None:
            where_clauses.append(BrowserTaskModel.execution_mode == expected_execution_mode)

        stmt = (
            update(BrowserTaskModel)
            .where(and_(*where_clauses))
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

    def recover_stale_task(
        self,
        task_id: str,
        expected_status: BrowserTaskStatus,
        new_status: BrowserTaskStatus,
        cutoff: datetime,
        reason: str,
        is_failure: bool = False,
    ) -> bool:
        """
        Atomically recover a single stale task if and only if its status matches expected_status
        and its updated_at timestamp is older than cutoff.
        Returns True if claimed and transitioned, False if already updated/claimed by another process.
        """
        now = datetime.now(timezone.utc)
        values_dict = {
            "status": new_status,
            "updated_at": now,
        }
        if is_failure:
            values_dict["failure_reason"] = reason
        else:
            values_dict["pause_reason"] = reason

        stmt = (
            update(BrowserTaskModel)
            .where(
                BrowserTaskModel.task_id == task_id,
                BrowserTaskModel.status == expected_status,
                BrowserTaskModel.updated_at < cutoff,
            )
            .values(**values_dict)
            .execution_options(synchronize_session=False)
        )
        result = self.db.execute(stmt)
        if result.rowcount > 0:
            self.db.commit()
            self.append_audit_event(
                task_id,
                {
                    "event": "stale_task_recovered",
                    "previous_status": expected_status.value,
                    "new_status": new_status.value,
                    "reason": reason,
                    "recovered_at": now.isoformat(),
                },
            )
            return True
        return False

    def recover_stale_running_tasks(self, timeout_minutes: int = 15) -> int:
        """
        Recover tasks that were left running when a worker process crashed or restarted.
        - Genuinely stale RUNNING tasks -> QUEUED (or FAILED if attempt limit reached).
        - Genuinely stale SUBMISSION_RUNNING tasks -> FAILED (or SUBMISSION_UNVERIFIED if submit click was dispatched).
          CRITICAL SAFETY INVARIANT: Stale SUBMISSION_RUNNING tasks are NEVER automatically converted
          to SUBMITTED or SUBMISSION_AUTHORIZED (which would auto-resubmit). They require manual re-authorization.
        - Atomic and concurrency-safe: concurrent recovery executions cannot claim the same task twice.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        recovered_count = 0

        # 1. Inspect stale SUBMISSION_RUNNING tasks
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
                # Dispatched before crash: outcome ambiguous; do NOT resubmit
                new_st = BrowserTaskStatus.SUBMISSION_UNVERIFIED
                reason = "Stale submission recovered after submit click was dispatched. Outcome unverified; do not retry automatically."
                is_fail = False
            else:
                # Crashed during submission execution: never auto-resubmit; transition to FAILED
                new_st = BrowserTaskStatus.FAILED
                reason = "Worker process crashed or timed out while SUBMISSION_RUNNING. Submissions are never automatically retried. Manual re-authorization required."
                is_fail = True

            if self.recover_stale_task(
                task_id=task.task_id,
                expected_status=BrowserTaskStatus.SUBMISSION_RUNNING,
                new_status=new_st,
                cutoff=cutoff,
                reason=reason,
                is_failure=is_fail,
            ):
                recovered_count += 1

        # 2. Inspect stale RUNNING preparation tasks
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
                new_st = BrowserTaskStatus.QUEUED
                reason = "Recovered after worker process crash/timeout"
                is_fail = False
            else:
                new_st = BrowserTaskStatus.FAILED
                reason = "Max execution attempts exceeded after multiple crashes"
                is_fail = True

            if self.recover_stale_task(
                task_id=task.task_id,
                expected_status=BrowserTaskStatus.RUNNING,
                new_status=new_st,
                cutoff=cutoff,
                reason=reason,
                is_failure=is_fail,
            ):
                recovered_count += 1

        return recovered_count


def create_browser_task(
    db: Session,
    *,
    application_id: Optional[str] = None,
    job_id: Optional[str] = None,
    target_url: str,
    source: str = "manual",
    task_id: Optional[str] = None,
    status: BrowserTaskStatus = BrowserTaskStatus.QUEUED,
    execution_mode: str = "LOCAL_INTERACTIVE",
    worker_id: Optional[str] = None,
    assigned_device_id: Optional[str] = None,
    attempt_count: int = 0,
    max_attempts: int = 3,
    pause_reason: Optional[str] = None,
    failure_reason: Optional[str] = None,
    confirmation_token: Optional[str] = None,
    confirmation_expires_at: Optional[datetime] = None,
    review_package_json: Optional[dict] = None,
    audit_events: Optional[List[dict]] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    id_prefix: str = "task-bw",
) -> BrowserTaskModel:
    """Canonical factory helper for creating and persisting a BrowserTask record."""
    repo = BrowserTaskRepository(db)
    return repo.create_task(
        application_id=application_id,
        job_id=job_id,
        target_url=target_url,
        source=source,
        task_id=task_id,
        status=status,
        execution_mode=execution_mode,
        worker_id=worker_id,
        assigned_device_id=assigned_device_id,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        pause_reason=pause_reason,
        failure_reason=failure_reason,
        confirmation_token=confirmation_token,
        confirmation_expires_at=confirmation_expires_at,
        review_package_json=review_package_json,
        audit_events=audit_events,
        started_at=started_at,
        completed_at=completed_at,
        id_prefix=id_prefix,
    )


