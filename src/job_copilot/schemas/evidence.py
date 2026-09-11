"""Pydantic models for structured Resume Evidence and Provenance Tracking."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    """Verification status of an extracted resume claim."""
    CONFIRMED = "CONFIRMED"          # Verifiable factual claim approved by candidate or backed by certificate
    NEEDS_REVIEW = "NEEDS_REVIEW"    # Single-source claim, metric, or positioning phrase needing confirmation
    CONFLICTING = "CONFLICTING"      # Incompatible or differing claims across resumes
    DUPLICATE = "DUPLICATE"          # Duplicate representation of an existing claim
    POSITIONING_ONLY = "POSITIONING_ONLY" # Resume positioning variant, not historical fact


class ClaimType(str, Enum):
    """Classification of the nature of a factual claim."""
    PROFESSIONAL = "PROFESSIONAL"
    PERSONAL_PROJECT = "PERSONAL_PROJECT"
    BENCHMARK = "BENCHMARK"
    ACADEMIC = "ACADEMIC"
    POSITIONING = "POSITIONING"


class MetricType(str, Enum):
    """Classification of quantitative metric claims."""
    PRODUCTION = "PRODUCTION"
    PROJECT = "PROJECT"
    BENCHMARK = "BENCHMARK"
    ESTIMATE = "ESTIMATE"


class FactCategory(str, Enum):
    """Categorization of extracted resume facts."""
    PERSONAL_INFORMATION = "personal_information"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    RESPONSIBILITY = "responsibility"
    ACHIEVEMENT = "achievement"
    METRIC = "metric"
    TECHNOLOGY = "technology"
    PROJECT = "project"
    CERTIFICATION = "certification"
    AWARD = "award"
    DOMAIN_EXPERIENCE = "domain_experience"
    LINK = "link"
    OTHER = "other"


class ResumeEvidenceItem(BaseModel):
    """
    Individual atomic factual claim extracted from a resume.
    Preserves exact provenance (source resume, section, and claim type).
    """
    id: str = Field(description="Unique identifier for the evidence item")
    claim: str = Field(description="Exact or structured text of the claim")
    category: FactCategory = Field(description="Category of the claim")
    claim_type: ClaimType = Field(default=ClaimType.PROFESSIONAL, description="Claim classification")
    metric_type: Optional[MetricType] = Field(default=None, description="Metric classification if applicable")
    source_resumes: List[str] = Field(default_factory=list, description="List of resume filenames containing this claim")
    source_file: Optional[str] = Field(default=None, description="Primary source file")
    source_section: Optional[str] = Field(default=None, description="Section in resume")
    context: Optional[str] = Field(default=None, description="Surrounding sentence / context")
    confidence: str = Field(default="high", description="'high', 'medium', or 'low'")
    status: EvidenceStatus = Field(default=EvidenceStatus.NEEDS_REVIEW, description="Review status")
    raw_metrics: List[str] = Field(default_factory=list, description="Extracted numerical/percentage metrics")
    notes: Optional[str] = Field(default=None, description="Explanation, bounds, or restrictions on use")


class SkillEvidence(BaseModel):
    """
    Structured skill evidence tracking whether a skill is backed by
    professional experience, personal project, or only listed in a skills section.
    """
    skill: str
    category: str
    in_skills_section: bool = True
    in_work_experience: bool = False
    in_projects: bool = False
    source_resumes: List[str] = Field(default_factory=list)
    evidence_contexts: List[str] = Field(default_factory=list)
    experience_level: str = Field(
        default="needs_review",
        description="'professional', 'project_based', 'positioning_only', or 'needs_review'"
    )


class EvidenceReportData(BaseModel):
    """Top-level container for all extracted evidence items and skill matrices."""
    total_resumes_processed: int
    source_files: List[str]
    evidence_items: List[ResumeEvidenceItem]
    skill_evidence: List[SkillEvidence]
