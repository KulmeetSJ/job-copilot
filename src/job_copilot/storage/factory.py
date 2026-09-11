"""Factory for instantiating the configured ArtifactStore implementation."""

from typing import Optional
from job_copilot.config import settings
from job_copilot.storage.base import ArtifactStore
from job_copilot.storage.local_store import LocalArtifactStore
from job_copilot.storage.s3_store import S3ArtifactStore
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def create_artifact_store(
    provider: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> ArtifactStore:
    """
    Instantiate and return an ArtifactStore according to configuration.
    Fails fast if cloud storage is misconfigured rather than silently falling back.
    """
    selected_provider = (provider or settings.artifact_storage_provider).lower()

    if selected_provider == "local":
        dir_path = base_dir or settings.artifact_storage_dir
        logger.debug(f"Initializing LocalArtifactStore at {dir_path}")
        return LocalArtifactStore(base_dir=dir_path)

    elif selected_provider == "s3":
        bucket = settings.artifact_storage_bucket
        if not bucket:
            raise ValueError(
                "ARTIFACT_STORAGE_BUCKET must be configured when ARTIFACT_STORAGE_PROVIDER is 's3'."
            )
        logger.debug(f"Initializing S3ArtifactStore with bucket '{bucket}' in region '{settings.artifact_storage_region}'")
        return S3ArtifactStore(
            bucket_name=bucket,
            region_name=settings.artifact_storage_region,
            endpoint_url=settings.artifact_storage_endpoint,
            access_key_id=settings.artifact_storage_access_key,
            secret_access_key=settings.artifact_storage_secret_key,
        )

    else:
        raise ValueError(
            f"Unsupported ARTIFACT_STORAGE_PROVIDER '{selected_provider}'. Must be 'local' or 's3'."
        )
