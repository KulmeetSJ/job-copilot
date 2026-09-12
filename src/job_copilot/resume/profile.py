"""Data structures for tailored resumes generated from the Master Profile."""

from typing import List, Optional
from pydantic import BaseModel, Field
from job_copilot.domain.enums import ResumeStrategy
from job_copilot.schemas.candidate import (
    Education,
    Experience,
    PersonalInformation,
    Project,
    SkillCategory,
)


class TailoredResumeData(BaseModel):
    """
    Data payload for a tailored resume targeting a specific job.
    
    SAFETY INVARIANT:
    All entries in this data structure must be strict projections or
    faithful rephrasings of the canonical Master Candidate Profile.
    No fabricated metrics, experiences, or skills are permitted.
    """
    strategy: ResumeStrategy = Field(default=ResumeStrategy.BACKEND_JAVA)
    target_job_title: str = Field(description="Target role for this resume")
    target_company: Optional[str] = Field(default=None, description="Target company if customized")
    personal_info: PersonalInformation
    summary: Optional[str] = Field(default=None, description="Tailored executive summary")
    skills: List[SkillCategory] = Field(default_factory=list, description="Prioritized skill categories")
    experience: List[Experience] = Field(default_factory=list, description="Selected/tailored experience items")
    projects: List[Project] = Field(default_factory=list, description="Selected/tailored projects")
    education: List[Education] = Field(default_factory=list, description="Education records")
