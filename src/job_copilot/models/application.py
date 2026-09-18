"""SQLAlchemy ORM models for Applications, Append-Only Lifecycle Events, and Frozen Snapshots."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_copilot.domain.enums import ApplicationMode, ApplicationStatus, ResumeStrategy
from job_copilot.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from job_copilot.models.job import Job


from sqlalchemy import TypeDecorator


class ResumeStrategyType(TypeDecorator):
    """SQLAlchemy column type for ResumeStrategy that safely maps legacy values to canonical strategies."""
    impl = String(50)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return ResumeStrategy.BACKEND_JAVA.value
        if isinstance(value, ResumeStrategy):
            return value.value
        return ResumeStrategy.normalize(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return ResumeStrategy.BACKEND_JAVA
        norm = ResumeStrategy.normalize(value)
        return ResumeStrategy(norm)


class Application(Base, TimestampMixin):
    """Represents the candidate's application to a specific job posting."""
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    job_id_str: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    canonical_job_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    source: Mapped[str] = mapped_column(String(100), default="unknown", nullable=False)

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False),
        default=ApplicationStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    mode: Mapped[ApplicationMode] = mapped_column(
        Enum(ApplicationMode, native_enum=False),
        default=ApplicationMode.ASSISTED,
        server_default="ASSISTED",
        nullable=False,
        index=True,
    )
    current_status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    strategy_used: Mapped[ResumeStrategy] = mapped_column(
        ResumeStrategyType(),
        default=ResumeStrategy.BACKEND_JAVA,
        nullable=False,
    )
    resume_strategy: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    package_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    browser_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_notes: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    discovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    recommended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    prepared_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="application")
    events: Mapped[List["ApplicationEventModel"]] = relationship(
        "ApplicationEventModel",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEventModel.timestamp",
    )
    snapshot: Mapped[Optional["ApplicationSnapshotModel"]] = relationship(
        "ApplicationSnapshotModel",
        back_populates="application",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("job_id", name="uq_application_job_id"),
    )

    def __repr__(self) -> str:
        return f"<Application(id={self.id}, app_id='{self.application_id}', status='{self.status.value}')>"


class ApplicationEventModel(Base):
    """Immutable append-only lifecycle event ledger (Phase 8)."""
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    application_id_ref: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    job_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), default="MANUAL", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application: Mapped["Application"] = relationship("Application", back_populates="events")

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_application_event_id"),
        UniqueConstraint("application_id", "event_type", "timestamp", name="uq_app_event_tuple"),
    )

    def __repr__(self) -> str:
        return f"<ApplicationEvent(id='{self.event_id}', app='{self.application_id}', type='{self.event_type}')>"


class ApplicationSnapshotModel(Base):
    """Immutable frozen snapshot recorded at submission time (Phase 8)."""
    __tablename__ = "application_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id_ref: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    application_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    resume_strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False)
    technical_match: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    responsibility_match: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    seniority_match: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    professional_evidence_match: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    domain_match: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    preference_match: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    credential_match: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    job_source: Mapped[str] = mapped_column(String(100), default="unknown", nullable=False)
    resume_pdf_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    cover_letter_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    applied_via: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    application: Mapped["Application"] = relationship("Application", back_populates="snapshot")

    def __repr__(self) -> str:
        return f"<ApplicationSnapshot(app='{self.application_id}', strategy='{self.resume_strategy}', score={self.match_score})>"
