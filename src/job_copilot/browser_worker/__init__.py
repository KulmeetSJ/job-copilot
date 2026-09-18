"""Phase 10B Browser Worker package."""

from job_copilot.browser_worker.adapters import (
    GenericPortalAdapter,
    InstahyreAdapter,
    JobSourceBrowserAdapter,
    LinkedInAdapter,
    NaukriAdapter,
    SourceAdapterRegistry,
)
from job_copilot.browser_worker.auto_apply_policy import (
    AutoApplyEligibilityResult,
    AutoApplyPolicyService,
    evaluate_auto_apply_eligibility,
)
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
from job_copilot.browser_worker.session_manager import AuthenticatedSessionManager
from job_copilot.browser_worker.session_store import BrowserSessionStore
from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
from job_copilot.browser_worker.worker import BrowserWorker

__all__ = [
    "BrowserManager",
    "BrowserSessionAdapter",
    "BrowserTaskExecutor",
    "BrowserWorker",
    "BrowserSessionStore",
    "AuthenticatedSessionManager",
    "SourceAdapterRegistry",
    "JobSourceBrowserAdapter",
    "LinkedInAdapter",
    "NaukriAdapter",
    "InstahyreAdapter",
    "GenericPortalAdapter",
    "HumanConfirmationService",
    "AutoApplyEligibilityResult",
    "AutoApplyPolicyService",
    "evaluate_auto_apply_eligibility",
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
    "is_sensitive_field",
    "is_prohibited_field",
    "validate_target_domain",
]

