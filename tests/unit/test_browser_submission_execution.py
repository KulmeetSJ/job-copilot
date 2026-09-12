"""Tests for safe browser-executed submission, verification, blocker intervention, and tracking safety."""

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
from job_copilot.db.migrations_runner import run_migrations
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.application import Application
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.schemas.candidate import CandidateProfile, PersonalInformation
from job_copilot.services.artifact_service import ArtifactService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.storage.local_store import LocalArtifactStore
from job_copilot.tracking.models import ApplicationLifecycleStatus


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
    return CandidateProfile(
        personal_info=PersonalInformation(
            full_name="Alex Mercer",
            email="alex.mercer@example.com",
            phone="+1-555-0199",
            location="Pune, India",
        )
    )


@pytest.mark.asyncio
async def test_authorized_task_executes_browser_submission_verified(db_session, mock_candidate_profile):
    """
    1. Human confirms -> SUBMISSION_AUTHORIZED
    2. execute_submission_task clicks submit on employer form
    3. Employer success response detected
    4. Screenshot artifact captured
    5. Task becomes COMPLETED and Application becomes APPLIED.
    """
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)
    app_repo = ApplicationRepository(session)

    # Create job, application, task
    job = Job(
        job_id="job-verified-101",
        title="Software Engineer",
        company="Fintech Corp",
        description="Engineering role description",
        source="greenhouse",
        url="https://boards.greenhouse.io/fintech/jobs/101",
    )
    session.add(job)
    session.flush()

    app = Application(
        application_id="app-verified-101",
        job_id_str="job-verified-101",
        job_id=job.id,
        company="Fintech Corp",
        role="Software Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
        canonical_job_url="https://boards.greenhouse.io/fintech/jobs/101",
    )
    session.add(app)
    session.commit()

    token = HumanConfirmationService.generate_confirmation_token()
    task = BrowserTaskModel(
        task_id="task-verified-101",
        application_id="app-verified-101",
        job_id="job-verified-101",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/fintech/jobs/101",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token=token,
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    task_repo.create(task)

    # 1. Human confirms
    confirm_svc = HumanConfirmationService(session)
    confirm_resp = confirm_svc.validate_and_confirm(
        "task-verified-101",
        HumanConfirmationRequest(confirmation_token=token, confirm_text="SUBMIT"),
        application_id="app-verified-101",
    )
    assert confirm_resp.success is True
    assert confirm_resp.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED
    assert app_repo.get_by_application_id("app-verified-101").status == ApplicationStatus.READY_TO_APPLY

    # 2. Mock Playwright adapter with genuine employer success signal
    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://boards.greenhouse.io/fintech/jobs/101")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.get_current_url = AsyncMock(return_value="https://boards.greenhouse.io/fintech/jobs/101/confirmation")
    mock_adapter.get_page_content = AsyncMock(return_value="Thank you for applying! Your application has been submitted.")
    mock_adapter.screenshot = AsyncMock(return_value=None)
    mock_adapter.is_captcha_present = AsyncMock(return_value=False)
    mock_adapter.is_login_page = AsyncMock(return_value=False)
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

    # 3. Execute submission task
    res_task = await executor.execute_submission_task("task-verified-101")

    # Invariants
    assert mock_adapter.click.call_count >= 1
    assert res_task.status == BrowserTaskStatus.COMPLETED
    assert app_repo.get_by_application_id("app-verified-101").status == ApplicationStatus.APPLIED
    assert app_repo.get_by_application_id("app-verified-101").submitted_at is not None

    events = app_repo.get_events("app-verified-101")
    event_types = [e.event_type for e in events]
    assert "SUBMITTED" in event_types


@pytest.mark.asyncio
async def test_submission_unverified_on_ambiguous_response(db_session, mock_candidate_profile):
    """
    If submit button is clicked but the employer portal does not show an explicit success signal,
    task becomes SUBMISSION_UNVERIFIED and application is NOT marked APPLIED.
    """
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)
    app_repo = ApplicationRepository(session)

    job = Job(job_id="job-unverified-01", title="DevOps", company="Cloud Corp", description="Cloud ops role", source="greenhouse", url="https://boards.greenhouse.io/cloud/jobs/201")
    session.add(job)
    session.flush()
    app = Application(application_id="app-unverified-01", job_id_str="job-unverified-01", job_id=job.id, company="Cloud Corp", role="DevOps", status=ApplicationStatus.READY_TO_APPLY)
    session.add(app)
    session.commit()
    session.commit()

    task = BrowserTaskModel(
        task_id="task-unverified-01",
        application_id="app-unverified-01",
        job_id="job-unverified-01",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/cloud/jobs/201",
        status=BrowserTaskStatus.SUBMISSION_AUTHORIZED,
    )
    task_repo.create(task)

    # Mock adapter where submit was clicked, but page URL and text remained generic/unchanged
    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://boards.greenhouse.io/cloud/jobs/201")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.get_current_url = AsyncMock(return_value="https://boards.greenhouse.io/cloud/jobs/201")
    mock_adapter.get_page_content = AsyncMock(return_value="Please fill all fields. Job details:")
    mock_adapter.screenshot = AsyncMock(return_value=None)
    mock_adapter.is_captcha_present = AsyncMock(return_value=False)
    mock_adapter.is_login_page = AsyncMock(return_value=False)
    mock_adapter.click = AsyncMock(return_value=True)
    mock_adapter.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(db=session, browser_manager=mock_manager, candidate_profile=mock_candidate_profile)
    res_task = await executor.execute_submission_task("task-unverified-01")

    # Invariants
    assert res_task.status == BrowserTaskStatus.SUBMISSION_UNVERIFIED
    assert "could not be verified" in (res_task.pause_reason or "")
    # Application MUST NOT be marked APPLIED
    assert app_repo.get_by_application_id("app-unverified-01").status == ApplicationStatus.READY_TO_APPLY


