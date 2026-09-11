"""Domain enums for Phase 10A Object Storage and Artifact Management."""

from enum import Enum


class ArtifactType(str, Enum):
    """Controlled vocabulary for stored artifact types."""

    TAILORED_RESUME_PDF = "TAILORED_RESUME_PDF"
    TAILORED_RESUME_TEX = "TAILORED_RESUME_TEX"
    COVER_LETTER = "COVER_LETTER"
    APPLICATION_PACKAGE = "APPLICATION_PACKAGE"
    QUESTIONS = "QUESTIONS"
    ANSWERS = "ANSWERS"
    VALIDATION_REPORT = "VALIDATION_REPORT"
    SCREENSHOT = "SCREENSHOT"
    PLAYWRIGHT_TRACE = "PLAYWRIGHT_TRACE"
    BROWSER_DIAGNOSTIC = "BROWSER_DIAGNOSTIC"
    OTHER = "OTHER"


class ArtifactStatus(str, Enum):
    """Lifecycle status for persisted artifacts."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


class StorageProvider(str, Enum):
    """Supported storage provider backends."""

    LOCAL = "local"
    S3 = "s3"
