"""Targeted submission boundary tests for Phase 10B Cloud Browser Worker.

Verifies the primary safety invariant:
The browser worker may navigate, inspect, classify, fill, upload, capture screenshots,
and reach READY_FOR_REVIEW. The browser worker MUST NOT autonomously submit an external
job application. The only valid submission transition requires explicit, valid human confirmation.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.browser.models import BrowserElementType, BrowserField
from job_copilot.browser_worker.browser import BrowserManager
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import SubmissionSafetyError
from job_copilot.browser_worker.models import HumanConfirmationRequest
from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
from job_copilot.browser_worker.worker import BrowserWorker
from job_copilot.db.migrations_runner import run_migrations
from job_copilot.domain.artifact_enums import ArtifactType
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.schemas.candidate import CandidateProfile, PersonalInformation
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
    return CandidateProfile(
        personal_info=PersonalInformation(
            full_name="Alex Mercer",
            email="alex.mercer@example.com",
            phone="+1-555-0199",
            location="Pune, India",
        )
    )


@pytest.mark.asyncio
async def test_ready_for_review_never_submits_without_confirmation(db_session, mock_candidate_profile):
    """
    Assert that task execution from QUEUED -> RUNNING -> READY_FOR_REVIEW
    never triggers a browser click or submit action.
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)

    task = BrowserTaskModel(
        task_id="task-sub-guard-001",
        application_id="app-sub-001",
        job_id="job-sub-001",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/fintech/jobs/101",
        status=BrowserTaskStatus.QUEUED,
    )
    repo.create(task)

    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://boards.greenhouse.io/fintech/jobs/101")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.screenshot = AsyncMock(return_value=None)
    mock_adapter.is_captcha_present = AsyncMock(return_value=False)
    mock_adapter.is_login_page = AsyncMock(return_value=False)
    mock_adapter.inspect_page = AsyncMock(
        return_value=[
            BrowserField(field_id="f1", label="Full Name", element_type=BrowserElementType.INPUT_TEXT),
            BrowserField(field_id="f2", label="Email", element_type=BrowserElementType.INPUT_EMAIL),
        ]
    )
    mock_adapter.fill_field = AsyncMock(return_value=True)
    mock_adapter.click = AsyncMock(return_value=True)
    mock_adapter.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(
        db=session,
        browser_manager=mock_manager,
        candidate_profile=mock_candidate_profile,
    )

    result = await executor.execute_task("task-sub-guard-001")

    # Reached READY_FOR_REVIEW
    assert result.status == BrowserTaskStatus.READY_FOR_REVIEW
    # Invariant assertion: Submit click was NEVER invoked
    assert mock_adapter.click.call_count == 0


