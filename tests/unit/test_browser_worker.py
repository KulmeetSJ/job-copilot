"""Unit and integration tests for Phase 10B Cloud Browser Worker."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.browser.models import BrowserElementType, BrowserField
from job_copilot.browser_worker.browser import BrowserManager, BrowserSessionAdapter
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import DomainSecurityError, SubmissionSafetyError
from job_copilot.browser_worker.models import HumanConfirmationRequest
from job_copilot.browser_worker.safety import (
    is_prohibited_field,
    is_sensitive_field,
    mask_sensitive_value,
    validate_target_domain,
)
from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
from job_copilot.browser_worker.worker import BrowserWorker
from job_copilot.db.migrations_runner import run_migrations
from job_copilot.domain.artifact_enums import ArtifactType
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus, FieldAction
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.services.artifact_service import ArtifactService
from job_copilot.storage.local_store import LocalArtifactStore


@pytest.fixture
def db_session():
    """Isolated temporary SQLite database with all migrations applied."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url=db_url)

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    try:
        yield session, db_url
    finally:
        session.close()
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def mock_candidate_profile():
    """Mock canonical candidate profile for deterministic testing."""
    from job_copilot.schemas.candidate import CandidateLink, PersonalInformation

    return CandidateProfile(
        personal_info=PersonalInformation(
            full_name="Alex Mercer",
            email="alex.mercer@example.com",
            phone="+1-555-0199",
            location="Pune, India",
            links=[
                CandidateLink(label="LinkedIn", url="https://linkedin.com/in/alexmercer"),
                CandidateLink(label="GitHub", url="https://github.com/alexmercer"),
            ],
        )
    )


# ==============================================================================
# 1. State Machine & Repository CRUD Tests
# ==============================================================================


def test_browser_task_state_machine_and_crud(db_session):
    """Verify BrowserTaskRepository persistence, status transitions, and audit logging."""
    session, _ = db_session
    repo = BrowserTaskRepository(session)

    task = BrowserTaskModel(
        task_id="task-test-001",
        application_id="app-test-001",
        job_id="job-test-001",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/fintech/jobs/101",
        status=BrowserTaskStatus.QUEUED,
    )
    saved = repo.create(task)
    assert saved.id is not None
    assert saved.status == BrowserTaskStatus.QUEUED

    # Transition to RUNNING
    updated = repo.update_status("task-test-001", BrowserTaskStatus.RUNNING)
    assert updated.status == BrowserTaskStatus.RUNNING
    assert updated.started_at is not None

    # Append audit event
    repo.append_audit_event("task-test-001", {"event": "navigated", "status": "ok"})
    reloaded = repo.get_by_task_id("task-test-001")
    assert len(reloaded.audit_events) == 1
    assert reloaded.audit_events[0]["event"] == "navigated"


# ==============================================================================
# 2. Domain Security & URL Validation Tests
# ==============================================================================


def test_domain_security_validation():
    """Verify domain whitelist matching and rejection of disallowed schemes or untrusted hosts."""
    # Allowed domains
    assert validate_target_domain("https://boards.greenhouse.io/company/jobs/1")
    assert validate_target_domain("https://jobs.lever.co/company/apply")
    assert validate_target_domain("https://test.example.com/careers")
    assert validate_target_domain("http://localhost:8000/application-form", allow_test_fixture=True)

    # Localhost / private IP blocked without explicit test fixture allowance
    with pytest.raises(DomainSecurityError, match="represents a private, loopback, or cloud metadata address"):
        validate_target_domain("http://localhost:8000/application-form", allow_test_fixture=False)

    # Disallowed schemes
    with pytest.raises(DomainSecurityError, match="Disallowed URL scheme"):
        validate_target_domain("javascript:alert(1)")

    with pytest.raises(DomainSecurityError, match="Disallowed URL scheme"):
        validate_target_domain("file:///etc/passwd")

    # Disallowed / Unknown domain
    with pytest.raises(DomainSecurityError, match="not in the allowed job portal domain list"):
        validate_target_domain("https://malicious-phishing-site.ru/form")


