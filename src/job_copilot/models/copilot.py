"""SQLAlchemy ORM models for Phase 9 Copilot Queue and Phase 9.2 Source Health."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from job_copilot.models.base import Base, TimestampMixin, utc_now


class CopilotQueueRecord(Base, TimestampMixin):
    """Persists the prioritized Copilot Opportunity Queue state."""
    __tablename__ = "copilot_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    priority_band: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    queue_status: Mapped[str] = mapped_column(String(50), default="PENDING_REVIEW", nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), default="ASSISTED", server_default="ASSISTED", nullable=False)
    category_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reasons: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    user_notes: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (
        UniqueConstraint("job_id", name="uq_copilot_queue_job_id"),
    )

    def __repr__(self) -> str:
        return f"<CopilotQueueRecord(job_id='{self.job_id}', band='{self.priority_band}', score={self.priority_score})>"


class SourceHealthRecord(Base):
    """Durable operational state and check history for configured job sources (Phase 9.2)."""
    __tablename__ = "source_health"

    source_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False, index=True)
    discovery_mode: Mapped[str] = mapped_column(String(50), default="PUBLIC", nullable=False)
    requires_login: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    def __repr__(self) -> str:
        return f"<SourceHealthRecord(source='{self.source_id}', state='{self.state}')>"
