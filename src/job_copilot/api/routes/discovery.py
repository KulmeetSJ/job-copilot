"""FastAPI routes for Phase 5 Job Discovery & Ingestion."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from job_copilot.ingestion.models import CanonicalJob, DiscoveryQuery, DiscoveryResult, JobIndexEntry
from job_copilot.matching.models import JobAssessment
from job_copilot.services.discovery_service import DiscoveryService

router = APIRouter(prefix="/api/jobs", tags=["Job Discovery & Ingestion"])

service = DiscoveryService()


class IngestTextRequest(BaseModel):
    """Payload for ingesting raw job text."""
    job_description: str = Field(description="Raw text or HTML of the job description")
    company: Optional[str] = None
    title: Optional[str] = None
    location: Optional[str] = None
    source_url: Optional[str] = None
    source_job_id: Optional[str] = None


class IngestUrlRequest(BaseModel):
    """Payload for ingesting a public job posting URL."""
    url: str = Field(description="Public URL of job posting")


@router.post("/ingest", response_model=CanonicalJob, summary="Ingest raw job description text")
def ingest_text_job(req: IngestTextRequest) -> CanonicalJob:
    """Normalize, deduplicate, and persist a raw job description."""
    if not req.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description text cannot be empty.")
    return service.ingest_text(
        text=req.job_description,
        company=req.company,
        title=req.title,
        location=req.location,
        source_url=req.source_url,
        source_job_id=req.source_job_id,
    )


@router.post("/ingest-url", response_model=CanonicalJob, summary="Ingest job from a public URL")
def ingest_url_job(req: IngestUrlRequest) -> CanonicalJob:
    """Fetch permitted public URL, normalize, deduplicate, and persist."""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty.")
    job = service.ingest_url(req.url.strip())
    if not job:
        raise HTTPException(status_code=400, detail=f"Failed to fetch job content from URL: {req.url}")
    return job


@router.post("/discover", response_model=DiscoveryResult, summary="Discover jobs matching query")
def discover_jobs(query: Optional[DiscoveryQuery] = None) -> DiscoveryResult:
    """Run discovery across configured feeds/sources using preferences or explicit query."""
    return service.discover_jobs(query=query)


@router.get("", response_model=List[JobIndexEntry], summary="List and filter indexed jobs")
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by lifecycle status"),
    min_score: Optional[float] = Query(None, description="Minimum overall fit score"),
    recommendation: Optional[str] = Query(None, description="Filter by recommendation tier"),
    strategy: Optional[str] = Query(None, description="Filter by resume strategy"),
    ranked: bool = Query(True, description="Whether to sort by Phase 4 fit score ranking"),
    include_duplicates: bool = Query(False, description="Whether to include duplicate jobs"),
) -> List[JobIndexEntry]:
    """Retrieve indexed jobs with optional filtering and ranking."""
    if ranked:
        jobs = service.rank_jobs(include_duplicates=include_duplicates)
        if status or min_score is not None or recommendation or strategy:
            jobs = [
                j for j in jobs
                if (not status or j.lifecycle_status.upper() == status.upper())
                and (min_score is None or (j.overall_fit_score is not None and j.overall_fit_score >= min_score))
                and (not recommendation or j.recommendation == recommendation.upper())
                and (not strategy or j.recommended_strategy == strategy)
            ]
        return jobs
    return service.list_jobs(
        status=status,
        min_score=min_score,
        recommendation=recommendation,
        strategy=strategy,
        include_duplicates=include_duplicates,
    )


@router.get("/{job_id}", response_model=CanonicalJob, summary="Get canonical job details")
def get_job(job_id: str) -> CanonicalJob:
    """Retrieve full canonical job details by ID."""
    job = service.store.get_canonical_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


@router.post("/{job_id}/process", response_model=JobAssessment, summary="Process stored job with Phase 4 Intelligence")
def process_stored_job(job_id: str) -> JobAssessment:
    """Evaluate a stored job through Phase 4 and update index with score and recommendation."""
    assessment = service.process_job(job_id)
    if not assessment:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return assessment
