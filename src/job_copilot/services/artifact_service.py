"""High-level service coordinating object storage and relational artifact metadata."""

import hashlib
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy.orm import Session

from job_copilot.config import settings
from job_copilot.db.database import get_db
from job_copilot.domain.artifact_enums import ArtifactStatus, ArtifactType, StorageProvider
from job_copilot.models.artifact import ArtifactModel
from job_copilot.repositories.artifact_repository import ArtifactRepository
from job_copilot.storage.base import ArtifactStore
from job_copilot.storage.factory import create_artifact_store
from job_copilot.storage.key_builder import build_storage_key
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class ArtifactService:
    """
    Core service for Phase 10A Object Storage & Artifact Management.
    Decouples binary persistence from PostgreSQL metadata and protects application logic
    from provider-specific details.
    """

    def __init__(
        self,
        store: Optional[ArtifactStore] = None,
        repo: Optional[ArtifactRepository] = None,
        db: Optional[Session] = None,
    ):
        self.store = store or create_artifact_store()
        self._db = db
        self.repo = repo or (ArtifactRepository(db) if db is not None else None)

    def _get_repo(self) -> Tuple[ArtifactRepository, Optional[Session]]:
        """Resolve an active repository and session scope."""
        if self.repo is not None:
            return self.repo, None
        session_gen = get_db()
        session = next(session_gen)
        return ArtifactRepository(session), session

    def store_artifact(
        self,
        data: bytes,
        artifact_type: ArtifactType,
        application_id: Optional[str] = None,
        job_id: Optional[str] = None,
        original_filename: Optional[str] = None,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, Any]] = None,
        custom_artifact_id: Optional[str] = None,
    ) -> ArtifactModel:
        """
        Store an artifact's binary data into object storage and persist its metadata in PostgreSQL.
        Enforces SHA-256 calculation, size validation, and safe key generation.
        """
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Artifact data must be bytes or bytearray.")

        size_bytes = len(data)
        if size_bytes > settings.artifact_max_size_bytes:
            raise ValueError(
                f"Artifact size ({size_bytes} bytes) exceeds configured limit of {settings.artifact_max_size_bytes} bytes."
            )

        sha256 = hashlib.sha256(data).hexdigest()
        artifact_id = custom_artifact_id or f"art-{uuid.uuid4().hex[:12]}"

        # 1. Build safe deterministic storage key
        storage_key = build_storage_key(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            application_id=application_id,
            job_id=job_id,
            filename=original_filename,
        )

        repo, session = self._get_repo()
        try:
            # 2. Check for existing identical record (Idempotency)
            existing = repo.get_by_storage_key(storage_key)
            if existing:
                if existing.sha256 == sha256:
                    logger.info(
                        f"Artifact '{artifact_id}' already stored with identical checksum at '{storage_key}'. Returning existing record."
                    )
                    return existing
                else:
                    logger.warning(
                        f"Overwriting artifact at '{storage_key}' with updated content (sha256={sha256[:8]}...)"
                    )

            # 3. Store binary content in object storage
            stored_size, stored_sha = self.store.put(
                storage_key=storage_key,
                data=data,
                content_type=content_type,
            )

            # Integrity verification on write
            if stored_sha != sha256 or stored_size != size_bytes:
                raise IOError("Artifact write integrity mismatch between computed and stored hash.")

            # 4. Persist metadata in relational database with compensatory rollback on failure
            provider_type = (
                StorageProvider.S3
                if settings.artifact_storage_provider.lower() == "s3"
                else StorageProvider.LOCAL
            )

            try:
                if existing:
                    existing.size_bytes = stored_size
                    existing.sha256 = stored_sha
                    existing.content_type = content_type
                    existing.metadata_json = metadata or {}
                    existing.status = ArtifactStatus.ACTIVE
                    repo.db.commit()
                    repo.db.refresh(existing)
                    artifact_model = existing
                else:
                    artifact_model = ArtifactModel(
                        artifact_id=artifact_id,
                        application_id=application_id,
                        job_id=job_id,
                        artifact_type=artifact_type,
                        storage_provider=provider_type,
                        storage_key=storage_key,
                        content_type=content_type,
                        size_bytes=stored_size,
                        sha256=stored_sha,
                        original_filename=original_filename,
                        status=ArtifactStatus.ACTIVE,
                        metadata_json=metadata or {},
                    )
                    artifact_model = repo.create(artifact_model)

                logger.info(
                    f"Stored artifact '{artifact_id}' (type={artifact_type.value}, size={stored_size} bytes) via {provider_type.value}"
                )
                return artifact_model

            except Exception as db_err:
                logger.error(
                    f"Database persistence failed for artifact '{artifact_id}'. Triggering compensatory object storage cleanup: {db_err}"
                )
                try:
                    repo.db.rollback()
                except Exception:
                    pass
                try:
                    # Clean up newly uploaded binary to prevent orphaned objects
                    if not existing:
                        self.store.delete(storage_key)
                except Exception as clean_err:
                    logger.warning(f"Compensatory storage cleanup notice for '{storage_key}': {clean_err}")
                raise

        finally:
            if session:
                session.close()

    def get_artifact(self, artifact_id: str) -> Tuple[bytes, ArtifactModel]:
        """Retrieve binary content and metadata for an artifact."""
        repo, session = self._get_repo()
        try:
            artifact = repo.get_by_artifact_id(artifact_id)
            if not artifact:
                raise FileNotFoundError(f"Artifact metadata not found for ID '{artifact_id}'")

            data = self.store.get(artifact.storage_key)

            # Verify integrity
            current_sha = hashlib.sha256(data).hexdigest()
            if current_sha != artifact.sha256:
                raise IOError(
                    f"Integrity check failed for artifact '{artifact_id}': expected SHA {artifact.sha256}, got {current_sha}"
                )

            return data, artifact
        finally:
            if session:
                session.close()

    def get_artifact_metadata(self, artifact_id: str) -> Optional[ArtifactModel]:
        """Fetch artifact metadata without reading binary content."""
        repo, session = self._get_repo()
        try:
            return repo.get_by_artifact_id(artifact_id)
        finally:
            if session:
                session.close()

    def list_artifacts(
        self,
        application_id: Optional[str] = None,
        job_id: Optional[str] = None,
        artifact_type: Optional[ArtifactType] = None,
        status: Optional[ArtifactStatus] = None,
    ) -> List[ArtifactModel]:
        """List artifacts matching criteria."""
        repo, session = self._get_repo()
        try:
            if application_id:
                return repo.list_by_application(application_id, artifact_type=artifact_type, status=status)
            if job_id:
                return repo.list_by_job(job_id, artifact_type=artifact_type, status=status)
            return repo.list_all(status=status)
        finally:
            if session:
                session.close()

    def get_download_url(self, artifact_id: str, expires_in_seconds: int = 3600) -> Optional[str]:
        """Generate a time-limited download URL if supported by the store."""
        repo, session = self._get_repo()
        try:
            artifact = repo.get_by_artifact_id(artifact_id)
            if not artifact:
                return None
            return self.store.presigned_url(artifact.storage_key, expires_in_seconds=expires_in_seconds)
        finally:
            if session:
                session.close()

    def archive_artifact(self, artifact_id: str) -> bool:
        """Mark artifact as ARCHIVED."""
        repo, session = self._get_repo()
        try:
            updated = repo.update_status(artifact_id, ArtifactStatus.ARCHIVED)
            return updated is not None
        finally:
            if session:
                session.close()

    def delete_artifact(self, artifact_id: str, hard_delete: bool = False) -> bool:
        """
        Delete artifact.
        If hard_delete=False (default), marks status as DELETED (soft-delete).
        If hard_delete=True, removes the binary object from storage and deletes metadata record.
        """
        repo, session = self._get_repo()
        try:
            artifact = repo.get_by_artifact_id(artifact_id)
            if not artifact:
                return False

            if not hard_delete:
                repo.update_status(artifact_id, ArtifactStatus.DELETED)
                logger.info(f"Soft-deleted artifact '{artifact_id}'")
                return True
            else:
                self.store.delete(artifact.storage_key)
                repo.delete(artifact_id)
                logger.info(f"Hard-deleted artifact '{artifact_id}' from storage and metadata")
                return True
        finally:
            if session:
                session.close()

    def verify_integrity(self, artifact_id: str) -> bool:
        """Verify that the stored object exists and matches its recorded SHA-256 hash."""
        repo, session = self._get_repo()
        try:
            artifact = repo.get_by_artifact_id(artifact_id)
            if not artifact:
                return False
            if not self.store.exists(artifact.storage_key):
                return False
            data = self.store.get(artifact.storage_key)
            actual_sha = hashlib.sha256(data).hexdigest()
            return actual_sha == artifact.sha256 and len(data) == artifact.size_bytes
        except Exception as e:
            logger.warning(f"Integrity verification failed for '{artifact_id}': {e}")
            return False
        finally:
            if session:
                session.close()
