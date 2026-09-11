"""SQLAlchemy ORM model for Jobs."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Enum, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_copilot.domain.enums import EmploymentType, RemoteStatus
from job_copilot.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from job_copilot.models.application import Application


class Job(Base, TimestampMixin):
    """Represents a job posting discovered or inputted into the system."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    remote_status: Mapped[RemoteStatus] = mapped_column(
        Enum(RemoteStatus, native_enum=False),
        default=RemoteStatus.UNKNOWN,
        nullable=False,
    )
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType, native_enum=False),
        default=EmploymentType.FULL_TIME,
        nullable=False,
    )
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), default="manual", nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Structured extraction stored as JSON
    requirements: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    preferred_qualifications: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    technologies: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    years_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Compensation
    salary_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)

    # Timestamps
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # 1:1 Relationship with Application
    application: Mapped[Optional["Application"]] = relationship(
        "Application",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.title}', company='{self.company}')>"