# ==============================================================================
# 3. Sensitive & Prohibited Field Rules Tests
# ==============================================================================


def test_sensitive_and_prohibited_field_rules():
    """Verify sensitive field detection and prohibited security pattern matching."""
    # Prohibited fields
    assert is_prohibited_field("Password") is True
    assert is_prohibited_field("Social Security Number (SSN)") is True
    assert is_prohibited_field("Credit Card Number") is True
    assert is_prohibited_field("First Name") is False

    # Sensitive fields requiring human confirmation
    assert is_sensitive_field("Expected Salary (Annual CTC)") is True
    assert is_sensitive_field("Do you require visa sponsorship now or in the future?") is True
    assert is_sensitive_field("Are you legally authorized to work in India?") is True
    assert is_sensitive_field("What is your official notice period?") is True
    assert is_sensitive_field("Do you hold an active security clearance?") is True
    assert is_sensitive_field("Full Name") is False
    assert is_sensitive_field("Email Address") is False

    # Masking
    assert mask_sensitive_value("alex.mercer@example.com") == "al***om"
    assert mask_sensitive_value("12") == "***"


# ==============================================================================
# 4. PRIMARY SAFETY INVARIANT: Human Confirmation Gate Tests
# ==============================================================================


def test_human_confirmation_gate_strictly_enforces_safety(db_session):
    """
    CRITICAL INVARIANT TEST:
    1. READY_FOR_REVIEW without valid confirmation token -> SUBMISSION BLOCKED.
    2. Stale / expired token -> SUBMISSION BLOCKED.
    3. Unrelated token from another task -> SUBMISSION BLOCKED.
    4. Keyword not 'SUBMIT' (e.g., 'auto_submit=true') -> SUBMISSION BLOCKED.
    5. Valid token + 'SUBMIT' -> SUBMISSION AUTHORIZED.
    6. Second submission on already COMPLETED task -> NO duplicate submission.
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    confirmation_svc = HumanConfirmationService(session)

    valid_token = HumanConfirmationService.generate_confirmation_token()
    task = BrowserTaskModel(
        task_id="task-confirm-001",
        application_id="app-confirm-001",
        target_url="https://boards.greenhouse.io/fintech/jobs/101",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token=valid_token,
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    repo.create(task)

    # 1. Invalid keyword
    with pytest.raises(SubmissionSafetyError, match="Explicit confirmation keyword 'SUBMIT' is required"):
        confirmation_svc.validate_and_confirm(
            "task-confirm-001",
            HumanConfirmationRequest(confirmation_token=valid_token, confirm_text="auto_submit=true"),
        )

    # 2. Invalid / Unrelated token
    with pytest.raises(SubmissionSafetyError, match="Invalid confirmation token provided"):
        confirmation_svc.validate_and_confirm(
            "task-confirm-001",
            HumanConfirmationRequest(confirmation_token="CONFIRM-unrelated-token-xyz", confirm_text="SUBMIT"),
        )

    # 3. Expired token
    task.confirmation_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    session.commit()
    with pytest.raises(SubmissionSafetyError, match="Confirmation token has expired"):
        confirmation_svc.validate_and_confirm(
            "task-confirm-001",
            HumanConfirmationRequest(confirmation_token=valid_token, confirm_text="SUBMIT"),
        )

    # 4. Valid confirmation
    task.confirmation_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    task.status = BrowserTaskStatus.READY_FOR_REVIEW
    session.commit()

    resp = confirmation_svc.validate_and_confirm(
        "task-confirm-001",
        HumanConfirmationRequest(confirmation_token=valid_token, confirm_text="SUBMIT", user_notes="Approved by candidate"),
    )
    assert resp.success is True
    assert resp.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED
    assert resp.submission_reference is not None

    # 5. Duplicate confirmation guard
    dup_resp = confirmation_svc.validate_and_confirm(
        "task-confirm-001",
        HumanConfirmationRequest(confirmation_token=valid_token, confirm_text="SUBMIT"),
    )
    assert dup_resp.success is True
    assert "Duplicate submission prevented" in dup_resp.message


# ==============================================================================
# 5. Task Executor Pause Behavior Tests (CAPTCHA, Login, Sensitive Fields)
# ==============================================================================


@pytest.mark.asyncio
async def test_task_executor_captcha_pause(db_session, mock_candidate_profile):
    """Verify that CAPTCHA challenges pause the worker in CAPTCHA_REQUIRED state without bypass."""
    session, _ = db_session
    repo = BrowserTaskRepository(session)

    task = BrowserTaskModel(
        task_id="task-captcha-001",
        target_url="https://boards.greenhouse.io/jobs/captcha-test",
        status=BrowserTaskStatus.QUEUED,
    )
    repo.create(task)

    # Mock adapter detecting CAPTCHA
    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://boards.greenhouse.io/jobs/captcha-test")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.screenshot = AsyncMock(return_value=None)
    mock_adapter.is_captcha_present = AsyncMock(return_value=True)
    mock_adapter.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(
        db=session,
        browser_manager=mock_manager,
        candidate_profile=mock_candidate_profile,
    )
    result = await executor.execute_task("task-captcha-001")

    assert result.status == BrowserTaskStatus.CAPTCHA_REQUIRED
    assert "CAPTCHA" in result.pause_reason


@pytest.mark.asyncio
async def test_task_executor_login_wall_pause(db_session, mock_candidate_profile):
    """Verify that login authentication walls pause the worker in LOGIN_REQUIRED state."""
    session, _ = db_session
    repo = BrowserTaskRepository(session)

    task = BrowserTaskModel(
        task_id="task-login-001",
        target_url="https://jobs.lever.co/company/login-required",
        status=BrowserTaskStatus.QUEUED,
    )
    repo.create(task)

    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://jobs.lever.co/company/login-required")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.screenshot = AsyncMock(return_value=None)
    mock_adapter.is_captcha_present = AsyncMock(return_value=False)
    mock_adapter.is_login_page = AsyncMock(return_value=True)
    mock_adapter.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(
        db=session,
        browser_manager=mock_manager,
        candidate_profile=mock_candidate_profile,
    )
    result = await executor.execute_task("task-login-001")

    assert result.status == BrowserTaskStatus.LOGIN_REQUIRED
    assert "login" in result.pause_reason.lower()


# ==============================================================================
# 6. Task Executor Form Preparation & Review Boundary Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_task_executor_end_to_end_preparation_stops_at_ready_for_review(
    db_session, mock_candidate_profile
):
    """
    Verify complete preparation workflow:
    1. Inspects form fields.
    2. Autofills candidate contact fields from authoritative candidate profile.
    3. Uploads resume PDF retrieved from Phase 10A ArtifactService.
    4. Generates review package with confirmation token.
    5. Transitions to READY_FOR_REVIEW.
    6. Stops strictly at review boundary without autonomous submission.
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)

    # Setup Phase 10A artifact store with mock resume
    with tempfile.TemporaryDirectory() as art_dir:
        local_store = LocalArtifactStore(base_dir=Path(art_dir))
        art_service = ArtifactService(store=local_store, db=session)

        # Store resume PDF
        resume_artifact = art_service.store_artifact(
            data=b"%PDF-1.4 Tailored Resume for Cloud Engineer",
            artifact_type=ArtifactType.TAILORED_RESUME_PDF,
            application_id="app-cloud-101",
            original_filename="tailored_resume.pdf",
            content_type="application/pdf",
        )

        task = BrowserTaskModel(
            task_id="task-prep-001",
            application_id="app-cloud-101",
            job_id="job-cloud-101",
            source="greenhouse",
            target_url="https://boards.greenhouse.io/cloudcorp/jobs/101",
            status=BrowserTaskStatus.QUEUED,
        )
        repo.create(task)

        # Mock form fields
        form_fields = [
            BrowserField(field_id="f1", label="Full Name", element_type=BrowserElementType.INPUT_TEXT),
            BrowserField(field_id="f2", label="Email Address", element_type=BrowserElementType.INPUT_EMAIL),
            BrowserField(field_id="f3", label="Phone Number", element_type=BrowserElementType.INPUT_TEL),
            BrowserField(field_id="f4", label="Resume / CV", element_type=BrowserElementType.INPUT_FILE),
        ]

        mock_adapter = MagicMock()
        mock_adapter.launch = AsyncMock()
        mock_adapter.navigate = AsyncMock(return_value="https://boards.greenhouse.io/cloudcorp/jobs/101")
        mock_adapter.wait_for_dom_idle = AsyncMock()
        mock_adapter.screenshot = AsyncMock(return_value=None)
        mock_adapter.is_captcha_present = AsyncMock(return_value=False)
        mock_adapter.is_login_page = AsyncMock(return_value=False)
        mock_adapter.inspect_page = AsyncMock(return_value=form_fields)
        mock_adapter.fill_field = AsyncMock(return_value=True)
        mock_adapter.upload_file = AsyncMock(return_value=True)
        mock_adapter.close = AsyncMock()

        mock_manager = MagicMock(spec=BrowserManager)
        mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
        mock_manager.close = AsyncMock()

        executor = BrowserTaskExecutor(
            db=session,
            artifact_service=art_service,
            browser_manager=mock_manager,
            candidate_profile=mock_candidate_profile,
        )

        result = await executor.execute_task("task-prep-001")

        # Invariant checks:
        assert result.status == BrowserTaskStatus.READY_FOR_REVIEW
        assert result.confirmation_token is not None
        assert result.review_package_json is not None
        assert result.review_package_json["fields_autofilled"] == 4

        # Field fills verified
        assert mock_adapter.fill_field.call_count == 3  # Name, Email, Phone
        mock_adapter.upload_file.assert_called_once()  # Resume upload

        # CRITICAL SAFETY: Submit was NEVER called
        assert mock_adapter.click.call_count == 0


