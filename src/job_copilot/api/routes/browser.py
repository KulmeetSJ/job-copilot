"""REST API endpoints for Phase 7 Browser-Assisted Application Workflow."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from job_copilot.browser.models import (
    BrowserSession,
    ReviewArtifact,
    SubmissionResult,
)
from job_copilot.services.browser_workflow_service import BrowserWorkflowService

router = APIRouter(prefix="/api/browser", tags=["Browser Workflow"])

# Singleton service instance for API runtime
_service: Optional[BrowserWorkflowService] = None


def get_browser_service() -> BrowserWorkflowService:
    global _service
    if _service is None:
        _service = BrowserWorkflowService()
    return _service


class StartBrowserSessionRequest(BaseModel):
    job_id: str
    application_url: str
    headless: bool = True


class ProvideInputRequest(BaseModel):
    field_id: str
    value: Any


class SubmitSessionRequest(BaseModel):
    confirmed: bool = Field(default=False, description="Explicit user confirmation to submit")
    confirm_text: Optional[str] = Field(default=None, description="Must match 'SUBMIT' if confirmed")


@router.post("/start", response_model=BrowserSession)
async def start_browser_session(req: StartBrowserSessionRequest):
    """Start an interactive browser application session."""
    service = get_browser_service()
    try:
        session = await service.start_session(
            job_id=req.job_id,
            application_url=req.application_url,
            headless=req.headless,
        )
        return session
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{session_id}", response_model=BrowserSession)
async def get_browser_session(session_id: str):
    """Get active or stored browser session state."""
    service = get_browser_service()
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    return session


@router.post("/{session_id}/inspect", response_model=BrowserSession)
async def inspect_browser_page(session_id: str):
    """Re-inspect DOM fields on current page."""
    service = get_browser_service()
    try:
        session = await service.inspect_session(session_id)
        return session
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{session_id}/fill", response_model=BrowserSession)
async def auto_fill_browser_session(session_id: str):
    """Safely auto-fill mapped candidate data and Phase 6 answers."""
    service = get_browser_service()
    try:
        session = await service.fill_session(session_id)
        return session
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{session_id}/inputs", response_model=List[Dict[str, Any]])
async def get_unresolved_inputs(session_id: str):
    """Get all fields requiring explicit user input."""
    service = get_browser_service()
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    res = []
    for field_id in session.unresolved_fields:
        field = next((f for f in session.detected_fields if f.field_id == field_id), None)
        mapping = next((m for m in session.mappings if m.field_id == field_id), None)
        res.append({
            "field_id": field_id,
            "label": field.label if field else field_id,
            "element_type": field.element_type.value if field else "UNKNOWN",
            "required": field.required if field else False,
            "rationale": mapping.rationale if mapping else "User input required",
        })
    return res


@router.post("/{session_id}/input", response_model=BrowserSession)
async def provide_field_input(session_id: str, req: ProvideInputRequest):
    """Provide explicit user input for a field."""
    service = get_browser_service()
    try:
        session = await service.provide_user_input(
            session_id=session_id,
            field_id=req.field_id,
            value=req.value,
        )
        return session
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{session_id}/review", response_model=ReviewArtifact)
async def review_browser_session(session_id: str):
    """Generate pre-submission review artifact."""
    service = get_browser_service()
    try:
        review = await service.review_session(session_id)
        return review
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{session_id}/submit", response_model=SubmissionResult)
async def submit_browser_session(session_id: str, req: SubmitSessionRequest):
    """
    Submit application.
    Requires explicit human confirmation (confirmed=True or confirm_text='SUBMIT').
    """
    service = get_browser_service()
    try:
        result = await service.submit_session(
            session_id=session_id,
            confirmed=req.confirmed,
            confirm_text=req.confirm_text,
        )
        return result
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{session_id}/cancel", response_model=BrowserSession)
async def cancel_browser_session(session_id: str):
    """Cancel browser application session."""
    service = get_browser_service()
    try:
        session = await service.cancel_session(session_id)
        return session
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
