"""Focused safety tests for local agent protocol completion endpoint.

Verifies:
1. State Gate: Only SUBMISSION_RUNNING tasks can be marked COMPLETED (rejects READY_FOR_REVIEW, QUEUED, SUBMISSION_AUTHORIZED, etc. with 409).
2. Ownership: Task must be owned by the authenticated device (rejects wrong/unassigned devices with 403).
3. Ownership Representations: Supports assigned_device_id, worker_id="device:{device_id}", and worker_id=device_id.
4. Success Verification: Requires non-empty employer_confirmation_signal (400 if empty).
5. Idempotency: Repeated completions on already COMPLETED tasks are harmless:
   - Same successful 200 response
   - submitted_at unchanged
   - No duplicate SUBMITTED lifecycle tracking events
   - No duplicate completion audit events
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.api.routes.dashboard import get_dashboard_service
from job_copilot.db.base import Base
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.tracking.models import ApplicationLifecycleStatus, EventSource
from job_copilot.models.application import Application, ApplicationEventModel, ApplicationStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.repositories.device_repository import DeviceRepository
from job_copilot.services.dashboard_service import DashboardService


@pytest.fixture
def in_memory_db():
    """Create isolated in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(in_memory_db):
    """FastAPI TestClient with overridden dependencies."""
    def override_get_db():
        try:
            yield in_memory_db
        finally:
            pass

    def override_get_dashboard_service():
        return DashboardService(db=in_memory_db)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_dashboard_service] = override_get_dashboard_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _pair_device(client: TestClient, device_name: str = "TestDevice") -> tuple[str, str]:
    """Helper to generate pairing code, pair device, and return (device_id, device_token)."""
    gen_resp = client.post(f"/api/dashboard/devices/pair-code?device_name={device_name}")
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    pairing_code = gen_data["pairing_code"]

    pair_resp = client.post(
        "/api/agent/pair",
        json={
            "pairing_code": pairing_code,
            "device_name": device_name,
            "agent_version": "1.0.0",
            "capabilities": ["playwright_chromium", "visible_browser"],
        },
    )
    assert pair_resp.status_code == 200
    pair_data = pair_resp.json()
    return pair_data["device_id"], pair_data["device_token"]