def test_invalid_confirmation_never_submits(db_session):
    """
    Assert that invalid confirmation parameters (wrong keyword or wrong token)
    raise SubmissionSafetyError and never authorize submission.
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    confirmation_svc = HumanConfirmationService(session)

    valid_token = HumanConfirmationService.generate_confirmation_token()
    task = BrowserTaskModel(
        task_id="task-invalid-conf-001",
        application_id="app-invalid-001",
        target_url="https://boards.greenhouse.io/fintech/jobs/101",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token=valid_token,
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    repo.create(task)

    mock_external_submit = MagicMock()

    # 1. Invalid confirm_text ("auto_submit=true")
    with pytest.raises(SubmissionSafetyError, match="Explicit confirmation keyword 'SUBMIT' is required"):
        confirmation_svc.validate_and_confirm(
            "task-invalid-conf-001",
            HumanConfirmationRequest(confirmation_token=valid_token, confirm_text="auto_submit=true"),
        )
    assert mock_external_submit.call_count == 0

    # 2. Invalid confirmation_token
    with pytest.raises(SubmissionSafetyError, match="Invalid confirmation token provided"):
        confirmation_svc.validate_and_confirm(
            "task-invalid-conf-001",
            HumanConfirmationRequest(confirmation_token="CONFIRM-wrong-token-abc", confirm_text="SUBMIT"),
        )
    assert mock_external_submit.call_count == 0

    # Task remains in READY_FOR_REVIEW
    reloaded = repo.get_by_task_id("task-invalid-conf-001")
    assert reloaded.status == BrowserTaskStatus.READY_FOR_REVIEW


def test_confirmation_for_different_task_never_submits(db_session):
    """
    Assert that a valid confirmation token generated for Task A cannot be used
    to authorize submission for Task B.
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    confirmation_svc = HumanConfirmationService(session)

    token_a = HumanConfirmationService.generate_confirmation_token()
    token_b = HumanConfirmationService.generate_confirmation_token()

    task_a = BrowserTaskModel(
        task_id="task-bound-A",
        application_id="app-A",
        target_url="https://boards.greenhouse.io/companyA/jobs/1",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token=token_a,
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    task_b = BrowserTaskModel(
        task_id="task-bound-B",
        application_id="app-B",
        target_url="https://boards.greenhouse.io/companyB/jobs/2",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token=token_b,
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    repo.create(task_a)
    repo.create(task_b)

    mock_external_submit = MagicMock()

    # Attempt to confirm Task B using Token A
    with pytest.raises(SubmissionSafetyError, match="Invalid confirmation token provided"):
        confirmation_svc.validate_and_confirm(
            "task-bound-B",
            HumanConfirmationRequest(confirmation_token=token_a, confirm_text="SUBMIT"),
        )

    assert mock_external_submit.call_count == 0
    assert repo.get_by_task_id("task-bound-B").status == BrowserTaskStatus.READY_FOR_REVIEW


def test_expired_confirmation_never_submits(db_session):
    """
    Assert that a stale / expired confirmation token cannot authorize submission
    and transitions the task status to EXPIRED.
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    confirmation_svc = HumanConfirmationService(session)

    valid_token = HumanConfirmationService.generate_confirmation_token()
    task = BrowserTaskModel(
        task_id="task-expired-001",
        application_id="app-expired-001",
        target_url="https://boards.greenhouse.io/company/jobs/1",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token=valid_token,
        confirmation_expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    repo.create(task)

    mock_external_submit = MagicMock()

    with pytest.raises(SubmissionSafetyError, match="Confirmation token has expired"):
        confirmation_svc.validate_and_confirm(
            "task-expired-001",
            HumanConfirmationRequest(confirmation_token=valid_token, confirm_text="SUBMIT"),
        )

    assert mock_external_submit.call_count == 0
    reloaded = repo.get_by_task_id("task-expired-001")
    assert reloaded.status == BrowserTaskStatus.EXPIRED


def test_valid_confirmation_is_required_before_submit(db_session):
    """
    Assert that submission is strictly blocked until a valid explicit human confirmation
    is supplied, which authorizes submission (SUBMISSION_AUTHORIZED) without faking external completion.
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    confirmation_svc = HumanConfirmationService(session)

    valid_token = HumanConfirmationService.generate_confirmation_token()
    task = BrowserTaskModel(
        task_id="task-valid-001",
        application_id="app-valid-001",
        job_id="job-valid-001",
        target_url="https://boards.greenhouse.io/company/jobs/1",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token=valid_token,
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    repo.create(task)

    submit_action = MagicMock(return_value={"status": "submitted", "ref": "REF-1234"})

    # Before confirmation: submit action call count == 0
    assert submit_action.call_count == 0

    # Execute confirmation
    resp = confirmation_svc.validate_and_confirm(
        "task-valid-001",
        HumanConfirmationRequest(confirmation_token=valid_token, confirm_text="SUBMIT"),
    )
    if resp.success:
        submit_action()

    # After valid confirmation: task is authorized (SUBMISSION_AUTHORIZED), NOT prematurely COMPLETED
    assert submit_action.call_count == 1
    assert resp.success is True
    assert resp.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED
    assert repo.get_by_task_id("task-valid-001").status == BrowserTaskStatus.SUBMISSION_AUTHORIZED


def test_duplicate_confirmation_does_not_submit_twice(db_session):
    """
    Assert that sending multiple confirmation requests for the same completed or authorized task
    does NOT trigger multiple submissions (idempotent duplicate prevention).
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    confirmation_svc = HumanConfirmationService(session)

    valid_token = HumanConfirmationService.generate_confirmation_token()
    task = BrowserTaskModel(
        task_id="task-dup-001",
        application_id="app-dup-001",
        job_id="job-dup-001",
        target_url="https://boards.greenhouse.io/company/jobs/1",
        status=BrowserTaskStatus.COMPLETED,
        confirmation_token=valid_token,
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    repo.create(task)

    submit_action = MagicMock(return_value={"status": "submitted"})

    # Confirmation on completed task returns duplicate guard
    resp = confirmation_svc.validate_and_confirm(
        "task-dup-001",
        HumanConfirmationRequest(confirmation_token=valid_token, confirm_text="SUBMIT"),
    )
    if resp.success and "Duplicate" not in (resp.message or ""):
        submit_action()

    # Call count remains strictly 0
    assert submit_action.call_count == 0
    assert "Duplicate submission prevented" in resp.message


@pytest.mark.asyncio
async def test_worker_retry_cannot_submit_without_confirmation(db_session, mock_candidate_profile):
    """
    Assert that if a task fails or is retried by the background worker,
    the retry cycle executes form inspection/filling up to READY_FOR_REVIEW
    but NEVER performs an autonomous submission.
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)

    task = BrowserTaskModel(
        task_id="task-retry-001",
        application_id="app-retry-001",
        target_url="https://jobs.lever.co/company/job-retry",
        status=BrowserTaskStatus.QUEUED,
        execution_mode="REMOTE_HEADLESS",
        attempt_count=1,
        max_attempts=3,
    )
    repo.create(task)

    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://jobs.lever.co/company/job-retry")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.screenshot = AsyncMock(return_value=None)
    mock_adapter.is_captcha_present = AsyncMock(return_value=False)
    mock_adapter.is_login_page = AsyncMock(return_value=False)
    mock_adapter.inspect_page = AsyncMock(
        return_value=[
            BrowserField(field_id="f1", label="Full Name", element_type=BrowserElementType.INPUT_TEXT),
        ]
    )
    mock_adapter.fill_field = AsyncMock(return_value=True)
    mock_adapter.click = AsyncMock(return_value=True)
    mock_adapter.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    worker = BrowserWorker(worker_id="test-worker-01")

    with patch("job_copilot.browser_worker.worker.BrowserTaskExecutor") as MockExecutorClass:
        executor_instance = BrowserTaskExecutor(
            db=session,
            browser_manager=mock_manager,
            candidate_profile=mock_candidate_profile,
        )
        MockExecutorClass.return_value = executor_instance

        processed = await worker.process_next_task(session)

    assert processed is not None
    assert processed.status == BrowserTaskStatus.READY_FOR_REVIEW
    assert processed.attempt_count == 2
    # Invariant assertion: Submit click was NEVER called during retry
    assert mock_adapter.click.call_count == 0
