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
