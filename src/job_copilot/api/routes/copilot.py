"""REST API endpoints for Phase 9 Continuous Job Copilot."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from job_copilot.copilot.models import (
    CopilotDashboard,
    CopilotJob,
    CopilotRecommendation,
    HistoricalInsight,
    PriorityBand,
    QueueStatus,
)
from job_copilot.services.copilot_service import CopilotService

router = APIRouter(prefix="/api/copilot", tags=["Continuous Copilot"])

# Singleton service instance
_service: Optional[CopilotService] = None


def get_copilot_service() -> CopilotService:
    global _service
    if _service is None:
        _service = CopilotService()
    return _service


class DiscoverRequest(BaseModel):
    keywords: Optional[List[str]] = None
    locations: Optional[List[str]] = None


class ProcessJobRequest(BaseModel):
    job_id: Optional[str] = None


class PrepareJobRequest(BaseModel):
    strategy_override: Optional[str] = None


class SkipJobRequest(BaseModel):
    reason: Optional[str] = None


class ApplyJobRequest(BaseModel):
    confirmation_token: Optional[str] = Field(
        default=None,
        description="Explicit human confirmation token from Phase 7 review",
    )
    headless: bool = True


@router.get("/dashboard", response_model=CopilotDashboard)
def get_daily_dashboard():
    """Get the prioritized daily Copilot dashboard and recent outcome metrics."""
    service = get_copilot_service()
    return service.get_dashboard()


@router.get("/queue", response_model=List[CopilotJob])
def get_copilot_queue(
    status: Optional[QueueStatus] = Query(None, description="Filter by queue status"),
    priority: Optional[PriorityBand] = Query(None, description="Filter by priority band"),
    min_score: Optional[float] = Query(None, description="Filter by minimum priority score"),
):
    """List opportunities from the prioritized Copilot queue."""
    service = get_copilot_service()
    return service.get_queue(status=status, priority_band=priority, min_priority_score=min_score)


@router.get("/recommendations", response_model=List[CopilotRecommendation])
def list_recommendations():
    """Get all active recommendations for queued opportunities."""
    service = get_copilot_service()
    jobs = service.get_queue()
    return [j.recommendation for j in jobs if j.recommendation is not None]


@router.get("/insights", response_model=List[HistoricalInsight])
def get_historical_insights():
    """Get conservative, sample-safe historical outcome insights."""
    service = get_copilot_service()
    return service.get_insights()


@router.get("/targets")
def get_target_configuration():
    """Get candidate company targets, job families, skills, and locations."""
    service = get_copilot_service()
    return service.get_targets().model_dump()


@router.get("/sources")
def list_job_sources(
    enabled_only: bool = Query(False, description="Filter for enabled sources only")
):
    """List all configured career sources, discovery modes, and check intervals."""
    service = get_copilot_service()
    sources = service.get_sources(enabled_only=enabled_only)
    return [s.model_dump() for s in sources]


@router.get("/sources/health")
def get_sources_health():
    """Get operational health status and accessibility for all configured sources."""
    service = get_copilot_service()
    reports = service.get_sources_health()
    return [r.model_dump() for r in reports]


@router.get("/jobs/{job_id}", response_model=CopilotJob)
def get_job_details(job_id: str):
    """Fetch full Copilot opportunity record by ID."""
    service = get_copilot_service()
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found in Copilot queue.")
    return job


@router.post("/discover", response_model=List[CopilotJob])
def run_continuous_discovery(req: Optional[DiscoverRequest] = None):
    """Trigger continuous discovery and process new opportunities into the queue."""
    service = get_copilot_service()
    try:
        query = None
        if req and (req.keywords or req.locations):
            from job_copilot.ingestion.models import DiscoveryQuery
            query = DiscoveryQuery(
                keywords=req.keywords or ["Software Engineer"],
                locations=req.locations or ["Remote"],
            )
        return service.discover(query=query)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/process", response_model=List[CopilotJob])
def process_pipeline_jobs(req: Optional[ProcessJobRequest] = None):
    """Process an individual job or all stored unassessed jobs through the pipeline."""
    service = get_copilot_service()
    try:
        if req and req.job_id:
            job = service.process_job(req.job_id)
            if not job:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{req.job_id}' not found.")
            return [job]
        return service.process_all_stored()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{job_id}/prepare", status_code=status.HTTP_200_OK)
def prepare_opportunity(job_id: str, req: Optional[PrepareJobRequest] = None):
    """Prepare application package using Phase 6 Application Prep Engine."""
    service = get_copilot_service()
    try:
        strat = req.strategy_override if req else None
        package = service.prepare(job_id=job_id, strategy_override=strat)
        return {
            "status": "PREPARED",
            "job_id": job_id,
            "strategy": package.selected_resume_strategy,
            "resume_pdf_path": package.resume_pdf_path,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{job_id}/approve", response_model=CopilotJob)
def approve_opportunity(job_id: str):
    """Approve an opportunity in the queue for preparation."""
    service = get_copilot_service()
    job = service.approve(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return job


@router.post("/{job_id}/skip", response_model=CopilotJob)
def skip_opportunity(job_id: str, req: Optional[SkipJobRequest] = None):
    """Skip an opportunity in the queue."""
    service = get_copilot_service()
    reason = req.reason if req else None
    job = service.skip(job_id=job_id, reason=reason)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return job


from job_copilot.browser_worker.exceptions import SubmissionSafetyError


@router.post("/{job_id}/apply")
def apply_opportunity(job_id: str, req: Optional[ApplyJobRequest] = None):
    """
    Legacy continuous copilot application handoff.
    Enforces submission safety invariants:
    1. Unconfirmed requests return SUBMISSION_BLOCKED safely without launching browser.
    2. Missing or fabricated URLs (example.com, manual.application.portal) fail safely.
    3. Confirmed requests delegate strictly to canonical HumanConfirmationService.
       Arbitrary strings ('x', '123', 'SUBMIT') cannot authorize submission.
    """
    service = get_copilot_service()
    token = req.confirmation_token if req else None
    headless = req.headless if req else True

    if not token:
        return {
            "status": "SUBMISSION_BLOCKED",
            "reason": "Explicit human confirmation token required before external portal submission.",
            "job_id": job_id,
            "review_required": True,
        }

    try:
        result = service.apply(job_id=job_id, confirmation_token=token, headless=headless)
        return result
    except (ValueError, SubmissionSafetyError, PermissionError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
