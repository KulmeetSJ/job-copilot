"""Phase 10B Browser Worker package."""

from job_copilot.browser_worker.browser import BrowserManager, BrowserSessionAdapter
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import (
    BrowserWorkerError,
    CaptchaDetectedError,
    DomainSecurityError,
    LoginRequiredError,
    SensitiveFieldPauseError,
    SubmissionSafetyError,
)
from job_copilot.browser_worker.models import (
    BrowserTaskResponse,
    BrowserTaskReviewPackage,
    BrowserWorkerTaskCreate,
    DetectedFieldInfo,
    HumanConfirmationRequest,
    HumanConfirmationResponse,
)
from job_copilot.browser_worker.safety import (
    is_prohibited_field,
    is_sensitive_field,
    validate_target_domain,
)
from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
from job_copilot.browser_worker.worker import BrowserWorker

__all__ = [
    "BrowserManager",
    "BrowserSessionAdapter",
    "BrowserTaskExecutor",
    "BrowserWorker",
    "HumanConfirmationService",
    "BrowserWorkerError",
    "DomainSecurityError",
    "CaptchaDetectedError",
    "LoginRequiredError",
    "SubmissionSafetyError",
    "SensitiveFieldPauseError",
    "BrowserWorkerTaskCreate",
    "BrowserTaskResponse",
    "BrowserTaskReviewPackage",
    "HumanConfirmationRequest",
    "HumanConfirmationResponse",
    "DetectedFieldInfo",
    "validate_target_domain",
    "is_sensitive_field",
    "is_prohibited_field",
]
