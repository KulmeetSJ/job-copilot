"""Strongly typed domain models for the Resume Tailoring Engine."""

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from job_copilot.schemas.candidate import (
    Award,
    CandidateLink,
    Certification,
    Education,
    PersonalInformation,
)


class JobRequirementType(str, Enum):
    """Categorization of extracted job posting requirements."""
    LANGUAGE = "LANGUAGE"
    FRAMEWORK = "FRAMEWORK"
    CLOUD = "CLOUD"
    DATABASE = "DATABASE"
    TOOL = "TOOL"
    CONCEPT = "CONCEPT"
    YEARS_EXP = "YEARS_EXP"
    DOMAIN = "DOMAIN"
    OTHER = "OTHER"


class JobRequirement(BaseModel):
    """An individual extracted requirement from a job description."""
    name: str = Field(description="Name of skill/requirement (e.g. Java, Terraform)")
    type: JobRequirementType = Field(default=JobRequirementType.TOOL)
    normalized_name: str = Field(description="Normalized canonical name")
    raw_text: Optional[str] = Field(default=None, description="Original sentence / phrase in JD")
    is_required: bool = Field(default=True, description="True if mandatory/required, False if preferred")
    years_required: Optional[float] = Field(default=None, description="Years of experience required if stated")


class JobAnalysis(BaseModel):
    """Structured result of analyzing a raw job description."""
    job_title: Optional[str] = Field(default=None, description="Extracted job title")
    company: Optional[str] = Field(default=None, description="Extracted company name")
    location: Optional[str] = Field(default=None, description="Extracted job location")
    seniority_level: Optional[str] = Field(default=None, description="e.g. Junior, Mid, Senior, Lead, Staff")
    years_experience_requirement: Optional[float] = Field(default=None, description="Overall required years of experience")
    
    required_skills: List[JobRequirement] = Field(default_factory=list)
    preferred_skills: List[JobRequirement] = Field(default_factory=list)
    
    programming_languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    cloud_technologies: List[str] = Field(default_factory=list)
    databases: List[str] = Field(default_factory=list)
    infrastructure_technologies: List[str] = Field(default_factory=list)
    domain_keywords: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    education_requirements: List[str] = Field(default_factory=list)
    certification_requirements: List[str] = Field(default_factory=list)
    ats_keywords: List[str] = Field(default_factory=list)
    dominant_themes: List[str] = Field(
        default_factory=list,
        description="Top 2-3 dominant technical themes of the role (e.g. 'Java/Spring backend development')",
    )


class MatchStatus(str, Enum):
    """Relationship between a job requirement and candidate background."""
    MATCH_CONFIRMED = "MATCH_CONFIRMED"          # Confirmed professional evidence in master profile
    MATCH_PARTIAL = "MATCH_PARTIAL"              # Matches skill but experience/years is below requirement
    MATCH_PROJECT_ONLY = "MATCH_PROJECT_ONLY"    # Evidence exists only in personal/demo projects
    MATCH_POSITIONING_ONLY = "MATCH_POSITIONING_ONLY" # Skill exists only in historical positioning / unverified
    NO_EVIDENCE = "NO_EVIDENCE"                  # Candidate profile has no evidence for this requirement


class RequirementMatch(BaseModel):
    """Evaluation of how a candidate requirement matches a specific JD requirement."""
    requirement: JobRequirement
    match_status: MatchStatus
    candidate_evidence_ids: List[str] = Field(default_factory=list)
    candidate_evidence_text: Optional[str] = Field(default=None)
    candidate_years: Optional[float] = Field(default=None)
    notes: Optional[str] = Field(default=None)


class JobMatchResult(BaseModel):
    """Overall evaluation score and breakdown of candidate match against a job description."""
    overall_score: float = Field(ge=0.0, le=100.0, description="Match fit score from 0.0 to 100.0")
    matches: List[RequirementMatch] = Field(default_factory=list)
    matched_required_count: int = 0
    total_required_count: int = 0
    matched_preferred_count: int = 0
    total_preferred_count: int = 0
    keyword_coverage_pct: float = 0.0
    recommended_strategy: str = "backend_java"
    summary: str = Field(default="")


class ResumeBullet(BaseModel):
    """A factual, evidence-backed bullet point formatted for a resume."""
    text: str = Field(description="Factual sentence formatted for resume")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance IDs in evidence.yaml")
    claim_type: str = Field(default="PROFESSIONAL", description="PROFESSIONAL, PERSONAL_PROJECT, BENCHMARK, ACADEMIC")
    metric_type: Optional[str] = Field(default=None, description="PRODUCTION, PROJECT, BENCHMARK, ESTIMATE")
    relevance_score: float = Field(default=1.0, description="Relevance score for ranking")


class ResumeExperience(BaseModel):
    """Tailored presentation of a professional employment record."""
    company: str
    role: str
    canonical_role: str
    team: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    current: bool = False
    bullets: List[ResumeBullet] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)


class ResumeProject(BaseModel):
    """Tailored presentation of a project record."""
    name: str
    description: str
    architecture: Optional[str] = None
    deployment_status: str = "PORTFOLIO_DEMO"
    bullets: List[ResumeBullet] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    links: List[CandidateLink] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    relevance_score: float = Field(default=1.0)


class ResumeSkillGroup(BaseModel):
    """Categorized skills selected for resume display."""
    category: str
    skills: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    """Strongly typed intermediate representation of a tailored resume ready for rendering."""
    strategy_name: str
    display_title: str
    personal_info: PersonalInformation
    summary: Optional[str] = None
    skill_groups: List[ResumeSkillGroup] = Field(default_factory=list)
    experience: List[ResumeExperience] = Field(default_factory=list)
    projects: List[ResumeProject] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    certifications: List[Certification] = Field(default_factory=list)
    awards: List[Award] = Field(default_factory=list)
    section_order: List[str] = Field(
        default_factory=lambda: [
            "summary",
            "skills",
            "experience",
            "projects",
            "certifications",
            "awards",
            "education",
        ]
    )
    target_job_title: Optional[str] = None
    target_company: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResumeValidationResult(BaseModel):
    """Structured report validating the correctness, truth safety, and rendering of a resume."""
    is_valid: bool = Field(description="True if all structural, content, and truth safety checks pass")
    pdf_generated: bool = False
    page_count: Optional[int] = None
    latex_errors: List[str] = Field(default_factory=list)
    content_errors: List[str] = Field(default_factory=list)
    truth_violations: List[str] = Field(default_factory=list)
    matched_skills: List[str] = Field(default_factory=list)
    unmatched_skills: List[str] = Field(default_factory=list)
    keyword_coverage_pct: float = 0.0
    warnings: List[str] = Field(default_factory=list)


class ResumeGenerationResult(BaseModel):
    """Top-level result of generating a tailored resume."""
    strategy_name: str
    tailored_resume: TailoredResume
    tex_path: Path
    pdf_path: Optional[Path] = None
    validation: ResumeValidationResult
