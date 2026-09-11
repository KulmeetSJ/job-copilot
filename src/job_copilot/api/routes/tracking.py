"""REST API endpoints for Phase 8 Application Tracking."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from job_copilot.tracking.models import (
    ApplicationEvent,
    ApplicationLifecycleStatus,
    ApplicationRecord,
    EventSource,
)
from job_copilot.services.tracking_service import TrackingService

router = APIRouter(prefix="/api/tracking", tags=["Application Tracking"])

# Singleton service instance
_service: Optional[TrackingService] = None


def get_tracking_service() -> TrackingService:
    global _service
    if _service is None:
        _service = TrackingService()
    return _service


class RegisterSubmissionRequest(BaseModel):
    job_id: str


class RecordEventRequest(BaseModel):
    event_type: ApplicationLifecycleStatus
    source: EventSource = Field(default=EventSource.MANUAL)
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AddNoteRequest(BaseModel):
    note: str


@router.post("/applications", response_model=ApplicationRecord, status_code=status.HTTP_201_CREATED)
def register_application(req: RegisterSubmissionRequest):
    """Register a prepared or submitted application into tracking."""
    service = get_tracking_service()
    try:
        record = service.register_submission(job_id=req.job_id)
        return record
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/applications", response_model=List[ApplicationRecord])
def list_tracked_applications(
    status: Optional[ApplicationLifecycleStatus] = Query(None, description="Filter by status"),
    strategy: Optional[str] = Query(None, description="Filter by resume strategy"),
    recommendation: Optional[str] = Query(None, description="Filter by recommendation tier"),
):
    """List all tracked job applications."""
    service = get_tracking_service()
    return service.list_applications(status=status, strategy=strategy, recommendation=recommendation)


@router.get("/applications/{application_id}", response_model=ApplicationRecord)
def get_tracked_application(application_id: str):
    """Get single tracked application record by ID."""
    service = get_tracking_service()
    app = service.get_application(application_id)
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Application '{application_id}' not found.")
    return app


@router.post("/applications/{application_id}/events", response_model=ApplicationEvent)
def record_application_event(application_id: str, req: RecordEventRequest):
    """Record an outcome or status event for an application."""
    service = get_tracking_service()
    try:
        event = service.record_event(
            application_id=application_id,
            event_type=req.event_type,
            source=req.source,
            notes=req.notes,
            metadata=req.metadata,
        )
        return event
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/applications/{application_id}/timeline", response_model=List[ApplicationEvent])
def get_application_timeline(application_id: str):
    """Get chronological event timeline for an application."""
    service = get_tracking_service()
    try:
        return service.get_timeline(application_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/applications/{application_id}/notes", response_model=ApplicationRecord)
def add_application_note(application_id: str, req: AddNoteRequest):
    """Add user note to an application record."""
    service = get_tracking_service()
    try:
        return service.add_user_note(application_id, req.note)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
