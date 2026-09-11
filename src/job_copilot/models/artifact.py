"""SQLAlchemy ORM model for Artifact metadata (Phase 10A)."""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, DateTime, Enum, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from job_copilot.domain.artifact_enums import ArtifactStatus, ArtifactType, StorageProvider
from job_copilot.models.base import Base, TimestampMixin, utc_now


class ArtifactModel(Base, TimestampMixin):
    """
    Persisted metadata and references for durable application artifacts.
    Binary content is stored in object storage (Local / S3), not in PostgreSQL.
    """

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    application_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)

    artifact_type: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType, native_enum=False),
        nullable=False,
        index=True,
    )
    storage_provider: Mapped[StorageProvider] = mapped_column(
        Enum(StorageProvider, native_enum=False),
        default=StorageProvider.LOCAL,
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream", nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[ArtifactStatus] = mapped_column(
        Enum(ArtifactStatus, native_enum=False),
        default=ArtifactStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_artifacts_app_type", "application_id", "artifact_type"),
        Index("ix_artifacts_job_type", "job_id", "artifact_type"),
        UniqueConstraint("artifact_id", name="uq_artifact_id"),
    )

    def __repr__(self) -> str:
        return f"<Artifact(id={self.id}, artifact_id='{self.artifact_id}', type='{self.artifact_type.value}', size={self.size_bytes})>"