@pytest.mark.asyncio
async def test_blocker_captcha_pauses_in_captcha_required(db_session, mock_candidate_profile):
    """
    If CAPTCHA is detected during submission, worker pauses in CAPTCHA_REQUIRED
    and does NOT submit the form.
    """
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)
    app_repo = ApplicationRepository(session)

    task = BrowserTaskModel(
        task_id="task-captcha-block-01",
        application_id="app-captcha-01",
        job_id="job-captcha-01",
        source="lever",
        target_url="https://jobs.lever.co/security/jobs/301",
        status=BrowserTaskStatus.SUBMISSION_AUTHORIZED,
    )
    task_repo.create(task)

    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://jobs.lever.co/security/jobs/301")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.is_captcha_present = AsyncMock(return_value=True)  # CAPTCHA challenge detected
    mock_adapter.click = AsyncMock(return_value=True)
    mock_adapter.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(db=session, browser_manager=mock_manager, candidate_profile=mock_candidate_profile)
    res_task = await executor.execute_submission_task("task-captcha-block-01")

    assert res_task.status == BrowserTaskStatus.CAPTCHA_REQUIRED
    # Submit click was NEVER called
    assert mock_adapter.click.call_count == 0


@pytest.mark.asyncio
async def test_resume_task_continues_submission(db_session, mock_candidate_profile):
    """
    When user intervenes and resumes a CAPTCHA_REQUIRED task,
    it re-executes submission from current state.
    """
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)

    task = BrowserTaskModel(
        task_id="task-resume-01",
        application_id="app-resume-01",
        job_id="job-resume-01",
        source="lever",
        target_url="https://jobs.lever.co/security/jobs/301",
        status=BrowserTaskStatus.CAPTCHA_REQUIRED,
        audit_events=[{"event": "human_submission_authorized", "timestamp": "2026-09-12T10:00:00Z"}],
    )
    task_repo.create(task)

    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://jobs.lever.co/security/jobs/301")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.is_captcha_present = AsyncMock(return_value=False)  # User solved CAPTCHA
    mock_adapter.is_login_page = AsyncMock(return_value=False)
    mock_adapter.get_current_url = AsyncMock(return_value="https://jobs.lever.co/security/jobs/301/thanks")
    mock_adapter.get_page_content = AsyncMock(return_value="Application submitted successfully.")
    mock_adapter.screenshot = AsyncMock(return_value=None)
    mock_adapter.click = AsyncMock(return_value=True)
    mock_adapter.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(db=session, browser_manager=mock_manager, candidate_profile=mock_candidate_profile)
    res_task = await executor.resume_task("task-resume-01")

    assert res_task.status == BrowserTaskStatus.COMPLETED
    assert mock_adapter.click.call_count >= 1


def test_register_submission_never_calls_prepare_application():
    """
    Regression test: TrackingService.register_submission must NEVER call
    prep_service.prepare_application synchronously.
    """
    mock_prep = MagicMock()
    mock_prep.get_application_package.return_value = None  # Package missing from disk

    mock_store = MagicMock()
    mock_store.get_application_by_job_id.return_value = None

    tracking_svc = TrackingService(store=mock_store, prep_service=mock_prep)

    tracking_svc.register_submission(job_id="test-fast-job-01")

    # Invariant: prepare_application must NOT be called
    assert mock_prep.prepare_application.call_count == 0
