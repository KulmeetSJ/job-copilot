"""Non-destructive migration utility to index existing filesystem artifacts into object storage."""

import json
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from job_copilot.domain.artifact_enums import ArtifactType
from job_copilot.models.artifact import ArtifactModel
from job_copilot.services.artifact_service import ArtifactService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def infer_artifact_type(file_path: Path) -> ArtifactType:
    """Infer ArtifactType from file name and extension."""
    name = file_path.name.lower()
    suffix = file_path.suffix.lower()

    if name == "package.json":
        return ArtifactType.APPLICATION_PACKAGE
    elif name.startswith("cover_letter"):
        return ArtifactType.COVER_LETTER
    elif name == "questions.json":
        return ArtifactType.QUESTIONS
    elif name == "answers.json":
        return ArtifactType.ANSWERS
    elif name.startswith("validation"):
        return ArtifactType.VALIDATION_REPORT
    elif suffix == ".pdf":
        return ArtifactType.TAILORED_RESUME_PDF
    elif suffix == ".tex":
        return ArtifactType.TAILORED_RESUME_TEX
    elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
        return ArtifactType.SCREENSHOT
    elif suffix in (".har", ".zip") or "trace" in name:
        return ArtifactType.PLAYWRIGHT_TRACE
    elif suffix == ".json" and "diagnostic" in name:
        return ArtifactType.BROWSER_DIAGNOSTIC
    else:
        return ArtifactType.OTHER


def infer_content_type(file_path: Path) -> str:
    """Infer MIME content type from file suffix."""
    suffix = file_path.suffix.lower()
    mapping = {
        ".pdf": "application/pdf",
        ".tex": "text/x-tex",
        ".json": "application/json",
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".zip": "application/zip",
        ".har": "application/json",
    }
    return mapping.get(suffix, "application/octet-stream")


def migrate_existing_filesystem_artifacts(
    applications_dir: Optional[Path] = None,
    artifact_service: Optional[ArtifactService] = None,
    db_session: Optional[Session] = None,
) -> Dict[str, int]:
    """
    Scan applications directory and register existing artifacts into Object Storage and PostgreSQL.
    Strictly non-destructive: does not delete or alter original files.
    """
    apps_path = applications_dir or Path("data/applications")
    if not apps_path.exists():
        logger.info(f"No existing applications directory found at {apps_path}")
        return {"discovered": 0, "migrated": 0, "skipped": 0, "errors": 0}

    service = artifact_service or ArtifactService(db=db_session)
    counts = {"discovered": 0, "migrated": 0, "skipped": 0, "errors": 0}

    logger.info(f"Starting non-destructive artifact migration from: {apps_path}")

    for job_dir in apps_path.iterdir():
        if not job_dir.is_dir() or job_dir.name.startswith("."):
            continue

        job_id = job_dir.name
        # Try to resolve application_id from package.json if available
        application_id = job_id
        pkg_file = job_dir / "package.json"
        if pkg_file.exists():
            try:
                pkg_data = json.loads(pkg_file.read_text(encoding="utf-8"))
                application_id = pkg_data.get("application_id", job_id)
            except Exception:
                pass

        for file_path in job_dir.rglob("*"):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue

            counts["discovered"] += 1
            rel_name = file_path.name
            art_type = infer_artifact_type(file_path)
            content_type = infer_content_type(file_path)

            try:
                data = file_path.read_bytes()
                service.store_artifact(
                    data=data,
                    artifact_type=art_type,
                    application_id=application_id,
                    job_id=job_id,
                    original_filename=rel_name,
                    content_type=content_type,
                    metadata={"migrated_from_path": str(file_path)},
                )
                counts["migrated"] += 1
            except Exception as e:
                logger.warning(f"Error migrating artifact '{file_path}': {e}")
                counts["errors"] += 1

    logger.info(
        f"Artifact migration completed: {counts['migrated']}/{counts['discovered']} migrated, {counts['errors']} errors"
    )
    return counts
