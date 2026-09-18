"""FastAPI routes for Local Interactive Browser Agent Protocol and Device Pairing."""

import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.application import Application, ApplicationStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.device import DeviceRegistrationModel, DeviceStatus
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.repositories.device_repository import DeviceRepository
from job_copilot.schemas.device import (
    AgentTaskCompleteSubmit,
    AgentTaskPackageSubmit,
    AgentTaskPollResponse,
    AgentTaskStatusUpdate,
    DeviceStatusResponse,
    PairDeviceRequest,
    PairDeviceResponse,
    PairingCodeResponse,
)
from job_copilot.services.artifact_service import ArtifactService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.models import ApplicationLifecycleStatus, EventSource
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/agent", tags=["Local Browser Agent Protocol"])


def get_authenticated_device(
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
    db: Session = Depends(get_db),
) -> DeviceRegistrationModel:
    """Dependency verifying device token authentication header."""
    if not x_device_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Device-Token authentication header.",
        )
    repo = DeviceRepository(db)
    device = repo.authenticate_device_token(x_device_token)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked device token.",
        )
    return device


@router.post("/pair", response_model=PairDeviceResponse)
def pair_device(
    payload: PairDeviceRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PairDeviceResponse:
    """
    Pair a local browser agent with the server using a one-time pairing code.
    Issues a secret device token for subsequent task polling and execution.
    """
    repo = DeviceRepository(db)
    client_ip = request.client.host if request.client else "unknown"
    try:
        device, raw_token = repo.verify_and_pair(
            pairing_code=payload.pairing_code,
            device_name=payload.device_name,
            agent_version=payload.agent_version,
            capabilities=payload.capabilities,
            client_ip=client_ip,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    forwarded_proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    if forwarded_host:
        base_url = f"{forwarded_proto}://{forwarded_host}"
    else:
        base_url = str(request.base_url).rstrip("/")

    return PairDeviceResponse(
        success=True,
        device_id=device.device_id,
        device_token=raw_token,
        device_name=device.device_name,
        server_url=base_url,
        message="Local browser agent paired successfully.",
    )


@router.get("/device", response_model=DeviceStatusResponse)
def get_device_status(
    device: DeviceRegistrationModel = Depends(get_authenticated_device),
) -> DeviceStatusResponse:
    """Retrieve operational details of the currently authenticated device."""
    is_active = False
    if device.status in (DeviceStatus.CONNECTED, DeviceStatus.BUSY) and device.last_seen_at is not None:
        last_seen_utc = device.last_seen_at.replace(tzinfo=timezone.utc) if device.last_seen_at.tzinfo is None else device.last_seen_at
        is_active = (datetime.now(timezone.utc) - last_seen_utc).total_seconds() < 60
    return DeviceStatusResponse(
        device_id=device.device_id,
        device_name=device.device_name,
        status=device.status.value,
        is_active=is_active,
        last_seen_at=device.last_seen_at,
        capabilities=device.capabilities,
        agent_version=device.agent_version,
        created_at=device.created_at,
    )


@router.get("/tasks/poll", response_model=AgentTaskPollResponse)
def poll_tasks(
    device: DeviceRegistrationModel = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
) -> AgentTaskPollResponse:
    """
    Poll for an authorized LOCAL_INTERACTIVE browser task.
    Returns the next task in QUEUED or SUBMISSION_AUTHORIZED status.
    """
    task_repo = BrowserTaskRepository(db)
    app_repo = ApplicationRepository(db)
    device_repo = DeviceRepository(db)

    # Update device heartbeat
    device_repo.update_heartbeat(device.device_id, status=DeviceStatus.CONNECTED)

    # 1. First priority: tasks authorized for final submission
    authorized_tasks = task_repo.list_by_status(BrowserTaskStatus.SUBMISSION_AUTHORIZED)
    for task in authorized_tasks:
        if task.execution_mode == "LOCAL_INTERACTIVE":
            # Claim task
            claimed = task_repo.claim_task(
                task_id=task.task_id,
                expected_status=BrowserTaskStatus.SUBMISSION_AUTHORIZED,
                new_status=BrowserTaskStatus.SUBMISSION_RUNNING,
                worker_id=f"device:{device.device_id}",
            )
            if not claimed:
                continue
            device_repo.update_heartbeat(device.device_id, status=DeviceStatus.BUSY)
            app = app_repo.get_by_application_id(task.application_id) if task.application_id else None
            return AgentTaskPollResponse(
                has_task=True,
                task={
                    "task_id": task.task_id,
                    "application_id": task.application_id,
                    "job_id": task.job_id,
                    "company": app.company if app else "Company",
                    "role": app.role if app else "Role",
                    "source": task.source,
                    "target_url": task.target_url,
                    "action": "EXECUTE_SUBMISSION",
                    "status": BrowserTaskStatus.SUBMISSION_RUNNING.value,
                    "confirmation_token": task.confirmation_token,
                },
            )

    # 2. Second priority: tasks queued for initial form preparation & inspection
    queued_tasks = task_repo.list_by_status(BrowserTaskStatus.QUEUED)
    for task in queued_tasks:
        if task.execution_mode == "LOCAL_INTERACTIVE":
            claimed = task_repo.claim_task(
                task_id=task.task_id,
                expected_status=BrowserTaskStatus.QUEUED,
                new_status=BrowserTaskStatus.RUNNING,
                worker_id=f"device:{device.device_id}",
            )
            if not claimed:
                continue
            device_repo.update_heartbeat(device.device_id, status=DeviceStatus.BUSY)
            app = app_repo.get_by_application_id(task.application_id) if task.application_id else None
            return AgentTaskPollResponse(
                has_task=True,
                task={
                    "task_id": task.task_id,
                    "application_id": task.application_id,
                    "job_id": task.job_id,
                    "company": app.company if app else "Company",
                    "role": app.role if app else "Role",
                    "source": task.source,
                    "target_url": task.target_url,
                    "action": "INSPECT_AND_FILL",
                    "status": BrowserTaskStatus.RUNNING.value,
                },
            )

    return AgentTaskPollResponse(has_task=False, task=None)


@router.post("/tasks/{task_id}/heartbeat")
def update_task_heartbeat(
    task_id: str,
    payload: AgentTaskStatusUpdate,
    device: DeviceRegistrationModel = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update task status (e.g. CAPTCHA_REQUIRED, LOGIN_REQUIRED, RUNNING) and device status."""
    task_repo = BrowserTaskRepository(db)
    device_repo = DeviceRepository(db)
    task = task_repo.get_by_task_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    try:
        new_status = BrowserTaskStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid task status '{payload.status}'.")

    task_repo.update_status(
        task_id=task_id,
        status=new_status,
        pause_reason=payload.pause_reason,
        failure_reason=payload.failure_reason,
    )
    task_repo.append_audit_event(
        task_id=task_id,
        event={
            "event": "agent_heartbeat",
            "status": new_status.value,
            "pause_reason": payload.pause_reason,
            "device_id": device.device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    device_status = DeviceStatus.BUSY if new_status in (BrowserTaskStatus.RUNNING, BrowserTaskStatus.SUBMISSION_RUNNING) else DeviceStatus.CONNECTED
    device_repo.update_heartbeat(device.device_id, status=device_status)

    return {"success": True, "task_id": task_id, "status": new_status.value}


@router.post("/tasks/{task_id}/package")
def submit_task_package(
    task_id: str,
    payload: AgentTaskPackageSubmit,
    device: DeviceRegistrationModel = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Save form inspection results, pre-submission screenshot, and transition task to READY_FOR_REVIEW.
    Generates a secure confirmation token for human authorization.
    """
    task_repo = BrowserTaskRepository(db)
    task = task_repo.get_by_task_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    screenshot_artifact_id = None
    if payload.screenshot_base64:
        try:
            artifact_svc = ArtifactService(db=db)
            img_bytes = base64.b64decode(payload.screenshot_base64)
            art = artifact_svc.create_artifact(
                application_id=task.application_id,
                artifact_type="screenshot",
                content=img_bytes,
                filename=f"pre_submit_{task_id}.png",
                content_type="image/png",
            )
            screenshot_artifact_id = art.artifact_id
        except Exception as e:
            logger.warning(f"Failed to persist review screenshot for task '{task_id}': {e}")

    import secrets
    from datetime import timedelta
    confirmation_token = f"tok_sub_{secrets.token_urlsafe(16)}"
    confirmation_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    review_pkg = {
        "task_id": task_id,
        "application_id": task.application_id,
        "fields_detected_count": payload.fields_detected_count,
        "fields_filled_count": payload.fields_filled_count,
        "fields_requiring_input_count": payload.fields_requiring_input_count,
        "screenshot_artifact_id": screenshot_artifact_id,
        "fields": payload.review_package_json.get("fields", []),
    }
    task = task_repo.set_review_package(
        task_id=task_id,
        review_package=review_pkg,
        confirmation_token=confirmation_token,
        confirmation_expires_at=confirmation_expires_at,
    )
    task_repo.update_status(task_id, BrowserTaskStatus.READY_FOR_REVIEW)

    device_repo = DeviceRepository(db)
    device_repo.update_heartbeat(device.device_id, status=DeviceStatus.CONNECTED)

    logger.info(f"Task '{task_id}' transitioned to READY_FOR_REVIEW by device '{device.device_id}'.")
    return {
        "success": True,
        "task_id": task_id,
        "status": BrowserTaskStatus.READY_FOR_REVIEW.value,
        "has_confirmation_token": bool(task.confirmation_token),
    }


@router.post("/tasks/{task_id}/complete")
def submit_task_complete(
    task_id: str,
    payload: AgentTaskCompleteSubmit,
    device: DeviceRegistrationModel = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Record verified employer portal submission completion evidence.
    Transitions task to COMPLETED and Application to APPLIED / SUBMITTED.
    Strictly gates on task state (SUBMISSION_RUNNING), device ownership, and idempotency.
    """
    task_repo = BrowserTaskRepository(db)
    app_repo = ApplicationRepository(db)
    task = task_repo.get_by_task_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    # 1. Device / Worker Ownership Gate
    is_owner = (
        task.assigned_device_id == device.device_id
        or task.worker_id == f"device:{device.device_id}"
        or task.worker_id == device.device_id
    )
    if not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Task '{task_id}' is not assigned to device '{device.device_id}'.",
        )

    # 2. Employer confirmation signal verification (must be non-empty)
    if not payload.employer_confirmation_signal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer confirmation signal must be provided to mark task COMPLETED.",
        )

    # 3. Idempotency Guard: if already COMPLETED, return existing result without re-executing side effects
    if task.status == BrowserTaskStatus.COMPLETED:
        device_repo = DeviceRepository(db)
        device_repo.update_heartbeat(device.device_id, status=DeviceStatus.CONNECTED)
        existing_ref = payload.submission_reference
        audit_events = getattr(task, "audit_events", None) or []
        for e in audit_events:
            if e.get("event") == "submission_completed_verified" and e.get("submission_reference"):
                existing_ref = e.get("submission_reference")
                break
        logger.info(f"Task '{task_id}' is already COMPLETED. Returning idempotent completion for device '{device.device_id}'.")
        return {
            "success": True,
            "task_id": task_id,
            "application_id": task.application_id,
            "status": BrowserTaskStatus.COMPLETED.value,
            "submission_reference": existing_ref,
        }

    # 4. State Gate: only tasks in SUBMISSION_RUNNING may be marked COMPLETED
    if task.status != BrowserTaskStatus.SUBMISSION_RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task '{task_id}' is in status '{task.status.value}', expected '{BrowserTaskStatus.SUBMISSION_RUNNING.value}'.",
        )

    # 5. Mark BrowserTask COMPLETED
    task_repo.update_status(task_id, BrowserTaskStatus.COMPLETED)
    task_repo.append_audit_event(
        task_id=task_id,
        event={
            "event": "submission_completed_verified",
            "device_id": device.device_id,
            "submission_reference": payload.submission_reference,
            "employer_signal": payload.employer_confirmation_signal,
            "evidence_notes": payload.evidence_notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    # 6. Mark Application APPLIED and record event
    now = datetime.now(timezone.utc)
    if task.application_id:
        app = app_repo.get_by_application_id(task.application_id)
        if app:
            app.status = ApplicationStatus.APPLIED
            app.submitted_at = now
            app.applied_at = now
            app_repo.append_event(
                application_id=task.application_id,
                job_id=task.job_id or task.application_id,
                event_type="SUBMITTED",
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                source="LOCAL_INTERACTIVE_AGENT",
                notes=f"Employer confirmation verified via local interactive agent. Ref: {payload.submission_reference or 'N/A'}",
            )
            db.commit()

        # 7. Update Tracking Service
        try:
            tracking_svc = TrackingService()
            tracking_svc.record_event(
                application_id=task.application_id,
                event_type=ApplicationLifecycleStatus.SUBMITTED,
                source=EventSource.BROWSER,
                notes=f"Employer confirmation verified via local interactive agent. Ref: {payload.submission_reference or 'N/A'}",
            )
        except Exception as e:
            logger.warning(f"Notice while updating TrackingService for application '{task.application_id}': {e}")

    device_repo = DeviceRepository(db)
    device_repo.update_heartbeat(device.device_id, status=DeviceStatus.CONNECTED)

    logger.info(f"Task '{task_id}' verified and marked COMPLETED / SUBMITTED by device '{device.device_id}'.")
    return {
        "success": True,
        "task_id": task_id,
        "application_id": task.application_id,
        "status": BrowserTaskStatus.COMPLETED.value,
        "submission_reference": payload.submission_reference,
    }
