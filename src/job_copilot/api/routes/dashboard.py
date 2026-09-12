"""REST API endpoints for Phase 11 Human Review Dashboard & Control Center."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from job_copilot.api.auth import require_dashboard_auth
from job_copilot.browser_worker.exceptions import SubmissionSafetyError
from job_copilot.copilot.models import PriorityBand, QueueStatus
from job_copilot.db.database import get_db
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.schemas.dashboard import (
    AnalyzeOpportunityRequest,
    AnalyzeOpportunityResponse,
    ApplicationDetailResponse,
    ApplicationTimelineEvent,
    ArtifactSummaryItem,
    BrowserReviewSummary,
    DashboardOverviewResponse,
    DashboardQueueResponse,
    HumanInputSubmitRequest,
    JobDetailResponse,
    PrepareApplicationPayload,
    RetrySubmissionPayload,
    SessionMetadataItem,
    SkipApplicationPayload,
    SourceMonitoringItem,
    SubmissionConfirmPayload,
    SubmissionConfirmResponse,
)
from job_copilot.services.dashboard_service import DashboardService
from job_copilot.tracking.models import ApplicationRecord
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["Human Review Dashboard"],
    dependencies=[Depends(require_dashboard_auth)],
)


def get_dashboard_service(db: Session = Depends(get_db)) -> DashboardService:
    """Dependency provider for DashboardService scoped to request DB session."""
    return DashboardService(db=db)


# ==============================================================================
# Overview & Priority Queue
# ==============================================================================

@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardOverviewResponse:
    """Retrieve high-level overview metrics, queue counts, pipeline stages, and recent activity."""
    return service.get_overview()


@router.get("/queue", response_model=DashboardQueueResponse)
def get_priority_queue(
    status: Optional[QueueStatus] = Query(None, description="Filter by queue status"),
    priority: Optional[PriorityBand] = Query(None, description="Filter by priority band"),
    min_score: Optional[float] = Query(None, description="Filter by minimum priority score"),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardQueueResponse:
    """Fetch prioritized opportunity cards with matched skills, gaps, and recommendations."""
    return service.get_queue(status=status, priority_band=priority, min_priority_score=min_score)


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
def get_job_detail(
    job_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> JobDetailResponse:
    """Retrieve comprehensive job detail, 7-dimensional score breakdown, and Fact vs Inference explanation."""
    try:
        return service.get_job_detail(job_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch job detail for '{job_id}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/opportunities/analyze", response_model=AnalyzeOpportunityResponse)
def analyze_submitted_opportunity(
    payload: AnalyzeOpportunityRequest,
    service: DashboardService = Depends(get_dashboard_service),
) -> AnalyzeOpportunityResponse:
    """
    Ingest, normalize, match, tailor resume, and prepare application for a candidate-submitted job URL.
    Safely validates URL/domain, deduplicates, and stages at READY_FOR_REVIEW.
    Never performs automated external submissions.
    """
    try:
        return service.analyze_user_submitted_url(payload.url)
    except ValueError as ve:
        logger.warning(f"Validation error analyzing opportunity URL '{payload.url}': {ve}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Unexpected error analyzing opportunity URL '{payload.url}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to analyze job opportunity: {e}")



# ==============================================================================
# Applications & Review
# ==============================================================================

@router.get("/applications", response_model=List[ApplicationRecord])
def list_applications(
    status: Optional[ApplicationStatus] = Query(None, description="Filter by application status"),
    strategy: Optional[str] = Query(None, description="Filter by resume strategy"),
    service: DashboardService = Depends(get_dashboard_service),
) -> List[ApplicationRecord]:
    """List tracked job applications across all lifecycle stages."""
    strat_filter = strategy if strategy else None
    stat_filter = status if status else None
    return service.list_applications(status=stat_filter, strategy=strat_filter)


@router.get("/applications/{application_id}", response_model=ApplicationDetailResponse)
def get_application_detail(
    application_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApplicationDetailResponse:
    """Retrieve complete application review data, tailored resume, cover letter, answers, and timeline."""
    return service.get_application_detail(application_id)


@router.get("/applications/{application_id}/timeline", response_model=List[ApplicationTimelineEvent])
def get_application_timeline(
    application_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> List[ApplicationTimelineEvent]:
    """Retrieve append-only chronological lifecycle event stream for an application."""
    detail = service.get_application_detail(application_id)
    return detail.timeline


@router.get("/applications/{application_id}/artifacts", response_model=List[ArtifactSummaryItem])
def get_application_artifacts(
    application_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> List[ArtifactSummaryItem]:
    """Retrieve list of artifacts associated with this application."""
    detail = service.get_application_detail(application_id)
    return detail.artifacts


@router.get("/applications/{application_id}/review", response_model=Optional[BrowserReviewSummary])
def get_browser_review_package(
    application_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> Optional[BrowserReviewSummary]:
    """Retrieve browser worker execution review package, filled fields, and safety status."""
    detail = service.get_application_detail(application_id)
    return detail.browser_review


# ==============================================================================
# Human Actions (Prepare, Skip, User Input, Confirm)
# ==============================================================================

@router.post("/applications/{application_id}/prepare", response_model=ApplicationDetailResponse)
def prepare_application(
    application_id: str,
    payload: Optional[PrepareApplicationPayload] = None,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApplicationDetailResponse:
    """Prepare tailored resume, cover letter, and Q&A answers for an application."""
    try:
        strat = payload.strategy_override if payload else None
        return service.prepare_application(application_id=application_id, strategy_override=strat)
    except Exception as e:
        logger.error(f"Application preparation failed for '{application_id}': {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/applications/{application_id}/skip", response_model=ApplicationDetailResponse)
def skip_application(
    application_id: str,
    payload: Optional[SkipApplicationPayload] = None,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApplicationDetailResponse:
    """Skip an opportunity/application without performing any external submissions."""
    reason = payload.reason if payload else None
    return service.skip_application(application_id=application_id, reason=reason)


@router.post("/applications/{application_id}/input", response_model=ApplicationDetailResponse)
def submit_human_input(
    application_id: str,
    payload: HumanInputSubmitRequest,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApplicationDetailResponse:
    """
    Supply human answers for sensitive or unresolved application questions.
    Answers are safely stored in application state without mutating candidate truth files.
    """
    return service.submit_user_inputs(application_id=application_id, req=payload)


@router.post("/applications/{application_id}/confirm", response_model=SubmissionConfirmResponse)
def confirm_application_submission(
    application_id: str,
    payload: SubmissionConfirmPayload,
    service: DashboardService = Depends(get_dashboard_service),
) -> SubmissionConfirmResponse:
    """
    Explicit submission confirmation gate.
    Requires exact keyword 'SUBMIT' and valid confirmation_token.
    Delegates directly to authoritative HumanConfirmationService.
    """
    if payload.confirm_text.strip().upper() != "SUBMIT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation keyword must match exact word 'SUBMIT'.",
        )
    try:
        return service.confirm_submission(payload, application_id=application_id)
    except SubmissionSafetyError as sse:
        logger.warning(f"Submission confirmation blocked for application '{application_id}': {sse}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(sse))
    except Exception as e:
        logger.error(f"Unexpected error during submission confirmation: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/applications/{application_id}/resume", response_model=ApplicationDetailResponse)
def resume_application(
    application_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApplicationDetailResponse:
    """
    Resume automation for an application that paused for human action (CAPTCHA, Login, MFA).
    """
    try:
        return service.resume_application(application_id=application_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error(f"Unexpected error during application resume: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/applications/{application_id}/retry", response_model=ApplicationDetailResponse)
def retry_application_submission(
    application_id: str,
    payload: RetrySubmissionPayload,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApplicationDetailResponse:
    """
    Review & Retry Submission gate for SUBMISSION_UNVERIFIED applications.
    Requires explicit duplicate risk acknowledgement checkbox and generates a fresh confirmation token.
    Historical Mastercard record (app-usr-2a43a63d) is protected and non-retryable.
    """
    try:
        return service.retry_submission(application_id=application_id, payload=payload)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Unexpected error during application submission retry: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==============================================================================
# Analytics, Sources, Sessions, Activity, Artifact Content
# ==============================================================================

@router.get("/analytics")
def get_dashboard_analytics(
    from_date: Optional[datetime] = Query(None, description="Start date filter"),
    to_date: Optional[datetime] = Query(None, description="End date filter"),
    service: DashboardService = Depends(get_dashboard_service),
) -> Dict[str, Any]:
    """Retrieve Phase 8 outcome analytics, funnel conversion, and cohort metrics (N < 10 labeled)."""
    return service.get_analytics(from_date=from_date, to_date=to_date)


@router.get("/sources", response_model=List[SourceMonitoringItem])
def get_sources_monitoring(
    service: DashboardService = Depends(get_dashboard_service),
) -> List[SourceMonitoringItem]:
    """Retrieve operational health, check intervals, and login requirements for configured sources."""
    return service.get_sources()


@router.get("/sessions", response_model=List[SessionMetadataItem])
def get_sessions_metadata(
    service: DashboardService = Depends(get_dashboard_service),
) -> List[SessionMetadataItem]:
    """Retrieve safe metadata for authenticated source sessions (Zero secrets/tokens)."""
    return service.get_sessions()


@router.get("/activity")
def get_recent_activity(
    limit: int = Query(50, ge=1, le=200),
    service: DashboardService = Depends(get_dashboard_service),
) -> List[Dict[str, Any]]:
    """Retrieve sanitized chronological audit events."""
    return service.get_activity_log(limit=limit)


@router.get("/artifacts/{artifact_id}/content")
def get_artifact_binary(
    artifact_id: str,
    service: DashboardService = Depends(get_dashboard_service),
):
    """Safely stream binary artifact content with appropriate content-type headers."""
    try:
        data, content_type, filename = service.get_artifact_content(artifact_id)
        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Artifact '{artifact_id}' not found.")
    except Exception as e:
        logger.error(f"Failed to fetch artifact content for '{artifact_id}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/applications/{application_id}/resume/pdf")
def get_application_resume_pdf(
    application_id: str,
    service: DashboardService = Depends(get_dashboard_service),
):
    """Serve the compiled PDF for an application resume directly for inline viewing."""
    try:
        data, content_type, filename = service.get_application_resume_pdf(application_id)
        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Compiled PDF not found for application '{application_id}'.")
    except Exception as e:
        logger.error(f"Failed to fetch resume PDF for '{application_id}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# --- Device Management Endpoints ---

@router.post("/devices/pair-code")
def create_device_pairing_code(
    device_name: str = Query("Local Browser Agent", description="Device name/hostname"),
    service: DashboardService = Depends(get_dashboard_service),
):
    """Generate a short-lived 6-digit pairing code for connecting a local interactive browser agent."""
    return service.generate_device_pairing_code(device_name=device_name)


@router.get("/devices")
def list_paired_devices(
    service: DashboardService = Depends(get_dashboard_service),
):
    """List paired local browser agent devices and their connectivity status."""
    return service.list_paired_devices()


@router.post("/devices/{device_id}/revoke")
def revoke_paired_device(
    device_id: str,
    service: DashboardService = Depends(get_dashboard_service),
):
    """Revoke authorization for a paired local browser agent device."""
    success = service.revoke_device(device_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_id}' not found.")
    return {"success": True, "device_id": device_id, "message": "Device revoked successfully."}

