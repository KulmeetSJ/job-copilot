"""Object storage package for Job Copilot."""

from job_copilot.storage.base import ArtifactStore
from job_copilot.storage.factory import create_artifact_store
from job_copilot.storage.key_builder import build_storage_key, sanitize_filename, validate_storage_key
from job_copilot.storage.local_store import LocalArtifactStore
from job_copilot.storage.s3_store import S3ArtifactStore

__all__ = [
    "ArtifactStore",
    "LocalArtifactStore",
    "S3ArtifactStore",
    "create_artifact_store",
    "build_storage_key",
    "sanitize_filename",
    "validate_storage_key",
]
