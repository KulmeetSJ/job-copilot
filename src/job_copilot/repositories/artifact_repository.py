"""SQLAlchemy repository for Phase 10A Artifact metadata."""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_copilot.domain.artifact_enums import ArtifactStatus, ArtifactType
from job_copilot.models.artifact import ArtifactModel


class ArtifactRepository:
    """Repository managing artifact metadata in PostgreSQL."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, artifact: ArtifactModel) -> ArtifactModel:
        """Persist a new artifact metadata record."""
        self.db.add(artifact)
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def get_by_id(self, id: int) -> Optional[ArtifactModel]:
        """Fetch artifact by primary key."""
        stmt = select(ArtifactModel).where(ArtifactModel.id == id)
        return self.db.scalars(stmt).first()

    def get_by_artifact_id(self, artifact_id: str) -> Optional[ArtifactModel]:
        """Fetch artifact by unique string artifact_id."""
        stmt = select(ArtifactModel).where(ArtifactModel.artifact_id == artifact_id)
        return self.db.scalars(stmt).first()

    def get_by_sha256(self, sha256: str) -> Optional[ArtifactModel]:
        """Find an artifact with the given content checksum."""
        stmt = select(ArtifactModel).where(ArtifactModel.sha256 == sha256)
        return self.db.scalars(stmt).first()

    def get_by_storage_key(self, storage_key: str) -> Optional[ArtifactModel]:
        """Fetch artifact by storage key."""
        stmt = select(ArtifactModel).where(ArtifactModel.storage_key == storage_key)
        return self.db.scalars(stmt).first()

    def list_by_application(
        self,
        application_id: str,
        artifact_type: Optional[ArtifactType] = None,
        status: Optional[ArtifactStatus] = None,
    ) -> List[ArtifactModel]:
        """List artifacts associated with an application."""
        stmt = select(ArtifactModel).where(ArtifactModel.application_id == application_id)
        if artifact_type:
            stmt = stmt.where(ArtifactModel.artifact_type == artifact_type)
        if status:
            stmt = stmt.where(ArtifactModel.status == status)
        stmt = stmt.order_by(ArtifactModel.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def list_by_job(
        self,
        job_id: str,
        artifact_type: Optional[ArtifactType] = None,
        status: Optional[ArtifactStatus] = None,
    ) -> List[ArtifactModel]:
        """List artifacts associated with a job posting."""
        stmt = select(ArtifactModel).where(ArtifactModel.job_id == job_id)
        if artifact_type:
            stmt = stmt.where(ArtifactModel.artifact_type == artifact_type)
        if status:
            stmt = stmt.where(ArtifactModel.status == status)
        stmt = stmt.order_by(ArtifactModel.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def list_all(
        self,
        limit: int = 100,
        status: Optional[ArtifactStatus] = None,
    ) -> List[ArtifactModel]:
        """List recent artifacts."""
        stmt = select(ArtifactModel)
        if status:
            stmt = stmt.where(ArtifactModel.status == status)
        stmt = stmt.order_by(ArtifactModel.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())

    def update_status(self, artifact_id: str, status: ArtifactStatus) -> Optional[ArtifactModel]:
        """Update artifact lifecycle status (ACTIVE, ARCHIVED, DELETED)."""
        artifact = self.get_by_artifact_id(artifact_id)
        if not artifact:
            return None
        artifact.status = status
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def delete(self, artifact_id: str) -> bool:
        """Permanently remove artifact record from database."""
        artifact = self.get_by_artifact_id(artifact_id)
        if not artifact:
            return False
        self.db.delete(artifact)
        self.db.commit()
        return True
