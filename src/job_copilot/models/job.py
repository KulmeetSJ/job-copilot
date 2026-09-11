"""SQLAlchemy ORM models for Jobs and Job Provenance."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_copilot.domain.enums import EmploymentType, RemoteStatus
from job_copilot.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from job_copilot.models.application import Application
    from job_copilot.models.recommendation import RecommendationRecord


class Job(Base, TimestampMixin):
    """Represents a canonical job posting discovered or ingested into the system."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    canonical_url: Mapped[Optional[str]] = mapped_column(String(1024), index=True, nullable=True)
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
    normalized_content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(50), default="DISCOVERED", index=True, nullable=False)
    duplicate_of: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

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

    # Relationships
    provenance: Mapped[List["JobProvenance"]] = relationship(
        "JobProvenance",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    recommendation: Mapped[Optional["RecommendationRecord"]] = relationship(
        "RecommendationRecord",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )
    application: Mapped[Optional["Application"]] = relationship(
        "Application",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, job_id='{self.job_id}', title='{self.title}', company='{self.company}')>"


class JobProvenance(Base, TimestampMixin):
    """Tracks multi-source discovery provenance for a job posting."""
    __tablename__ = "job_provenance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id_ref: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_job_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    job: Mapped["Job"] = relationship("Job", back_populates="provenance")

    __table_args__ = (
        UniqueConstraint("job_id_ref", "source_id", "source_url", name="uq_job_source_provenance"),
    )

    def __repr__(self) -> str:
        return f"<JobProvenance(source='{self.source_id}', url='{self.source_url}')>"
