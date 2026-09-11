"""Data models for Phase 7 Browser-Assisted Application Workflow."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BrowserSessionStatus(str, Enum):
    """Lifecycle states of a browser session."""
    CREATED = "CREATED"
    NAVIGATING = "NAVIGATING"
    INSPECTING = "INSPECTING"
    MAPPING = "MAPPING"
    FILLING = "FILLING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    READY_TO_SUBMIT = "READY_TO_SUBMIT"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BrowserElementType(str, Enum):
    """HTML form element types."""
    INPUT_TEXT = "INPUT_TEXT"
    INPUT_EMAIL = "INPUT_EMAIL"
    INPUT_TEL = "INPUT_TEL"
    INPUT_NUMBER = "INPUT_NUMBER"
    INPUT_FILE = "INPUT_FILE"
    INPUT_RADIO = "INPUT_RADIO"
    INPUT_CHECKBOX = "INPUT_CHECKBOX"
    INPUT_DATE = "INPUT_DATE"
    TEXTAREA = "TEXTAREA"
    SELECT = "SELECT"
    BUTTON = "BUTTON"
    UNKNOWN = "UNKNOWN"


class FieldClassification(str, Enum):
    """Semantic classification of a detected form field."""
    KNOWN_CANDIDATE_FIELD = "KNOWN_CANDIDATE_FIELD"
    APPLICATION_QUESTION = "APPLICATION_QUESTION"
    USER_INPUT_REQUIRED = "USER_INPUT_REQUIRED"
    FILE_UPLOAD = "FILE_UPLOAD"
    JOB_METADATA = "JOB_METADATA"
    UNKNOWN = "UNKNOWN"
    DO_NOT_TOUCH = "DO_NOT_TOUCH"


class MappingConfidence(str, Enum):
    """Confidence level of field mapping."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class BrowserField(BaseModel):
    """Structured representation of a detected DOM form field."""
    field_id: str = Field(description="Unique field identifier (e.g., element ID, name, or generated locator)")
    element_type: BrowserElementType = Field(default=BrowserElementType.INPUT_TEXT)
    name: Optional[str] = Field(default=None, description="HTML name attribute")
    id_attr: Optional[str] = Field(default=None, description="HTML id attribute")
    label: Optional[str] = Field(default=None, description="Associated label text")
    placeholder: Optional[str] = Field(default=None, description="Placeholder text")
    aria_label: Optional[str] = Field(default=None, description="ARIA label")
    autocomplete: Optional[str] = Field(default=None, description="Autocomplete attribute")
    required: bool = Field(default=False, description="Whether the field is required")
    options: List[str] = Field(default_factory=list, description="Select or radio options")
    visible: bool = Field(default=True, description="Whether the element is visible")
    enabled: bool = Field(default=True, description="Whether the element is enabled")
    current_value: Optional[str] = Field(default=None, description="Current field value")
    context_text: Optional[str] = Field(default=None, description="Nearby textual context")
    selector: Optional[str] = Field(default=None, description="CSS selector or Playwright locator")


class FieldMapping(BaseModel):
    """Mapping between a detected browser field and target candidate/application data."""
    field_id: str
    target_field: str = Field(description="Internal target name (e.g. first_name, email, resume, question_id)")
    classification: FieldClassification = Field(default=FieldClassification.UNKNOWN)
    confidence: MappingConfidence = Field(default=MappingConfidence.UNKNOWN)
    proposed_value: Optional[str] = Field(default=None, description="Value to fill if safe")
    is_safe_to_autofill: bool = Field(default=False)
    requires_user_input: bool = Field(default=False)
    rationale: str = Field(default="")
    evidence_refs: List[str] = Field(default_factory=list)


class BrowserAuditEventType(str, Enum):
    """Audit log event types."""
    SESSION_STARTED = "SESSION_STARTED"
    NAVIGATED = "NAVIGATED"
    PAGE_INSPECTED = "PAGE_INSPECTED"
    FIELD_DETECTED = "FIELD_DETECTED"
    FIELD_MAPPED = "FIELD_MAPPED"
    FIELD_FILLED = "FIELD_FILLED"
    FIELD_SKIPPED = "FIELD_SKIPPED"
    USER_INPUT_REQUESTED = "USER_INPUT_REQUESTED"
    USER_INPUT_PROVIDED = "USER_INPUT_PROVIDED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    REVIEW_STARTED = "REVIEW_STARTED"
    SUBMISSION_CONFIRMED = "SUBMISSION_CONFIRMED"
    SUBMISSION_ATTEMPTED = "SUBMISSION_ATTEMPTED"
    SUBMISSION_SUCCEEDED = "SUBMISSION_SUCCEEDED"
    SUBMISSION_FAILED = "SUBMISSION_FAILED"
    SESSION_PAUSED = "SESSION_PAUSED"
    SESSION_CANCELLED = "SESSION_CANCELLED"


class BrowserAuditEvent(BaseModel):
    """Structured audit trail record."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    event_type: BrowserAuditEventType
    field_id: Optional[str] = None
    action: str = Field(description="Action description")
    result: str = Field(default="SUCCESS", description="SUCCESS, FAILURE, PAUSED, etc.")
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewArtifact(BaseModel):
    """Pre-submission review artifact."""
    job_id: str
    company: str
    role: str
    resume_strategy: str
    resume_path: str
    cover_letter_preview: Optional[str] = None
    fields_total: int = 0
    fields_filled: int = 0
    user_confirmed: int = 0
    unresolved: int = 0
    blocked: int = 0
    validation: str = "PASS"
    ready_to_submit: bool = False
    details: List[Dict[str, Any]] = Field(default_factory=list)


class SubmissionResult(BaseModel):
    """Outcome of form submission."""
    success: bool
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    confirmation_reference: Optional[str] = None
    final_url: Optional[str] = None
    evidence: Optional[str] = None
    error: Optional[str] = None


class BrowserSession(BaseModel):
    """State of an interactive browser application session."""
    session_id: str
    job_id: str
    application_url: str
    status: BrowserSessionStatus = Field(default=BrowserSessionStatus.CREATED)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity_at: datetime = Field(default_factory=datetime.utcnow)
    current_url: Optional[str] = None
    current_step: int = 1
    total_steps: int = 1
    detected_fields: List[BrowserField] = Field(default_factory=list)
    mappings: List[FieldMapping] = Field(default_factory=list)
    filled_fields: Dict[str, Any] = Field(default_factory=dict)
    unresolved_fields: List[str] = Field(default_factory=list)
    blocked_fields: List[str] = Field(default_factory=list)
    user_inputs: Dict[str, Any] = Field(default_factory=dict)
    pause_reason: Optional[str] = None
    review: Optional[ReviewArtifact] = None
    submission_result: Optional[SubmissionResult] = None
    screenshots: List[str] = Field(default_factory=list)
