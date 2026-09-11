"""Pydantic schemas for Job Application tracking."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from job_copilot.domain.enums import ApplicationStatus, ResumeStrategy
from job_copilot.schemas.job import JobRead


class ApplicationBase(BaseModel):
    """Base fields for an Application."""
    job_id: int = Field(description="Foreign key ID of the job")
    status: ApplicationStatus = Field(
        default=ApplicationStatus.DISCOVERED,
        description="Application status"
    )
    strategy_used: Optional[ResumeStrategy] = Field(
        default=ResumeStrategy.GENERAL_SWE,
        description="Strategy used for tailoring"
    )
    notes: Optional[str] = Field(default=None, description="Personal notes or logs")
    applied_at: Optional[datetime] = Field(default=None, description="Timestamp when submitted")


class ApplicationCreate(ApplicationBase):
    """Schema for creating a new application record."""
    pass


class ApplicationUpdate(BaseModel):
    """Schema for updating an application record."""
    status: Optional[ApplicationStatus] = None
    strategy_used: Optional[ResumeStrategy] = None
    notes: Optional[str] = None
    applied_at: Optional[datetime] = None


class ApplicationRead(ApplicationBase):
    """Schema for reading application details."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    job: Optional[JobRead] = None