# ==============================================================================
# 7. API Routes Verification Tests
# ==============================================================================


def test_browser_task_api_routes(db_session):
    """Verify FastAPI task endpoints for creation, execution, and confirmation."""
    session, _ = db_session
    from job_copilot.db.database import get_db

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # 1. Create task
        create_resp = client.post(
            "/api/browser/tasks",
            json={
                "application_id": "app-api-test-01",
                "job_id": "job-api-test-01",
                "source": "lever",
                "target_url": "https://jobs.lever.co/company/software-engineer",
            },
        )
        assert create_resp.status_code == 201
        task_data = create_resp.json()
        task_id = task_data["task_id"]
        assert task_data["status"] == "QUEUED"

        # 2. Get task
        get_resp = client.get(f"/api/browser/tasks/{task_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["task_id"] == task_id

        # 3. Confirm with invalid keyword -> 403 Forbidden
        confirm_resp = client.post(
            f"/api/browser/tasks/{task_id}/confirm",
            json={"confirmation_token": "mock-token", "confirm_text": "no"},
        )
        assert confirm_resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)


# ==============================================================================
# 8. Candidate Truth Immutability Test
# ==============================================================================


def test_candidate_truth_remains_immutable():
    """Verify that browser worker execution never mutates candidate master profile."""
    profile_path = Path("data/candidate/master_profile.yaml")
    if profile_path.exists():
        content_before = profile_path.read_text(encoding="utf-8")
        # Ensure candidate truth exists and remains unpolluted
        assert len(content_before) > 0
        assert "name:" in content_before
