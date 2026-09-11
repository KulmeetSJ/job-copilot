"""S3-compatible object storage implementation (AWS S3, Cloudflare R2, MinIO, Wasabi)."""

import hashlib
import io
from typing import Any, List, Optional, Tuple

from job_copilot.storage.base import ArtifactStore
from job_copilot.storage.key_builder import validate_storage_key
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class S3ArtifactStore(ArtifactStore):
    """
    S3-compatible implementation of ArtifactStore.
    Works with AWS S3, Cloudflare R2, MinIO, Wasabi, and other standard S3 endpoints.
    """

    def __init__(
        self,
        bucket_name: str,
        region_name: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        if not bucket_name:
            raise ValueError("S3ArtifactStore requires a valid 'bucket_name'.")

        self.bucket_name = bucket_name
        self.region_name = region_name
        self.endpoint_url = endpoint_url

        if client is not None:
            self._client = client
        else:
            try:
                import boto3
                from botocore.config import Config

                config = Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                )
                self._client = boto3.client(
                    "s3",
                    region_name=self.region_name,
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key,
                    config=config,
                )
            except ImportError as e:
                raise ImportError(
                    "boto3 package is required for S3ArtifactStore. Install via `pip install boto3`."
                ) from e

    def put(
        self,
        storage_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> Tuple[int, str]:
        """Upload binary data to S3 bucket and return size + sha256 checksum."""
        validate_storage_key(storage_key)
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Data must be bytes or bytearray.")

        sha256 = hashlib.sha256(data).hexdigest()
        size_bytes = len(data)

        try:
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=data,
                ContentType=content_type,
                Metadata={"sha256": sha256},
            )
            logger.debug(f"S3 store uploaded {size_bytes} bytes to '{self.bucket_name}/{storage_key}'")
            return size_bytes, sha256
        except Exception as e:
            logger.error(f"S3 put_object failed for '{storage_key}': {e}")
            raise IOError(f"Failed uploading to S3 at '{storage_key}': {e}") from e

    def get(self, storage_key: str) -> bytes:
        """Download binary data from S3 bucket."""
        validate_storage_key(storage_key)
        try:
            response = self._client.get_object(
                Bucket=self.bucket_name,
                Key=storage_key,
            )
            body = response["Body"]
            return body.read()
        except self._client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Artifact not found in S3 at key '{storage_key}'")
        except Exception as e:
            if "NoSuchKey" in type(e).__name__ or "404" in str(e):
                raise FileNotFoundError(f"Artifact not found in S3 at key '{storage_key}'") from e
            logger.error(f"S3 get_object failed for '{storage_key}': {e}")
            raise IOError(f"Failed retrieving from S3 at '{storage_key}': {e}") from e

    def delete(self, storage_key: str) -> bool:
        """Delete object from S3 bucket."""
        validate_storage_key(storage_key)
        try:
            if not self.exists(storage_key):
                return False
            self._client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_key,
            )
            return True
        except Exception as e:
            logger.warning(f"S3 delete_object failed for '{storage_key}': {e}")
            return False

    def exists(self, storage_key: str) -> bool:
        """Check if object exists in S3 bucket via head_object."""
        validate_storage_key(storage_key)
        try:
            self._client.head_object(
                Bucket=self.bucket_name,
                Key=storage_key,
            )
            return True
        except Exception:
            return False

    def presigned_url(self, storage_key: str, expires_in_seconds: int = 3600) -> Optional[str]:
        """Generate time-limited presigned GET URL."""
        validate_storage_key(storage_key)
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": storage_key},
                ExpiresIn=expires_in_seconds,
            )
            return url
        except Exception as e:
            logger.warning(f"Failed to generate presigned URL for '{storage_key}': {e}")
            return None

    def list_keys(self, prefix: str = "") -> List[str]:
        """List object keys under the given prefix."""
        results: List[str] = []
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
            for page in pages:
                for obj in page.get("Contents", []):
                    results.append(obj["Key"])
            return results
        except Exception as e:
            logger.warning(f"S3 list_keys failed for prefix '{prefix}': {e}")
            return []
