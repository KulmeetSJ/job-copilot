"""Strongly typed domain models for the Job Intelligence & Matching Engine."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from job_copilot.domain.enums import EmploymentType, RemoteStatus


class RequirementImportance(str, Enum):
    """Importance level of an extracted job requirement."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MatchClassification(str, Enum):
    """Deterministic classification of how candidate background satisfies a job requirement."""
    MATCH_CONFIRMED = "MATCH_CONFIRMED"          # Confirmed professional production experience
    MATCH_PROJECT_ONLY = "MATCH_PROJECT_ONLY"    # Evidence exists solely in personal/portfolio project
    MATCH_EXPOSURE_ONLY = "MATCH_EXPOSURE_ONLY"  # Confirmed training and hands-on exposure (e.g. GKE, Helm, ADK)
    MATCH_POSITIONING_ONLY = "MATCH_POSITIONING_ONLY" # Positioning/preferences indicate relevance; unverified
    PARTIAL_MATCH = "PARTIAL_MATCH"              # Partial satisfaction (e.g. experience years mismatch or compound requirement)
    NO_EVIDENCE = "NO_EVIDENCE"                  # No factual candidate evidence or positioning support
    CONFLICT = "CONFLICT"                        # Explicit contradiction with candidate profile/preferences


class JobSeniority(str, Enum):
    """Seniority tier indicated by job description."""
    INTERN = "INTERN"
    JUNIOR = "JUNIOR"
    ENTRY_LEVEL = "ENTRY_LEVEL"
    MID_LEVEL = "MID_LEVEL"
    SENIOR = "SENIOR"
    STAFF = "STAFF"
    PRINCIPAL = "PRINCIPAL"
    LEAD = "LEAD"


class WorkAuthorizationRequirement(str, Enum):
    """Work authorization / sponsorship status parsed from job posting."""
    REQUIRED = "REQUIRED"
    SPONSORSHIP_AVAILABLE = "SPONSORSHIP_AVAILABLE"
    SPONSORSHIP_UNKNOWN = "SPONSORSHIP_UNKNOWN"
    CITIZEN_ONLY = "CITIZEN_ONLY"


class TechnicalRequirement(BaseModel):
    """An individual technical requirement parsed from a job posting."""
    name: str = Field(description="Name of technical skill as parsed")
    normalized_name: str = Field(description="Canonical normalized skill name")
    category: str = Field(default="Tool", description="Language, Framework, Cloud, Database, Tool, Concept")
    importance: RequirementImportance = Field(default=RequirementImportance.HIGH)
    is_must_have: bool = Field(default=True, description="True if mandatory/must-have, False if preferred")
    years_required: Optional[float] = Field(default=None, description="Years of experience required if stated")
    raw_snippet: Optional[str] = Field(default=None, description="Context sentence in JD")


class AnalyzedJob(BaseModel):
    """Canonical structured representation of an analyzed job posting."""
    job_id: str = Field(description="Deterministic unique ID e.g. company-title-hash")
    source: str = Field(default="text_input", description="file, text_input, pasted, url")
    source_url: Optional[str] = None
    company: str = Field(default="Target Company")
    title: str = Field(default="Software Engineer")
    location: Optional[str] = None
    remote_policy: RemoteStatus = Field(default=RemoteStatus.UNKNOWN)
    employment_type: EmploymentType = Field(default=EmploymentType.FULL_TIME)
    seniority: JobSeniority = Field(default=JobSeniority.MID_LEVEL)
    years_experience_required: Optional[float] = None
    description: str = Field(description="Full text of the job description")
    
    technical_requirements: List[TechnicalRequirement] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    domain_requirements: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    education_requirements: List[str] = Field(default_factory=list)
    work_authorization: WorkAuthorizationRequirement = Field(default=WorkAuthorizationRequirement.SPONSORSHIP_UNKNOWN)
    
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: str = "USD"
    
    ats_keywords: List[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    analyzer_version: str = "1.0.0"


class RequirementMatchResult(BaseModel):
    """Evaluation of how candidate evidence satisfies a single requirement."""
    requirement: TechnicalRequirement
    classification: MatchClassification
    candidate_evidence_ids: List[str] = Field(default_factory=list)
    candidate_evidence_text: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    reason: str = Field(description="Human-readable explainability string")


class FitScoreBreakdown(BaseModel):
    """Multi-dimensional breakdown of fit score across 7 distinct evaluation dimensions."""
    technical_score: float = Field(ge=0.0, le=100.0, description="Score based on mandatory & preferred technical skills")
    responsibility_score: float = Field(ge=0.0, le=100.0, description="Score based on matching responsibilities")
    role_score: float = Field(ge=0.0, le=100.0, description="Score based on role & seniority alignment")
    experience_score: float = Field(ge=0.0, le=100.0, description="Score based on confirmed professional evidence depth")
    domain_score: float = Field(ge=0.0, le=100.0, description="Score based on domain overlap e.g. Fintech/Payments")
    preference_score: float = Field(ge=0.0, le=100.0, description="Score based on location & work mode preferences")
    credential_score: float = Field(ge=0.0, le=100.0, description="Score based on education & certification overlap")
    overall_score: float = Field(ge=0.0, le=100.0, description="Weighted composite fit score")


class JobRecommendation(str, Enum):
    """Application recommendation tier."""
    STRONG_APPLY = "STRONG_APPLY"   # High score, strong core match, minimal risk
    APPLY = "APPLY"                 # Good fit, solid evidence foundation
    REVIEW = "REVIEW"               # Partial match or important unknowns/gaps to evaluate
    LOW_PRIORITY = "LOW_PRIORITY"   # Moderate mismatch or significant requirement gaps
    SKIP = "SKIP"                   # Poor match, major contradictions, or unrelated role


class JobAssessment(BaseModel):
    """Complete structured assessment of candidate match against a job posting."""
    job: AnalyzedJob
    match_results: List[RequirementMatchResult] = Field(default_factory=list)
    score_breakdown: FitScoreBreakdown
    recommendation: JobRecommendation
    
    strengths: List[str] = Field(default_factory=list, description="Key candidate strengths for this role")
    partial_matches: List[str] = Field(default_factory=list, description="Requirements with project/exposure support")
    gaps: List[str] = Field(default_factory=list, description="Missing or unconfirmed requirements")
    risks: List[str] = Field(default_factory=list, description="Potential risks (seniority, visa, depth)")
    
    recommended_strategy: str = Field(description="Recommended Phase 3 resume strategy")
    alternative_strategies: List[str] = Field(default_factory=list)
    strategy_reasoning: str = Field(description="Justification for selected resume strategy")
    
    human_report: str = Field(description="Human-readable formatted job assessment report")
    created_at: datetime = Field(default_factory=datetime.utcnow)
