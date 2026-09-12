"""Domain enums for Phase 10B Cloud Browser Worker."""

from enum import Enum


class BrowserTaskStatus(str, Enum):
    """Explicit state machine for browser execution tasks."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    USER_INPUT_REQUIRED = "USER_INPUT_REQUIRED"
    BLOCKED = "BLOCKED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class FieldAction(str, Enum):
    """Classification of action to take for a detected form field."""

    AUTO_FILL = "AUTO_FILL"
    REQUIRES_USER_INPUT = "REQUIRES_USER_INPUT"
    DO_NOT_FILL = "DO_NOT_FILL"
    UNKNOWN = "UNKNOWN"


class AuthenticatedSessionStatus(str, Enum):
    """Status lifecycle for source-authenticated browser sessions."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"
    REVOKED = "REVOKED"