def _create_job_and_application(db, app_id: str, job_id_str: str) -> Application:
    """Helper to create Job and Application rows for testing."""
    job = Job(
        job_id=job_id_str,
        title="Senior Software Engineer",
        company="TechCorp",
        source="greenhouse",
        description="Looking for senior backend engineer.",
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    app_record = Application(
        application_id=app_id,
        job_id=job.id,
        job_id_str=job_id_str,
        company="TechCorp",
        role="Senior Software Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
        created_at=datetime.now(timezone.utc),
    )
    db.add(app_record)
    db.commit()
    db.refresh(app_record)
    return app_record


@pytest.mark.parametrize(
    "invalid_status",
    [
        BrowserTaskStatus.READY_FOR_REVIEW,
        BrowserTaskStatus.QUEUED,
        BrowserTaskStatus.SUBMISSION_AUTHORIZED,
        BrowserTaskStatus.USER_INPUT_REQUIRED,
        BrowserTaskStatus.RUNNING,
        BrowserTaskStatus.FAILED,
    ],
)
def test_state_gate_rejects_non_submission_running(client, in_memory_db, invalid_status):
    """
    submit_task_complete must reject completion with HTTP 409 when the task
    is not in SUBMISSION_RUNNING (e.g. READY_FOR_REVIEW, QUEUED, SUBMISSION_AUTHORIZED, etc.).
    """
    device_id, device_token = _pair_device(client, "GateDevice")
    app_record = _create_job_and_application(in_memory_db, f"app-gate-{invalid_status.value}", f"job-gate-{invalid_status.value}")

    task_repo = BrowserTaskRepository(in_memory_db)
    task = BrowserTaskModel(
        task_id=f"task-gate-{invalid_status.value}",
        application_id=app_record.application_id,
        job_id=app_record.job_id_str,
        source="greenhouse",
        target_url="https://boards.greenhouse.io/techcorp/jobs/101",
        status=invalid_status,
        assigned_device_id=device_id,
        execution_mode="LOCAL_INTERACTIVE",
    )
    task_repo.create(task)

    resp = client.post(
        f"/api/agent/tasks/{task.task_id}/complete",
        headers={"X-Device-Token": device_token},
        json={
            "task_id": task.task_id,
            "employer_confirmation_signal": "Thanks for applying! Confirmation #12345",
            "submission_reference": "REF-12345",
        },
    )
    assert resp.status_code == 409
    assert "expected 'SUBMISSION_RUNNING'" in resp.json()["detail"]

    # Verify task status was NOT modified
    reloaded_task = task_repo.get_by_task_id(task.task_id)
    assert reloaded_task.status == invalid_status

    # Verify application status was NOT changed to APPLIED
    app_repo = ApplicationRepository(in_memory_db)
    reloaded_app = app_repo.get_by_application_id(app_record.application_id)
    assert reloaded_app.status == ApplicationStatus.READY_TO_APPLY
    assert reloaded_app.submitted_at is None


def test_device_ownership_rejection(client, in_memory_db):
    """
    Calling completion from a wrong device or when the task is not assigned
    to the authenticated device must be rejected with HTTP 403.
    """
    device_a_id, device_a_token = _pair_device(client, "DeviceA")
    device_b_id, device_b_token = _pair_device(client, "DeviceB")

    app_record = _create_job_and_application(in_memory_db, "app-owner-01", "job-owner-01")

    task_repo = BrowserTaskRepository(in_memory_db)
    # Task owned by Device A
    task = BrowserTaskModel(
        task_id="task-owner-01",
        application_id=app_record.application_id,
        job_id=app_record.job_id_str,
        source="greenhouse",
        target_url="https://boards.greenhouse.io/techcorp/jobs/102",
        status=BrowserTaskStatus.SUBMISSION_RUNNING,
        assigned_device_id=device_a_id,
        execution_mode="LOCAL_INTERACTIVE",
    )
    task_repo.create(task)

    # Device B tries to complete Device A's task -> 403 Forbidden
    resp = client.post(
        f"/api/agent/tasks/{task.task_id}/complete",
        headers={"X-Device-Token": device_b_token},
        json={
            "task_id": task.task_id,
            "employer_confirmation_signal": "Thanks for applying! Confirmation #12345",
            "submission_reference": "REF-12345",
        },
    )
    assert resp.status_code == 403
    assert f"not assigned to device '{device_b_id}'" in resp.json()["detail"]

    # Also test unassigned task -> 403 Forbidden
    task_unassigned = BrowserTaskModel(
        task_id="task-unassigned-01",
        application_id=app_record.application_id,
        job_id=app_record.job_id_str,
        source="greenhouse",
        target_url="https://boards.greenhouse.io/techcorp/jobs/103",
        status=BrowserTaskStatus.SUBMISSION_RUNNING,
        assigned_device_id=None,
        worker_id=None,
        execution_mode="LOCAL_INTERACTIVE",
    )
    task_repo.create(task_unassigned)

    resp_unassigned = client.post(
        f"/api/agent/tasks/{task_unassigned.task_id}/complete",
        headers={"X-Device-Token": device_a_token},
        json={
            "task_id": task_unassigned.task_id,
            "employer_confirmation_signal": "Thanks for applying! Confirmation #12345",
        },
    )
    assert resp_unassigned.status_code == 403


@pytest.mark.parametrize(
    "ownership_setup",
    [
        "assigned_device_id",
        "worker_id_device_prefix",  # f"device:{device_id}" used in production local agent polling
        "worker_id_raw",            # device_id
    ],
)
def test_valid_ownership_representations(client, in_memory_db, ownership_setup):
    """
    Accept the repository's valid ownership representations:
    1. task.assigned_device_id == device.device_id
    2. task.worker_id == f"device:{device.device_id}" (exact production poll_tasks claim)
    3. task.worker_id == device.device_id
    """
    device_id, device_token = _pair_device(client, f"Dev-{ownership_setup}")
    app_record = _create_job_and_application(in_memory_db, f"app-rep-{ownership_setup}", f"job-rep-{ownership_setup}")

    task_repo = BrowserTaskRepository(in_memory_db)
    assigned_dev = None
    worker = None

    if ownership_setup == "assigned_device_id":
        assigned_dev = device_id
    elif ownership_setup == "worker_id_device_prefix":
        worker = f"device:{device_id}"
    elif ownership_setup == "worker_id_raw":
        worker = device_id

    task = BrowserTaskModel(
        task_id=f"task-rep-{ownership_setup}",
        application_id=app_record.application_id,
        job_id=app_record.job_id_str,
        source="greenhouse",
        target_url="https://boards.greenhouse.io/techcorp/jobs/104",
        status=BrowserTaskStatus.SUBMISSION_RUNNING,
        assigned_device_id=assigned_dev,
        worker_id=worker,
        execution_mode="LOCAL_INTERACTIVE",
    )
    task_repo.create(task)

    resp = client.post(
        f"/api/agent/tasks/{task.task_id}/complete",
        headers={"X-Device-Token": device_token},
        json={
            "task_id": task.task_id,
            "employer_confirmation_signal": "Your application has been received. Thank you!",
            "submission_reference": f"CONF-{ownership_setup}",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"
    assert resp.json()["submission_reference"] == f"CONF-{ownership_setup}"


def test_employer_confirmation_signal_required(client, in_memory_db):
    """Employer confirmation signal must be non-empty string."""
    device_id, device_token = _pair_device(client, "SignalDevice")
    app_record = _create_job_and_application(in_memory_db, "app-signal-01", "job-signal-01")

    task_repo = BrowserTaskRepository(in_memory_db)
    task = BrowserTaskModel(
        task_id="task-signal-01",
        application_id=app_record.application_id,
        job_id=app_record.job_id_str,
        source="greenhouse",
        target_url="https://boards.greenhouse.io/techcorp/jobs/105",
        status=BrowserTaskStatus.SUBMISSION_RUNNING,
        assigned_device_id=device_id,
        execution_mode="LOCAL_INTERACTIVE",
    )
    task_repo.create(task)

    # Empty confirmation signal -> 400 Bad Request
    resp = client.post(
        f"/api/agent/tasks/{task.task_id}/complete",
        headers={"X-Device-Token": device_token},
        json={
            "task_id": task.task_id,
            "employer_confirmation_signal": "",
        },
    )
    assert resp.status_code == 400
    assert "Employer confirmation signal must be provided" in resp.json()["detail"]


def test_successful_completion_and_idempotency(client, in_memory_db):
    """
    Test successful initial completion and idempotency of repeated completion requests.
    Repeated completion must:
    - Return same 200 response with status COMPLETED and original submission reference
    - Leave application.submitted_at unchanged
    - Leave application.status as APPLIED
    - NOT create additional SUBMITTED lifecycle events
    - NOT append duplicate audit events
    """
    device_id, device_token = _pair_device(client, "IdempotentDevice")
    app_record = _create_job_and_application(in_memory_db, "app-idem-01", "job-idem-01")

    task_repo = BrowserTaskRepository(in_memory_db)
    app_repo = ApplicationRepository(in_memory_db)

    task = BrowserTaskModel(
        task_id="task-idem-01",
        application_id=app_record.application_id,
        job_id=app_record.job_id_str,
        source="greenhouse",
        target_url="https://boards.greenhouse.io/techcorp/jobs/106",
        status=BrowserTaskStatus.SUBMISSION_RUNNING,
        worker_id=f"device:{device_id}",
        execution_mode="LOCAL_INTERACTIVE",
    )
    task_repo.create(task)

    payload = {
        "task_id": task.task_id,
        "employer_confirmation_signal": "Application submitted successfully! Ref #EMP-9988",
        "submission_reference": "EMP-9988",
        "evidence_notes": "Captured confirmation page with reference number",
    }

    # First completion call
    resp1 = client.post(
        f"/api/agent/tasks/{task.task_id}/complete",
        headers={"X-Device-Token": device_token},
        json=payload,
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["success"] is True
    assert data1["status"] == "COMPLETED"
    assert data1["submission_reference"] == "EMP-9988"

    # Verify task and application state after first completion
    task_after_1 = task_repo.get_by_task_id(task.task_id)
    assert task_after_1.status == BrowserTaskStatus.COMPLETED
    audit_events_count_1 = len(task_after_1.audit_events or [])
    assert audit_events_count_1 >= 1

    app_after_1 = app_repo.get_by_application_id(app_record.application_id)
    assert app_after_1.status == ApplicationStatus.APPLIED
    assert app_after_1.submitted_at is not None
    original_submitted_at = app_after_1.submitted_at
    original_applied_at = app_after_1.applied_at

    # Count lifecycle tracking events for this application
    tracking_events_1 = in_memory_db.query(ApplicationEventModel).filter(
        ApplicationEventModel.application_id == app_record.application_id,
        ApplicationEventModel.event_type == "SUBMITTED",
    ).all()
    assert len(tracking_events_1) == 1

    # Second completion call (idempotent retry)
    resp2 = client.post(
        f"/api/agent/tasks/{task.task_id}/complete",
        headers={"X-Device-Token": device_token},
        json=payload,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["success"] is True
    assert data2["status"] == "COMPLETED"
    assert data2["submission_reference"] == "EMP-9988"

    # Third completion call (idempotent retry with slightly different notes, original ref preserved)
    resp3 = client.post(
        f"/api/agent/tasks/{task.task_id}/complete",
        headers={"X-Device-Token": device_token},
        json={
            "task_id": task.task_id,
            "employer_confirmation_signal": "Application submitted successfully! Ref #EMP-9988",
            "submission_reference": "EMP-9988-retry",
            "evidence_notes": "Retry after connection hiccup",
        },
    )
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["success"] is True
    assert data3["status"] == "COMPLETED"
    # Preserves original submission reference recorded in the first audit event
    assert data3["submission_reference"] == "EMP-9988"

    # Verify idempotency invariants:
    # 1. submitted_at and applied_at unchanged
    app_after_retries = app_repo.get_by_application_id(app_record.application_id)
    assert app_after_retries.status == ApplicationStatus.APPLIED
    assert app_after_retries.submitted_at == original_submitted_at
    assert app_after_retries.applied_at == original_applied_at

    # 2. No additional SUBMITTED lifecycle tracking events
    tracking_events_retries = in_memory_db.query(ApplicationEventModel).filter(
        ApplicationEventModel.application_id == app_record.application_id,
        ApplicationEventModel.event_type == "SUBMITTED",
    ).all()
    assert len(tracking_events_retries) == 1

    # 3. No duplicate completion audit events on task
    task_after_retries = task_repo.get_by_task_id(task.task_id)
    completion_audit_events = [
        e for e in (task_after_retries.audit_events or [])
        if e.get("event") == "submission_completed_verified"
    ]
    assert len(completion_audit_events) == 1
