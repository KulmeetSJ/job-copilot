"""SQLAlchemy ORM model for Browser Execution Tasks (Phase 10B)."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import DateTime, Enum, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.base import Base, TimestampMixin, utc_now


class BrowserTaskModel(Base, TimestampMixin):
    """Durable state representation of a background browser worker execution task."""

    __tablename__ = "browser_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    application_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(100), default="manual", index=True, nullable=False)
    target_url: Mapped[str] = mapped_column(String(1024), nullable=False)

    status: Mapped[BrowserTaskStatus] = mapped_column(
        Enum(BrowserTaskStatus, native_enum=False),
        default=BrowserTaskStatus.QUEUED,
        nullable=False,
        index=True,
    )
    pause_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    worker_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(64), default="LOCAL_INTERACTIVE", nullable=False)
    application_mode: Mapped[str] = mapped_column(String(32), default="ASSISTED", server_default="ASSISTED", nullable=False)
    assigned_device_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    confirmation_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confirmation_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    review_package_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    audit_events: Mapped[List[dict]] = mapped_column(JSON, default=list, nullable=False)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_browser_tasks_status_created", "status", "created_at"),
        UniqueConstraint("task_id", name="uq_browser_task_id"),
    )

    def __repr__(self) -> str:
        return f"<BrowserTask(id={self.id}, task_id='{self.task_id}', status='{self.status.value}')>"
