"""SQLAlchemy ORM model for Applications."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_copilot.domain.enums import ApplicationStatus, ResumeStrategy
from job_copilot.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from job_copilot.models.job import Job


class Application(Base, TimestampMixin):
    """Represents the candidate's application to a specific job posting."""
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False),
        default=ApplicationStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    strategy_used: Mapped[ResumeStrategy] = mapped_column(
        Enum(ResumeStrategy, native_enum=False),
        default=ResumeStrategy.GENERAL_SWE,
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationship back to Job
    job: Mapped["Job"] = relationship("Job", back_populates="application")

    __table_args__ = (
        UniqueConstraint("job_id", name="uq_application_job_id"),
    )

    def __repr__(self) -> str:
        return f"<Application(id={self.id}, job_id={self.job_id}, status='{self.status.value}')>"
