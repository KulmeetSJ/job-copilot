"""Domain models and schemas for Job Discovery, Ingestion, and Lifecycle tracking."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from job_copilot.domain.enums import EmploymentType, RemoteStatus
from job_copilot.matching.models import JobRecommendation


class JobLifecycleStatus(str, Enum):
    """Lifecycle state machine for discovered and ingested jobs."""
    DISCOVERED = "DISCOVERED"      # Discovered from a source feed/search
    INGESTED = "INGESTED"          # Raw content fetched and stored
    NORMALIZED = "NORMALIZED"      # Cleaned and canonicalized
    DUPLICATE = "DUPLICATE"        # Marked as duplicate of another canonical job
    ANALYZED = "ANALYZED"          # Analyzed by Phase 4 analyzer
    MATCHED = "MATCHED"            # Evaluated against candidate truth
    RECOMMENDED = "RECOMMENDED"    # Fit score and recommendation assigned
    ARCHIVED = "ARCHIVED"          # Archived by user
    EXPIRED = "EXPIRED"            # Stale / no longer available on source


class RawJob(BaseModel):
    """Raw unnormalized job record directly from a source."""
    source: str = Field(description="Source identifier e.g. manual, url, feed, greenhouse")
    source_job_id: Optional[str] = Field(default=None, description="Identifier provided by source if present")
    source_url: Optional[str] = Field(default=None, description="Original URL of the job posting")
    company: Optional[str] = Field(default=None, description="Raw company name if provided")
    title: Optional[str] = Field(default=None, description="Raw title if provided")
    location: Optional[str] = Field(default=None, description="Raw location string")
    raw_description: str = Field(description="Raw untouched text or HTML content")
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    source_metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary source-provided metadata")


class CanonicalJob(BaseModel):
    """Normalized pre-analysis canonical job representation."""
    job_id: str = Field(description="Deterministic stable job ID e.g. stripe-senior-backend-java-a1b2c3")
    source: str = Field(description="Source identifier")
    source_job_id: Optional[str] = None
    source_url: Optional[str] = None
    canonical_url: Optional[str] = Field(default=None, description="URL with tracking parameters stripped")
    
    company: str = Field(default="Company unavailable")
    title: str = Field(default="Role unavailable")
    location: Optional[str] = None
    remote_policy: RemoteStatus = Field(default=RemoteStatus.UNKNOWN)
    employment_type: EmploymentType = Field(default=EmploymentType.FULL_TIME)
    
    clean_description: str = Field(description="Cleaned, normalized text content")
    content_hash: str = Field(description="SHA-256 hash of normalized text for deduplication")
    
    lifecycle_status: JobLifecycleStatus = Field(default=JobLifecycleStatus.NORMALIZED)
    duplicate_of: Optional[str] = Field(default=None, description="Canonical job_id if marked as duplicate")
    duplicate_reason: Optional[str] = None
    
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    source_metadata: Dict[str, Any] = Field(default_factory=dict)


class JobIndexEntry(BaseModel):
    """Lightweight index summary for rapid querying, ranking, and status lookup."""
    job_id: str
    source: str
    source_url: Optional[str] = None
    company: str
    title: str
    location: Optional[str] = None
    remote_policy: str = "UNKNOWN"
    lifecycle_status: str = "NORMALIZED"
    duplicate_of: Optional[str] = None
    
    # Phase 4 evaluation data (populated when evaluated)
    overall_fit_score: Optional[float] = None
    recommendation: Optional[str] = None
    recommended_strategy: Optional[str] = None
    
    discovered_at: str
    updated_at: str


class DiscoveryQuery(BaseModel):
    """Structured query parameters for discovering job opportunities."""
    keywords: List[str] = Field(default_factory=list, description="Target job titles / keywords")
    locations: List[str] = Field(default_factory=list, description="Target locations e.g. Pune, Remote")
    strategies: List[str] = Field(default_factory=list, description="Target resume strategies")
    domains: List[str] = Field(default_factory=list, description="Target industry domains")
    min_years: Optional[float] = Field(default=None, description="Minimum experience requirement")
    max_years: Optional[float] = Field(default=None, description="Maximum experience requirement")
    remote_preferred: bool = Field(default=True, description="Whether remote/hybrid roles are preferred")
    limit_per_source: int = Field(default=20, ge=1, le=100)


class DiscoveryResult(BaseModel):
    """Summary result of a discovery run across one or multiple sources."""
    query: DiscoveryQuery
    jobs_discovered: int = 0
    jobs_new: int = 0
    jobs_updated: int = 0
    duplicates_found: int = 0
    failed_sources: Dict[str, str] = Field(default_factory=dict)
    jobs: List[CanonicalJob] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=datetime.utcnow)
