"""Pydantic schemas for the Canonical Candidate Profile (Master Source of Truth)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CandidateLink(BaseModel):
    """External link associated with a candidate (LinkedIn, GitHub, Portfolio, LeetCode, etc.)."""
    label: str = Field(description="Label for the link (e.g., LinkedIn, GitHub, Portfolio, LeetCode)")
    url: Optional[str] = Field(default=None, description="Target URL (null if unconfirmed)")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance evidence IDs")


class PersonalInformation(BaseModel):
    """Personal contact and identification details."""
    full_name: str = Field(description="Candidate's full legal name")
    email: str = Field(description="Primary contact email")
    phone: Optional[str] = Field(default=None, description="Primary contact phone number")
    location: str = Field(description="Current primary city, state/country")
    headline: Optional[str] = Field(default=None, description="Short professional headline")
    summary: Optional[str] = Field(default=None, description="Brief professional summary")
    links: List[CandidateLink] = Field(default_factory=list, description="List of profile links")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance evidence IDs")


class WorkAuthorization(BaseModel):
    """Work authorization and visa sponsorship status."""
    current_country: Optional[str] = Field(default="India", description="Country of residence / primary authorization")
    current_work_authorization: Optional[str] = Field(default=None, description="Current legal working status (requires confirmation)")
    international_sponsorship_required: Optional[bool] = Field(default=None, description="Whether future visa sponsorship is required for international roles")
    notes: Optional[str] = Field(default=None, description="Additional context on work authorization")


class Education(BaseModel):
    """Formal education record."""
    institution: str = Field(description="University or institution name")
    degree: str = Field(description="Degree obtained or pursued (e.g., B.Tech, Class 12th)")
    field_of_study: str = Field(description="Major or area of study")
    location: Optional[str] = Field(default=None, description="City, State/Country of institution")
    start_date: Optional[str] = Field(default=None, description="Start date (YYYY-MM or YYYY)")
    end_date: Optional[str] = Field(default=None, description="End date / graduation date (YYYY-MM, YYYY, or 'Present')")
    gpa: Optional[str] = Field(default=None, description="GPA or grade score if relevant")
    coursework: List[str] = Field(default_factory=list, description="Relevant coursework")
    honors: List[str] = Field(default_factory=list, description="Academic honors or awards")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance evidence IDs")


class Achievement(BaseModel):
    """Granular achievement or impact claim."""
    description: str = Field(description="Factual statement of achievement directly stated in source")
    claim_type: str = Field(default="PROFESSIONAL", description="PROFESSIONAL, PERSONAL_PROJECT, BENCHMARK, ACADEMIC")
    metrics: List[str] = Field(default_factory=list, description="Extracted numerical/percentage metrics")
    technologies: List[str] = Field(default_factory=list, description="Specific technologies used")
    impact: Optional[str] = Field(default=None, description="Business or engineering outcome stated in source")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance evidence IDs")


class Experience(BaseModel):
    """Professional work experience record."""
    company: str = Field(description="Company or organization name")
    role: Optional[str] = Field(default="Software Engineer", description="Canonical job title")
    canonical_role: Optional[str] = Field(default="Software Engineer", description="Official corporate/HR job title")
    historical_titles: List[str] = Field(
        default_factory=list,
        description="Exact titles appearing in supplied historical resumes (positioning variants)"
    )
    team: Optional[str] = Field(default=None, description="Specific team or platform")
    location: Optional[str] = Field(default=None, description="Job location")
    remote_status: Optional[str] = Field(default=None, description="Work mode if stated")
    start_date: Optional[str] = Field(default=None, description="Start date (YYYY-MM)")
    end_date: Optional[str] = Field(default=None, description="End date (YYYY-MM or 'Present')")
    current: bool = Field(default=False, description="Whether this is the current job")
    description: Optional[str] = Field(default=None, description="Summary of role context directly from source")
    domain: Optional[str] = Field(default=None, description="Industry domain")
    technologies: List[str] = Field(default_factory=list, description="Technologies utilized")
    responsibilities: List[str] = Field(default_factory=list, description="Directly stated responsibilities")
    achievements: List[Achievement] = Field(default_factory=list, description="Directly stated achievements")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance evidence IDs")


class Project(BaseModel):
    """Personal, open-source, or academic project."""
    name: str = Field(description="Project name")
    description: str = Field(description="Overview of the project from source")
    claim_type: str = Field(default="PERSONAL_PROJECT", description="PERSONAL_PROJECT, BENCHMARK, ACADEMIC")
    technologies: List[str] = Field(default_factory=list, description="Technologies used")
    architecture: Optional[str] = Field(default=None, description="Architectural pattern directly stated")
    deployment_status: Optional[str] = Field(default="PORTFOLIO_DEMO", description="Deployment status (PORTFOLIO_DEMO, PRODUCTION, UNKNOWN)")
    responsibilities: List[str] = Field(default_factory=list, description="Directly stated contributions")
    achievements: List[Achievement] = Field(default_factory=list, description="Directly stated achievements")
    metrics: List[str] = Field(default_factory=list, description="Key metrics claimed")
    links: List[CandidateLink] = Field(default_factory=list, description="Project links")
    start_date: Optional[str] = Field(default=None, description="Start date (null if unknown)")
    end_date: Optional[str] = Field(default=None, description="End date (null if unknown)")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance evidence IDs")


class SkillEvidenceItem(BaseModel):
    """Evidence occurrence for a specific skill."""
    type: str = Field(description="'professional', 'project', or 'skills_section'")
    source_file: str = Field(description="Resume source filename")
    source_section: Optional[str] = Field(default=None, description="Resume section")
    context: str = Field(description="Sentence or bullet where skill is evidenced")
    evidence_id: Optional[str] = Field(default=None, description="Linked fact ID in evidence.yaml")


class SkillItem(BaseModel):
    """A specific skill with provenance evidence and verification status."""
    name: str = Field(description="Skill name (e.g. Java, Terraform, Kubernetes)")
    status: str = Field(
        default="NEEDS_REVIEW",
        description="'CONFIRMED', 'NEEDS_REVIEW', 'POSITIONING_ONLY', or 'UNKNOWN'"
    )
    evidence: List[SkillEvidenceItem] = Field(default_factory=list, description="Evidence references")


class SkillCategory(BaseModel):
    """Grouped category of technical skills."""
    category: str = Field(description="Category name (e.g. Languages, Cloud & Infrastructure)")
    skills: List[SkillItem] = Field(default_factory=list, description="List of skills in category")


class Certification(BaseModel):
    """Professional certification or license."""
    name: str = Field(description="Certification name")
    issuer: str = Field(description="Issuing organization")
    issue_date: Optional[str] = Field(default=None, description="Issue date (null if unconfirmed)")
    expiration_date: Optional[str] = Field(default=None, description="Expiration date (null if unconfirmed)")
    credential_id: Optional[str] = Field(default=None, description="Verification ID (null if unconfirmed)")
    credential_url: Optional[str] = Field(default=None, description="Verification URL (null if unconfirmed)")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance evidence IDs")


class Award(BaseModel):
    """Honors, awards, and competition recognitions."""
    title: str = Field(description="Award title")
    issuer: str = Field(description="Issuing entity / organization")
    date: Optional[str] = Field(default=None, description="Date or Quarter")
    description: Optional[str] = Field(default=None, description="Details or recognition context")
    verified_document: Optional[str] = Field(default=None, description="Filename of verifying certificate")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance evidence IDs")


class DomainExperience(BaseModel):
    """Industry domain expertise."""
    domain: str = Field(description="Domain name")
    highlights: List[str] = Field(default_factory=list, description="Key domain concepts applied")
    evidence_ids: List[str] = Field(default_factory=list, description="Provenance evidence IDs")


from datetime import datetime, timezone


def calculate_verified_experience_years(profile: Optional['CandidateProfile']) -> Optional[float]:
    """
    Calculate verified professional experience years directly from canonical employment records.
    Returns None if no verified employment records with dates are found.
    """
    if not profile or not profile.employment:
        return None

    total_months = 0
    now = datetime.now(timezone.utc)
    for exp in profile.employment:
        if not exp.start_date:
            continue
        try:
            parts = exp.start_date.split("-")
            start_year = int(parts[0])
            start_month = int(parts[1]) if len(parts) > 1 else 1

            if exp.current or not exp.end_date or str(exp.end_date).lower() == "present":
                end_year = now.year
                end_month = now.month
            else:
                end_parts = exp.end_date.split("-")
                end_year = int(end_parts[0])
                end_month = int(end_parts[1]) if len(end_parts) > 1 else 12

            months = max(1, (end_year - start_year) * 12 + (end_month - start_month))
            total_months += months
        except (ValueError, IndexError):
            continue

    if total_months <= 0:
        return None
    return round(total_months / 12.0, 1)


class CandidateProfile(BaseModel):
    """
    Canonical Master Candidate Profile.
    Contains strictly factual, evidence-backed candidate data.
    """
    version: str = Field(default="1.0.0", description="Profile schema version")
    last_updated: Optional[str] = Field(default=None, description="Last update timestamp")
    personal_info: PersonalInformation = Field(description="Personal contact details")
    work_authorization: WorkAuthorization = Field(
        default_factory=WorkAuthorization,
        description="Work authorization info"
    )
    education: List[Education] = Field(default_factory=list, description="Education history")
    employment: List[Experience] = Field(default_factory=list, description="Work experience history")
    projects: List[Project] = Field(default_factory=list, description="Projects")
    skills: List[SkillCategory] = Field(default_factory=list, description="Categorized technical skills with evidence")
    certifications: List[Certification] = Field(default_factory=list, description="Certifications")
    awards: List[Award] = Field(default_factory=list, description="Awards and recognitions")
    domain_experience: List[DomainExperience] = Field(default_factory=list, description="Industry domain depth")

    @property
    def experience(self) -> List[Experience]:
        """Backward compatibility alias for employment."""
        return self.employment

    @property
    def verified_experience_years(self) -> Optional[float]:
        """Derived verified professional experience duration in years."""
        return calculate_verified_experience_years(self)
