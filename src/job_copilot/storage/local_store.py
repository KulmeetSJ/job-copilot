"""Local filesystem object storage implementation."""

import hashlib
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from job_copilot.storage.base import ArtifactStore
from job_copilot.storage.key_builder import validate_storage_key
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class LocalArtifactStore(ArtifactStore):
    """
    Filesystem-backed implementation of ArtifactStore for local development and testing.
    All files are stored safely under a designated root directory.
    """

    def __init__(self, base_dir: Optional[Any] = None):
        self.base_dir = Path(base_dir or "data/artifacts").resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, storage_key: str) -> Path:
        """Resolve storage key to a filesystem path and verify boundary security."""
        validate_storage_key(storage_key)
        target = (self.base_dir / storage_key).resolve()

        # Strict containment check: target must be inside base_dir
        if not str(target).startswith(str(self.base_dir)):
            raise PermissionError(f"Path traversal detected for storage key '{storage_key}'")

        return target

    def put(
        self,
        storage_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> Tuple[int, str]:
        """Write binary data to local filesystem atomically and return size + sha256."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Data must be bytes or bytearray.")

        target_path = self._resolve_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Calculate sha256 and size
        sha256 = hashlib.sha256(data).hexdigest()
        size_bytes = len(data)

        # Atomic write via temporary file in same parent directory
        tmp_path = target_path.with_name(f".tmp_{os.getpid()}_{target_path.name}")
        try:
            tmp_path.write_bytes(data)
            tmp_path.replace(target_path)
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise IOError(f"Failed to write artifact at '{storage_key}': {e}") from e

        logger.debug(f"Local store persisted {size_bytes} bytes to '{storage_key}' (sha256={sha256[:12]}...)")
        return size_bytes, sha256

    def get(self, storage_key: str) -> bytes:
        """Read binary data from local filesystem."""
        target_path = self._resolve_path(storage_key)
        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"Artifact not found at storage key '{storage_key}'")

        return target_path.read_bytes()

    def delete(self, storage_key: str) -> bool:
        """Delete file from local filesystem."""
        try:
            target_path = self._resolve_path(storage_key)
            if target_path.exists() and target_path.is_file():
                target_path.unlink()
                # Clean up empty parent directories if any
                parent = target_path.parent
                while parent != self.base_dir and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to delete artifact at '{storage_key}': {e}")
            return False

    def exists(self, storage_key: str) -> bool:
        """Check if file exists."""
        try:
            target_path = self._resolve_path(storage_key)
            return target_path.exists() and target_path.is_file()
        except Exception:
            return False

    def presigned_url(self, storage_key: str, expires_in_seconds: int = 3600) -> Optional[str]:
        """Return a local file URI or relative endpoint."""
        target_path = self._resolve_path(storage_key)
        if not target_path.exists():
            return None
        return f"file://{target_path}"

    def list_keys(self, prefix: str = "") -> List[str]:
        """List all relative storage keys matching the given prefix."""
        prefix_clean = prefix.replace("\\", "/").strip("/")
        results: List[str] = []

        for root, _, files in os.walk(self.base_dir):
            for f in sorted(files):
                if f.startswith("."):
                    continue
                full_p = Path(root) / f
                rel_p = full_p.relative_to(self.base_dir).as_posix()
                if not prefix_clean or rel_p.startswith(prefix_clean):
                    results.append(rel_p)

        return results
