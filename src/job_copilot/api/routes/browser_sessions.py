"""API endpoints for Phase 10C Authenticated Browser Session management."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from job_copilot.browser_worker.session_manager import AuthenticatedSessionManager
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus
from job_copilot.models.browser_session import BrowserSessionModel
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/browser/sessions", tags=["Browser Sessions"])


class BrowserSessionCreate(BaseModel):
    source: str = Field(..., description="Job source portal name (e.g. 'linkedin', 'naukri', 'instahyre')")
    session_id: Optional[str] = Field(default=None, description="Optional custom session ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Safe metadata (e.g. account label)")


class BrowserSessionSaveStateRequest(BaseModel):
    storage_state: Dict[str, Any] = Field(..., description="Playwright storage state dictionary")
    expires_in_days: int = Field(default=14, description="Session expiration in days")


class BrowserSessionResponse(BaseModel):
    id: int
    session_id: str
    source: str
    status: AuthenticatedSessionStatus
    has_stored_state: bool
    created_at: datetime
    last_verified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


def _format_session_response(
    session_model: BrowserSessionModel,
    manager: AuthenticatedSessionManager,
) -> BrowserSessionResponse:
    """Format ORM model to safe API response, never returning cookies/tokens."""
    has_state = manager.session_store.has_session_state(session_model.session_id)
    return BrowserSessionResponse(
        id=session_model.id,
        session_id=session_model.session_id,
        source=session_model.source,
        status=session_model.status,
        has_stored_state=has_state,
        created_at=session_model.created_at,
        last_verified_at=session_model.last_verified_at,
        expires_at=session_model.expires_at,
        metadata=session_model.metadata_json,
    )


@router.post("", response_model=BrowserSessionResponse, status_code=status.HTTP_201_CREATED)
def create_browser_session(
    payload: BrowserSessionCreate,
    db: Session = Depends(get_db),
) -> BrowserSessionResponse:
    """Register a new authenticated browser session tracking record."""
    manager = AuthenticatedSessionManager(db=db)
    session_obj = manager.create_session(
        source=payload.source,
        session_id=payload.session_id,
        metadata_json=payload.metadata,
    )
    return _format_session_response(session_obj, manager)


@router.get("", response_model=List[BrowserSessionResponse])
def list_browser_sessions(
    limit: int = 50,
    db: Session = Depends(get_db),
) -> List[BrowserSessionResponse]:
    """List all registered authenticated browser sessions."""
    manager = AuthenticatedSessionManager(db=db)
    sessions = manager.list_sessions(limit=limit)
    return [_format_session_response(s, manager) for s in sessions]


@router.get("/{session_id}", response_model=BrowserSessionResponse)
def get_browser_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> BrowserSessionResponse:
    """Retrieve metadata and status for a browser session."""
    manager = AuthenticatedSessionManager(db=db)
    session_obj = manager.get_session(session_id)
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    return _format_session_response(session_obj, manager)


@router.post("/{session_id}/save-state", response_model=BrowserSessionResponse)
async def save_browser_session_state(
    session_id: str,
    payload: BrowserSessionSaveStateRequest,
    db: Session = Depends(get_db),
) -> BrowserSessionResponse:
    """
    Save authenticated Playwright storage state into isolated local store and activate session.
    """
    manager = AuthenticatedSessionManager(db=db)
    session_obj = manager.get_session(session_id)
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    updated = await manager.save_authenticated_state(
        session_id=session_id,
        state_dict=payload.storage_state,
        expires_in_days=payload.expires_in_days,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save session state.")
    return _format_session_response(updated, manager)


@router.post("/{session_id}/revoke", response_model=BrowserSessionResponse)
async def revoke_browser_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> BrowserSessionResponse:
    """Revoke an authenticated session and purge its stored browser state."""
    manager = AuthenticatedSessionManager(db=db)
    session_obj = manager.get_session(session_id)
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    await manager.revoke_session(session_id)
    reloaded = manager.get_session(session_id)
    return _format_session_response(reloaded, manager)
