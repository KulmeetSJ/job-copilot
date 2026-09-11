"""Data models for Phase 9 Continuous Job Copilot."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from job_copilot.tracking.models import ApplicationLifecycleStatus


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class PriorityBand(str, Enum):
    """Deterministic opportunity prioritization bands."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    IGNORE = "IGNORE"


class QueueStatus(str, Enum):
    """Lifecycle status of an opportunity in the Copilot Queue."""
    NEW = "NEW"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    PREPARING = "PREPARING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    SUBMITTED = "SUBMITTED"
    TRACKING = "TRACKING"
    SKIPPED = "SKIPPED"
    ARCHIVED = "ARCHIVED"


class CopilotAction(str, Enum):
    """Suggested next action for the candidate."""
    REVIEW = "REVIEW"
    PREPARE = "PREPARE"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    SUBMIT_PENDING_CONFIRMATION = "SUBMIT_PENDING_CONFIRMATION"
    WAIT = "WAIT"
    SKIP = "SKIP"
    ARCHIVE = "ARCHIVE"


class ClaimType(str, Enum):
    """Classification of candidate qualification claims for truth-safety."""
    PROFESSIONAL_EXPERIENCE = "PROFESSIONAL_EXPERIENCE"
    PERSONAL_PROJECT = "PERSONAL_PROJECT"
    EXPOSURE = "EXPOSURE"
    EDUCATION_OR_CERT = "EDUCATION_OR_CERT"
    UNKNOWN = "UNKNOWN"


class EvidenceReference(BaseModel):
    """Traceable citation to verified canonical candidate evidence."""
    claim_id: str = Field(description="Evidence ID e.g. EXP-HSBC-PAYMENTS-AI-001 or PRJ-AI-TRAVEL-001")
    claim_type: ClaimType = Field(default=ClaimType.PROFESSIONAL_EXPERIENCE)
    description: str = Field(description="Summary of the verified claim")
    source_ref: Optional[str] = Field(default=None, description="Section or bullet citation")


class CopilotExplanation(BaseModel):
    """Transparent explanation of why an opportunity is or is not recommended."""
    why_apply: List[str] = Field(default_factory=list, description="Positive alignment factors with evidence citations")
    why_not_apply: List[str] = Field(default_factory=list, description="Risks, conflicts, or missing evidence")
    uncertainties: List[str] = Field(default_factory=list, description="Unknown aspects (e.g. unknown visa sponsorship)")
    historical_context: Optional[str] = Field(default=None, description="Relevant statistical context from past outcomes")
    evidence_references: List[EvidenceReference] = Field(default_factory=list, description="Direct citations to candidate evidence")


class CopilotRecommendation(BaseModel):
    """Actionable recommendation produced for a specific job."""
    job_id: str
    action: CopilotAction = Field(default=CopilotAction.REVIEW)
    priority_band: PriorityBand = Field(default=PriorityBand.MEDIUM)
    priority_score: float = Field(default=50.0)
    reasons: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    historical_context: Optional[str] = Field(default=None)
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class CopilotJob(BaseModel):
    """
    Consolidated view of a job opportunity managed by Phase 9 Continuous Copilot.
    References underlying Phase 5 job records, Phase 4 assessments, Phase 6 packages,
    Phase 7 browser sessions, and Phase 8 tracking without duplicating storage.
    """
    job_id: str
    title: str
    company: str
    location: Optional[str] = None
    source: str = "unknown"
    canonical_url: Optional[str] = None
    discovered_at: datetime = Field(default_factory=utc_now)

    # Phase 4 Assessment references
    match_score: Optional[float] = None
    recommendation_tier: Optional[str] = None
    selected_strategy: Optional[str] = None

    # Phase 8 Tracking reference
    tracking_application_id: Optional[str] = None
    current_application_status: Optional[ApplicationLifecycleStatus] = None

    # Phase 9 Prioritization & Queue
    queue_status: QueueStatus = Field(default=QueueStatus.NEW)
    priority_score: float = Field(default=50.0)
    priority_band: PriorityBand = Field(default=PriorityBand.MEDIUM)
    effort_estimate: str = Field(default="MEDIUM", description="LOW, MEDIUM, HIGH application effort")
    freshness_days: int = Field(default=0)
    risk_flags: List[str] = Field(default_factory=list)
    user_notes: List[str] = Field(default_factory=list)

    # Explanations and recommendations
    explanation: Optional[CopilotExplanation] = None
    recommendation: Optional[CopilotRecommendation] = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HistoricalInsight(BaseModel):
    """
    Conservative historical insight derived from Phase 8 analytics using a minimum
    sample threshold (N >= 10) for surfacing historical signals.
    Strictly separates empirical FACT from derived INFERENCE and advisory RECOMMENDATION
    without claiming unverified statistical significance.
    """
    topic: str
    fact_statements: List[str] = Field(default_factory=list, description="Empirically observed counts and rates")
    inference_statements: List[str] = Field(default_factory=list, description="Observed patterns and comparative signals")
    recommendation_statements: List[str] = Field(default_factory=list, description="Actionable advisory guidance for candidate")
    sample_size: int
    sample_threshold_met: bool = Field(
        default=False,
        description="True if minimum sample threshold N >= 10 for surfacing historical signals is met",
    )
    is_statistically_reliable: bool = Field(
        default=False,
        description="Backwards-compatible alias: True if minimum sample threshold N >= 10 is met",
    )
    sample_size_warning: Optional[str] = None
    action_required: str = Field(
        default="No configuration change made (human decision required)",
        description="Explicit guarantee of zero automatic system mutation",
    )
    generated_at: datetime = Field(default_factory=utc_now)


class CopilotDashboard(BaseModel):
    """Daily summary view for the candidate."""
    critical_priority_jobs: List[CopilotJob] = Field(default_factory=list)
    high_priority_jobs: List[CopilotJob] = Field(default_factory=list)
    medium_priority_jobs: List[CopilotJob] = Field(default_factory=list)
    low_priority_jobs: List[CopilotJob] = Field(default_factory=list)
    waiting_for_user_jobs: List[CopilotJob] = Field(default_factory=list)
    queue_summary: Dict[str, int] = Field(default_factory=dict)
    recent_outcomes: Dict[str, Any] = Field(default_factory=dict)
    top_historical_insights: List[HistoricalInsight] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)
