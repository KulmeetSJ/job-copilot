"""Phase 7 Browser-Assisted Application Workflow package."""

from job_copilot.browser.adapter import BrowserAdapter, PlaywrightBrowserAdapter
from job_copilot.browser.classifier import FieldClassifier
from job_copilot.browser.detector import FormDetector
from job_copilot.browser.mapper import FieldMapper
from job_copilot.browser.models import (
    BrowserAuditEvent,
    BrowserAuditEventType,
    BrowserElementType,
    BrowserField,
    BrowserSession,
    BrowserSessionStatus,
    FieldClassification,
    FieldMapping,
    MappingConfidence,
    ReviewArtifact,
    SubmissionResult,
)

__all__ = [
    "BrowserAdapter",
    "PlaywrightBrowserAdapter",
    "FormDetector",
    "FieldClassifier",
    "FieldMapper",
    "BrowserField",
    "BrowserElementType",
    "FieldClassification",
    "MappingConfidence",
    "FieldMapping",
    "BrowserSession",
    "BrowserSessionStatus",
    "BrowserAuditEvent",
    "BrowserAuditEventType",
    "ReviewArtifact",
    "SubmissionResult",
]
