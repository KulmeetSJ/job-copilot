"""API endpoints for Phase 10B Browser Worker task management and human confirmation."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import SubmissionSafetyError
from job_copilot.browser_worker.models import (
    BrowserTaskResponse,
    BrowserWorkerTaskCreate,
    HumanConfirmationRequest,
    HumanConfirmationResponse,
)
from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/browser/tasks", tags=["Browser Worker Tasks"])


def _format_task_response(task: BrowserTaskModel) -> BrowserTaskResponse:
    """Helper to convert ORM model to API response schema."""
    return BrowserTaskResponse(
        id=task.id,
        task_id=task.task_id,
        application_id=task.application_id,
        job_id=task.job_id,
        source=task.source,
        target_url=task.target_url,
        status=task.status,
        pause_reason=task.pause_reason,
        failure_reason=task.failure_reason,
        attempt_count=task.attempt_count,
        max_attempts=task.max_attempts,
        review_package=task.review_package_json if task.review_package_json else None,
        audit_events_count=len(task.audit_events or []),
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


@router.post("", response_model=BrowserTaskResponse, status_code=status.HTTP_201_CREATED)
def create_browser_task(
    payload: BrowserWorkerTaskCreate,
    db: Session = Depends(get_db),
) -> BrowserTaskResponse:
    """Create a new queued browser execution task."""
    repo = BrowserTaskRepository(db)
    saved = repo.create_task(
        application_id=payload.application_id,
        job_id=payload.job_id,
        source=payload.source,
        target_url=payload.target_url,
        status=BrowserTaskStatus.QUEUED,
        max_attempts=payload.max_attempts,
    )
    logger.info(f"Created browser execution task '{saved.task_id}' for URL: {payload.target_url}")
    return _format_task_response(saved)


@router.get("/{task_id}", response_model=BrowserTaskResponse)
def get_browser_task(
    task_id: str,
    db: Session = Depends(get_db),
) -> BrowserTaskResponse:
    """Retrieve details and review package for a browser task."""
    repo = BrowserTaskRepository(db)
    task = repo.get_by_task_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")
    return _format_task_response(task)


@router.post("/{task_id}/execute", response_model=BrowserTaskResponse)
async def execute_browser_task(
    task_id: str,
    db: Session = Depends(get_db),
) -> BrowserTaskResponse:
    """Trigger browser worker execution for a task up to READY_FOR_REVIEW."""
    repo = BrowserTaskRepository(db)
    task = repo.get_by_task_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    executor = BrowserTaskExecutor(db=db)
    result = await executor.execute_task(task_id)
    return _format_task_response(result)


@router.post("/{task_id}/confirm", response_model=HumanConfirmationResponse)
def confirm_browser_task_submission(
    task_id: str,
    payload: HumanConfirmationRequest,
    db: Session = Depends(get_db),
) -> HumanConfirmationResponse:
    """
    Explicit human confirmation gate.
    Validates confirmation token and triggers the only authorized submission path.
    """
    confirmation_service = HumanConfirmationService(db=db)
    try:
        return confirmation_service.validate_and_confirm(task_id=task_id, request=payload)
    except SubmissionSafetyError as sse:
        logger.warning(f"Submission confirmation blocked for task '{task_id}': {sse}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(sse))


@router.post("/{task_id}/submit", response_model=BrowserTaskResponse)
async def submit_browser_task(
    task_id: str,
    db: Session = Depends(get_db),
) -> BrowserTaskResponse:
    """Execute actual Playwright employer submission for an explicitly SUBMISSION_AUTHORIZED task."""
    repo = BrowserTaskRepository(db)
    task = repo.get_by_task_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    if task.status != BrowserTaskStatus.SUBMISSION_AUTHORIZED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task '{task_id}' is in '{task.status.value}' state. Must be 'SUBMISSION_AUTHORIZED' before submitting.",
        )

    executor = BrowserTaskExecutor(db=db)
    result = await executor.execute_submission_task(task_id)
    return _format_task_response(result)


@router.post("/{task_id}/resume", response_model=BrowserTaskResponse)
async def resume_browser_task(
    task_id: str,
    db: Session = Depends(get_db),
) -> BrowserTaskResponse:
    """Resume a browser task that was paused for human action (CAPTCHA, Login, MFA, User Input)."""
    repo = BrowserTaskRepository(db)
    task = repo.get_by_task_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    executor = BrowserTaskExecutor(db=db)
    result = await executor.resume_task(task_id)
    return _format_task_response(result)


@router.post("/{task_id}/cancel", response_model=BrowserTaskResponse)
def cancel_browser_task(
    task_id: str,
    db: Session = Depends(get_db),
) -> BrowserTaskResponse:
    """Cancel an active or pending browser task."""
    repo = BrowserTaskRepository(db)
    task = repo.get_by_task_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    updated = repo.update_status(task_id, BrowserTaskStatus.FAILED, failure_reason="Cancelled by operator")
    return _format_task_response(updated)

