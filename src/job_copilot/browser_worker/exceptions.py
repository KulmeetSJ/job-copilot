"""Domain exceptions for Phase 10B Browser Worker."""


class BrowserWorkerError(Exception):
    """Base exception for all browser worker errors."""
    pass


class DomainSecurityError(BrowserWorkerError):
    """Raised when an untrusted or disallowed domain / URL scheme is targeted."""
    pass


class CaptchaDetectedError(BrowserWorkerError):
    """Raised when CAPTCHA or anti-bot challenge is detected (worker pauses safely)."""
    pass


class LoginRequiredError(BrowserWorkerError):
    """Raised when an authentication wall is detected (worker pauses safely)."""
    pass


class SubmissionSafetyError(BrowserWorkerError):
    """Raised when an unauthorized, stale, or invalid submission attempt is detected."""
    pass


class SensitiveFieldPauseError(BrowserWorkerError):
    """Raised when a sensitive or unknown field requires human user input."""
    pass
