"""Pydantic schemas for Job domain models and analysis."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from job_copilot.domain.enums import EmploymentType, RemoteStatus, ResumeStrategy


class JobBase(BaseModel):
    """Base fields for a Job."""
    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    location: Optional[str] = Field(default=None, description="Job location")
    remote_status: RemoteStatus = Field(default=RemoteStatus.UNKNOWN, description="Work mode")
    employment_type: EmploymentType = Field(default=EmploymentType.FULL_TIME, description="Employment type")
    url: Optional[str] = Field(default=None, description="URL of the job posting")
    source: Optional[str] = Field(default="manual", description="Source of posting (e.g. greenhouse, linkedin, manual)")
    description: str = Field(description="Full text or markdown of job description")
    requirements: List[str] = Field(default_factory=list, description="Extracted job requirements")
    preferred_qualifications: List[str] = Field(default_factory=list, description="Extracted preferred qualifications")
    technologies: List[str] = Field(default_factory=list, description="Extracted tech stack")
    years_experience: Optional[float] = Field(default=None, description="Required years of experience")
    salary_min: Optional[int] = Field(default=None, description="Minimum salary")
    salary_max: Optional[int] = Field(default=None, description="Maximum salary")
    currency: str = Field(default="USD", description="Salary currency")
    posted_at: Optional[datetime] = Field(default=None, description="When the job was originally posted")


class JobCreate(JobBase):
    """Schema for creating a new job posting."""
    pass


class JobUpdate(BaseModel):
    """Schema for updating an existing job posting."""
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    remote_status: Optional[RemoteStatus] = None
    employment_type: Optional[EmploymentType] = None
    url: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[List[str]] = None
    preferred_qualifications: Optional[List[str]] = None
    technologies: Optional[List[str]] = None
    years_experience: Optional[float] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    posted_at: Optional[datetime] = None


class JobRead(JobBase):
    """Schema for returning job details."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    discovered_at: datetime
    created_at: datetime
    updated_at: datetime


class JobAnalysisResult(BaseModel):
    """Structured result of analyzing a job against candidate profile."""
    job_id: Optional[int] = None
    title: str
    company: str
    match_score: float = Field(
        ge=0.0,
        le=100.0,
        description="Fit score from 0.0 to 100.0"
    )
    matching_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    potential_concerns: List[str] = Field(default_factory=list)
    recommended_strategy: ResumeStrategy = Field(default=ResumeStrategy.BACKEND_JAVA)
    recommendation: str = Field(
        description="'APPLY', 'CONSIDER', or 'SKIP'"
    )
    summary: str = Field(description="Summary of fit analysis")
