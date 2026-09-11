"""Abstract base interface for object storage providers."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple


class ArtifactStore(ABC):
    """Abstract interface representing a binary object store (Local filesystem, S3, R2, etc.)."""

    @abstractmethod
    def put(
        self,
        storage_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> Tuple[int, str]:
        """
        Store binary data at storage_key.
        Returns:
            Tuple of (size_bytes: int, sha256_checksum: str).
        """
        pass

    @abstractmethod
    def get(self, storage_key: str) -> bytes:
        """Retrieve binary data from storage_key. Raises FileNotFoundError if not found."""
        pass

    @abstractmethod
    def delete(self, storage_key: str) -> bool:
        """Delete object at storage_key. Returns True if deleted, False if not found."""
        pass

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Check if an object exists at storage_key."""
        pass

    @abstractmethod
    def presigned_url(self, storage_key: str, expires_in_seconds: int = 3600) -> Optional[str]:
        """Generate a time-limited read URL if supported by the provider."""
        pass

    @abstractmethod
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all storage keys matching the given prefix."""
        pass
