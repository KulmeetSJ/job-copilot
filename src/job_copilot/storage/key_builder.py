"""Safe, deterministic storage key generation and path traversal defenses."""

import re
from typing import Optional

from job_copilot.domain.artifact_enums import ArtifactType


def sanitize_filename(filename: Optional[str]) -> str:
    """
    Sanitize filename to prevent directory traversal and illegal characters.
    Only allows alphanumeric characters, underscores, hyphens, and periods.
    """
    if not filename:
        return "artifact.bin"

    # Replace any directory components or path separators with underscores
    clean = re.sub(r"[\\/]", "_", filename)
    # Strip dangerous characters, spaces, and control characters
    clean = re.sub(r"[^\w\.\-]", "_", clean)
    # Disallow leading periods or double dots
    clean = clean.lstrip(".")
    while ".." in clean:
        clean = clean.replace("..", "_")
    clean = clean.strip("_")

    return clean if clean else "artifact.bin"


def sanitize_path_segment(segment: Optional[str], default: str = "general") -> str:
    """Sanitize a logical path segment (application ID, job ID, artifact ID)."""
    if not segment:
        return default
    clean = re.sub(r"[^\w\-]", "_", segment)
    clean = clean.strip("_")
    return clean if clean else default


def validate_storage_key(storage_key: str) -> None:
    """
    Validate that a storage key does not contain directory traversal or illegal prefixes.
    Raises ValueError if unsafe.
    """
    if not storage_key or not isinstance(storage_key, str):
        raise ValueError("Storage key must be a non-empty string.")

    if "\x00" in storage_key:
        raise ValueError("Storage key contains null bytes.")

    if storage_key.startswith("/") or storage_key.startswith("\\"):
        raise ValueError("Storage key cannot be an absolute path.")

    parts = storage_key.replace("\\", "/").split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise ValueError(f"Storage key contains illegal path segment: '{part}'")
        if re.search(r"[\x00-\x1f\x7f]", part):
            raise ValueError("Storage key contains invalid control characters.")


def build_storage_key(
    artifact_type: ArtifactType,
    artifact_id: str,
    application_id: Optional[str] = None,
    job_id: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Construct a safe, deterministic, collision-resistant storage key.
    Format: applications/{parent_scope}/{type_folder}/{artifact_id}/{safe_filename}
    """
    parent_scope = sanitize_path_segment(application_id or job_id, default="general")
    type_folder = artifact_type.value.lower()
    safe_art_id = sanitize_path_segment(artifact_id, default="unknown")
    safe_fn = sanitize_filename(filename)

    key = f"applications/{parent_scope}/{type_folder}/{safe_art_id}/{safe_fn}"
    validate_storage_key(key)
    return key
