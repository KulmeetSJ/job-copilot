"""Pydantic schemas for Phase 11 Human Review Dashboard & Control Center."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from job_copilot.copilot.models import (
    ClaimType,
    CopilotAction,
    EvidenceReference,
    PriorityBand,
    QueueStatus,
)
from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus, BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus, EmploymentType, RemoteStatus, ResumeStrategy
from job_copilot.matching.models import JobRecommendation, MatchClassification


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


# ==============================================================================
# Overview & Summary Models
# ==============================================================================

class PipelineCounts(BaseModel):
    """Counts of applications across key lifecycle stages."""
    discovered: int = 0
    recommended: int = 0
    prepared: int = 0
    ready_for_review: int = 0
    needs_user_input: int = 0
    awaiting_confirmation: int = 0
    submitted: int = 0
    recruiter_response: int = 0
    interview: int = 0
    offer: int = 0
    rejected: int = 0
    withdrawn: int = 0


class QueueCounts(BaseModel):
    """Opportunity counts by priority band."""
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    total_active: int = 0


class DashboardOverviewResponse(BaseModel):
    """Consolidated summary for the main Dashboard Control Center."""
    queue_counts: QueueCounts
    pipeline_counts: PipelineCounts
    recent_submissions_count: int = 0
    active_sources_count: int = 0
    healthy_sources_count: int = 0
    authenticated_sessions_count: int = 0
    recent_activity: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)


# ==============================================================================
# Priority Queue Models
# ==============================================================================

class DashboardQueueItem(BaseModel):
    """A prioritized job opportunity card for the queue view."""
    job_id: str
    company: str
    title: str
    location: Optional[str] = None
    remote_status: Optional[str] = None
    source: str = "unknown"
    canonical_url: Optional[str] = None
    match_score: Optional[float] = None
    recommendation: Optional[str] = None
    priority_band: PriorityBand = PriorityBand.MEDIUM
    priority_score: float = 50.0
    queue_status: QueueStatus = QueueStatus.NEW
    freshness_days: int = 0
    key_matched_skills: List[str] = Field(default_factory=list)
    major_gaps: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    primary_reason: Optional[str] = None
    selected_strategy: Optional[str] = None
    tracking_application_id: Optional[str] = None
    application_status: Optional[str] = None
    discovered_at: datetime = Field(default_factory=utc_now)


class DashboardQueueResponse(BaseModel):
    """Paginated or filtered response for the priority queue."""
    items: List[DashboardQueueItem]
    total_count: int
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0


# ==============================================================================
# Job Detail & Match Explanation Models
# ==============================================================================

class MatchDimensionScore(BaseModel):
    """Detailed score and weight for one of the 7 match dimensions."""
    dimension_name: str
    score: float
    weight: float
    description: str


class RequirementMatchDetail(BaseModel):
    """Classification, confidence, and provenance for an individual requirement."""
    requirement_name: str
    normalized_name: str
    category: str
    importance: str
    is_must_have: bool
    classification: MatchClassification
    confidence: float
    evidence_ids: List[str] = Field(default_factory=list)
    evidence_text: Optional[str] = None
    reason: str


class ExplanationSection(BaseModel):
    """Explicitly separated Fact vs Inference vs Recommendation model."""
    facts: List[str] = Field(default_factory=list, description="Ground truth verified candidate experience/qualifications")
    inferences: List[str] = Field(default_factory=list, description="Derived match assessments and alignment signals")
    recommendations: List[str] = Field(default_factory=list, description="Advisory action recommendations for the user")


class JobDetailResponse(BaseModel):
    """Complete detail and evidence-backed match explanation for a job."""
    job_id: str
    title: str
    company: str
    location: Optional[str] = None
    source: str = "unknown"
    url: Optional[str] = None
    remote_status: Optional[str] = None
    employment_type: Optional[str] = None
    discovered_at: datetime
    lifecycle_status: str
    description: str
    requirements: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: str = "USD"
    
    # 7-Dimensional Score Breakdown
    match_score: float
    priority_score: float
    priority_band: str
    recommendation: str
    dimension_scores: List[MatchDimensionScore] = Field(default_factory=list)
    
    # Evidence Provenance
    requirement_matches: List[RequirementMatchDetail] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    partial_matches: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    
    # Structured Explanation
    explanation: ExplanationSection
    recommended_strategy: str
    strategy_reasoning: str
    alternative_strategies: List[str] = Field(default_factory=list)


# ==============================================================================
# Application Review & Artifact Models
# ==============================================================================

class PreparedAnswerItem(BaseModel):
    """An answered application question."""
    question_text: str
    field_name: Optional[str] = None
    field_category: str
    answer_text: str
    confidence: float
    source_evidence: List[str] = Field(default_factory=list)
    requires_user_input: bool = False
    validation_status: str = "VALID"


class UserInputRequiredItem(BaseModel):
    """A field requiring explicit human input."""
    question_id: str
    question_text: str
    field_type: str = "text"
    current_value: Optional[Any] = None
    reason_required: str
    options: Optional[List[str]] = None
    is_sensitive: bool = True


class ArtifactSummaryItem(BaseModel):
    """Metadata summary of an application artifact (Phase 10A)."""
    artifact_id: str
    artifact_type: str
    original_filename: Optional[str] = None
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    created_at: datetime
    download_url: Optional[str] = None


class BrowserReviewSummary(BaseModel):
    """Browser worker execution and review package summary."""
    task_id: Optional[str] = None
    source: str = "unknown"
    target_url: Optional[str] = None
    status: str = "NOT_STARTED"
    fields_detected_count: int = 0
    fields_filled_count: int = 0
    fields_requiring_input_count: int = 0
    has_screenshot: bool = False
    screenshot_artifact_id: Optional[str] = None
    has_confirmation_token: bool = False
    confirmation_token: Optional[str] = None
    is_ready_for_review: bool = False
    pause_reason: Optional[str] = None
    failure_reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    blocker_type: Optional[str] = None
    blocker_instruction: Optional[str] = None
    can_resume: bool = False
    is_external_unverified: bool = False


class ApplicationTimelineEvent(BaseModel):
    """Append-only lifecycle event item (Phase 8)."""
    event_id: str
    event_type: str
    timestamp: datetime
    source: str
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ApplicationDetailResponse(BaseModel):
    """Full application review data for human inspection."""
    application_id: str
    job_id: str
    company: str
    role: str
    source: str
    canonical_job_url: Optional[str] = None
    status: str
    match_score: Optional[float] = None
    recommendation: Optional[str] = None
    selected_strategy: str
    resume_pdf_path: Optional[str] = None
    resume_tex_content: Optional[str] = None
    cover_letter_text: Optional[str] = None
    cover_letter_subject: Optional[str] = None
    cover_letter_valid: bool = True
    prepared_answers: List[PreparedAnswerItem] = Field(default_factory=list)
    user_inputs_required: List[UserInputRequiredItem] = Field(default_factory=list)
    artifacts: List[ArtifactSummaryItem] = Field(default_factory=list)
    browser_review: Optional[BrowserReviewSummary] = None
    timeline: List[ApplicationTimelineEvent] = Field(default_factory=list)
    user_notes: List[str] = Field(default_factory=list)
    discovered_at: Optional[datetime] = None
    prepared_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    blocker_type: Optional[str] = None
    blocker_instruction: Optional[str] = None
    can_resume: bool = False
    is_external_unverified: bool = False



# ==============================================================================
# Human Input & Confirmation Payloads
# ==============================================================================

class HumanInputAnswerItem(BaseModel):
    """An answer supplied by the human operator for a sensitive question."""
    question_id: str
    question_text: str
    answer_value: Any


class HumanInputSubmitRequest(BaseModel):
    """Submission of human answers for unresolved application questions."""
    answers: List[HumanInputAnswerItem]


class PrepareApplicationPayload(BaseModel):
    """Request to prepare an application with an optional strategy override."""
    strategy_override: Optional[str] = None


class SkipApplicationPayload(BaseModel):
    """Request to skip an opportunity with an optional reason."""
    reason: Optional[str] = None


class SubmissionConfirmPayload(BaseModel):
    """
    Explicit submission confirmation payload.
    Must contain confirm_text='SUBMIT' and valid confirmation_token.
    """
    task_id: str = Field(..., description="Browser task ID to confirm")
    confirmation_token: str = Field(..., description="Active unexpired confirmation token")
    confirm_text: str = Field(..., description="Mandatory confirmation keyword. Must match 'SUBMIT'.")
    user_notes: Optional[str] = Field(default=None, description="Optional user submission notes")


class SubmissionConfirmResponse(BaseModel):
    """Response returned upon validated submission confirmation."""
    success: bool
    application_id: Optional[str] = None
    task_id: str
    status: str
    submission_reference: Optional[str] = None
    submitted_at: Optional[datetime] = None
    message: str


# ==============================================================================
# Source & Session Monitoring Models
# ==============================================================================

class SourceMonitoringItem(BaseModel):
    """Monitoring and health metadata for a configured job source."""
    source_name: str
    display_name: str
    enabled: bool
    discovery_mode: str
    health_status: str
    last_run_at: Optional[datetime] = None
    last_error: Optional[str] = None
    requires_login: bool = False
    has_active_session: bool = False
    session_status: Optional[str] = None


class SessionMetadataItem(BaseModel):
    """Safe metadata representation of an authenticated source session (Zero secrets)."""
    id: int
    session_id: str
    source: str
    status: AuthenticatedSessionStatus
    has_stored_state: bool
    created_at: datetime
    last_verified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


# ==============================================================================
# User-Submitted Opportunity Models
# ==============================================================================

class AnalyzeOpportunityRequest(BaseModel):
    """Request payload for user-submitted opportunity analysis."""
    url: str = Field(..., description="Public job posting URL to ingest and analyze")


class AnalyzeOpportunityResponse(BaseModel):
    """Structured response from user-submitted opportunity pipeline."""
    job_id: str
    application_id: Optional[str] = None
    company: str
    title: str
    location: Optional[str] = None
    canonical_url: str
    source: str = "user_submitted_url"
    match_score: float
    recommendation: str
    priority_band: str
    priority_score: float
    selected_strategy: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of_id: Optional[str] = None
    status: str = "READY_FOR_REVIEW"
    resume_download_url: Optional[str] = None
    supports_browser_prep: bool = False
    has_active_session: bool = False
    needs_user_input_count: int = 0
    message: str = "Opportunity successfully analyzed and prepared for review."

