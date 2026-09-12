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


def test_browser_worker_atomic_claiming_and_crash_recovery(db_session):
    """
    Assert that BrowserTaskRepository.claim_task provides atomic compare-and-swap
    and recover_stale_running_tasks resets crashed tasks without data loss.
    """
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)

    task = BrowserTaskModel(
        task_id="task-atomic-01",
        application_id="app-atomic-01",
        job_id="job-atomic-01",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/corp/jobs/1",
        status=BrowserTaskStatus.SUBMISSION_AUTHORIZED,
    )
    task_repo.create(task)

    # 1. Worker 1 claims task
    claimed_1 = task_repo.claim_task(
        task_id="task-atomic-01",
        expected_status=BrowserTaskStatus.SUBMISSION_AUTHORIZED,
        new_status=BrowserTaskStatus.SUBMISSION_RUNNING,
        worker_id="worker-001",
    )
    assert claimed_1 is True

    # 2. Worker 2 attempts to claim the same task -> fails (atomic compare-and-swap)
    claimed_2 = task_repo.claim_task(
        task_id="task-atomic-01",
        expected_status=BrowserTaskStatus.SUBMISSION_AUTHORIZED,
        new_status=BrowserTaskStatus.SUBMISSION_RUNNING,
        worker_id="worker-002",
    )
    assert claimed_2 is False

    # 3. Crash recovery simulation (stale task reset)
    task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    session.commit()

    recovered_count = task_repo.recover_stale_running_tasks(timeout_minutes=15)
    assert recovered_count == 1
    reloaded_task = task_repo.get_by_task_id("task-atomic-01")
    assert reloaded_task.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED
    assert "Recovered after worker restart" in reloaded_task.pause_reason


def test_dashboard_service_blocker_and_mastercard_historical_unverified(db_session):
    """
    Assert that DashboardService computes blocker instructions for CAPTCHA/Login/MFA
    and honors Mastercard application app-usr-2a43a63d as external unverified.
    """
    from job_copilot.services.dashboard_service import DashboardService
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)

    # 1. CAPTCHA blocker task
    job = Job(job_id="job-dash-01", title="Engineer", company="Payment Inc", description="Payment eng", source="greenhouse", url="https://boards.greenhouse.io/pay/1")
    session.add(job)
    session.flush()

    app = Application(
        application_id="app-usr-2a43a63d",  # Historical Mastercard application
        job_id_str="job-dash-01",
        job_id=job.id,
        company="Mastercard",
        role="Engineer",
        status=ApplicationStatus.APPLIED,
    )
    session.add(app)
    session.commit()

    task = BrowserTaskModel(
        task_id="task-dash-01",
        application_id="app-usr-2a43a63d",
        job_id="job-dash-01",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/pay/1",
        status=BrowserTaskStatus.CAPTCHA_REQUIRED,
    )
    task_repo.create(task)

    dash_svc = DashboardService(db=session)
    detail = dash_svc.get_application_detail("app-usr-2a43a63d")

    assert detail.blocker_type == "CAPTCHA"
    assert "manual" in detail.blocker_instruction.lower()
    assert detail.can_resume is False
    # Historical Mastercard record must be flagged as unverified
    assert detail.is_external_unverified is True


@pytest.mark.asyncio
async def test_generic_unsafe_selector_pauses_in_human_action_required(db_session, mock_candidate_profile):
    """
    If an unknown or generic site only has ambiguous buttons (Save, Apply Filters, Next, Submit Feedback),
    execute_submission_task MUST NOT click them and must pause in HUMAN_ACTION_REQUIRED.
    """
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)

    task = BrowserTaskModel(
        task_id="task-ambig-01",
        application_id="app-ambig-01",
        job_id="job-ambig-01",
        source="generic",
        target_url="https://example.com/careers/apply",
        status=BrowserTaskStatus.SUBMISSION_AUTHORIZED,
    )
    task_repo.create(task)

    # Page with ambiguous buttons: 'Save Application', 'Apply Filters', 'Next'
    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://example.com/careers/apply")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.get_current_url = AsyncMock(return_value="https://example.com/careers/apply")
    mock_adapter.get_page_content = AsyncMock(return_value="""
        <html><body>
            <button>Save Application</button>
            <button>Apply Filters</button>
            <button>Continue to Profile</button>
            <button>Submit Feedback</button>
            <button>Next</button>
        </body></html>
    """)
    mock_adapter.screenshot = AsyncMock(return_value=None)
    mock_adapter.is_captcha_present = AsyncMock(return_value=False)
    mock_adapter.is_login_page = AsyncMock(return_value=False)
    mock_adapter.click = AsyncMock(return_value=True)
    mock_adapter.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(db=session, browser_manager=mock_manager, candidate_profile=mock_candidate_profile)
    res_task = await executor.execute_submission_task("task-ambig-01")

    # Invariants:
    # 1. Click MUST NEVER be called on ambiguous buttons
    assert mock_adapter.click.call_count == 0
    # 2. Task MUST pause in HUMAN_ACTION_REQUIRED
    assert res_task.status == BrowserTaskStatus.HUMAN_ACTION_REQUIRED
    assert "could not be safely identified" in (res_task.pause_reason or "")


@pytest.mark.asyncio
async def test_linkedin_multi_step_distinguishes_next_from_final_submit():
    """
    LinkedInAdapter must return None when page only contains 'Next' or 'Review'
    and return final selector when page contains 'Submit application'.
    """
    from job_copilot.browser_worker.adapters.linkedin import LinkedInAdapter
    from job_copilot.browser_worker.browser import BrowserSessionAdapter

    adapter = LinkedInAdapter()

    # Case 1: Intermediate step with 'Next'
    mock_adapter_step1 = MagicMock()
    mock_adapter_step1.get_page_content = AsyncMock(return_value="""
        <div data-easy-apply-footer>
            <button>Next</button>
        </div>
    """)
    session_step1 = BrowserSessionAdapter(mock_adapter_step1)
    sel_step1 = await adapter.get_submit_selector(session_step1)
    assert sel_step1 is None

    # Case 2: Final review step with 'Submit application'
    mock_adapter_final = MagicMock()
    mock_adapter_final.get_page_content = AsyncMock(return_value="""
        <div data-easy-apply-footer>
            <button aria-label="Submit application">Submit application</button>
        </div>
    """)
    session_final = BrowserSessionAdapter(mock_adapter_final)
    sel_final = await adapter.get_submit_selector(session_final)
    assert sel_final is not None
    assert "Submit application" in sel_final or "submit application" in sel_final


@pytest.mark.asyncio
async def test_network_drop_post_submit_becomes_unverified_without_retry(db_session, mock_candidate_profile):
    """
    If a network error / timeout occurs after submit is clicked,
    the task becomes SUBMISSION_UNVERIFIED and does NOT auto-retry.
    """
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)
    app_repo = ApplicationRepository(session)

    job = Job(job_id="job-net-01", title="SRE", company="NetCorp", description="SRE role", source="greenhouse", url="https://boards.greenhouse.io/net/1")
    session.add(job)
    session.flush()
    app = Application(application_id="app-net-01", job_id_str="job-net-01", job_id=job.id, company="NetCorp", role="SRE", status=ApplicationStatus.READY_TO_APPLY)
    session.add(app)
    session.commit()

    task = BrowserTaskModel(
        task_id="task-net-01",
        application_id="app-net-01",
        job_id="job-net-01",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/net/1",
        status=BrowserTaskStatus.SUBMISSION_AUTHORIZED,
    )
    task_repo.create(task)

    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://boards.greenhouse.io/net/1")
    mock_adapter.is_captcha_present = AsyncMock(return_value=False)
    mock_adapter.is_login_page = AsyncMock(return_value=False)
    mock_adapter.get_current_url = AsyncMock(return_value="https://boards.greenhouse.io/net/1")
    mock_adapter.get_page_content = AsyncMock(return_value="<html>Submit Application</html>")
    mock_adapter.wait_for_dom_idle = AsyncMock(return_value=None)
    
    # Network dies immediately after click during post-submit wait
    async def mock_click_and_drop(*args, **kwargs):
        mock_adapter.wait_for_dom_idle.side_effect = ConnectionResetError("Network connection aborted by remote host")
        return True

    mock_adapter.click = AsyncMock(side_effect=mock_click_and_drop)
    mock_adapter.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(db=session, browser_manager=mock_manager, candidate_profile=mock_candidate_profile)
    res_task = await executor.execute_submission_task("task-net-01")

    # Invariants:
    assert res_task.status == BrowserTaskStatus.SUBMISSION_UNVERIFIED
    assert "network" in (res_task.pause_reason or "").lower()
    # Application MUST NOT be marked APPLIED
    assert app_repo.get_by_application_id("app-net-01").status == ApplicationStatus.READY_TO_APPLY


def test_stale_task_recovery_with_submit_dispatched_prevents_duplicate_retry(db_session):
    """
    When recover_stale_running_tasks runs on worker restart, if a SUBMISSION_RUNNING task
    had 'submit_click_dispatched' in its audit events, it transitions to SUBMISSION_UNVERIFIED
    (not SUBMISSION_AUTHORIZED), preventing duplicate submissions.
    """
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)

    # Task that crashed after submit click
    task = BrowserTaskModel(
        task_id="task-crash-dispatched",
        application_id="app-crash-01",
        job_id="job-crash-01",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/corp/1",
        status=BrowserTaskStatus.SUBMISSION_RUNNING,
        audit_events=[
            {"event": "submission_running", "timestamp": "2026-09-12T10:00:00Z"},
            {"event": "submit_click_dispatched", "selector": "button#submit_app", "timestamp": "2026-09-12T10:00:05Z"},
        ],
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    task_repo.create(task)

    recovered = task_repo.recover_stale_running_tasks(timeout_minutes=15)
    assert recovered == 1

    reloaded = task_repo.get_by_task_id("task-crash-dispatched")
    assert reloaded.status == BrowserTaskStatus.SUBMISSION_UNVERIFIED
    assert "do not retry automatically" in (reloaded.pause_reason or "").lower()


def test_deterministic_newly_created_mastercard_opportunity_renders_complete_data(db_session):
    """
    Verify that a newly created opportunity with:
    company = Mastercard
    role = Software Engineer
    source = USER_SUBMITTED_URL
    strategy = BACKEND_JAVA
    renders complete data in DashboardService.get_application_detail without legacy/fallback defaults.
    """
    from job_copilot.services.dashboard_service import DashboardService
    from job_copilot.application.models import ApplicationPackage, CoverLetter, CoverLetterValidation, ApplicationAnswer, QuestionClassification


    session, _ = db_session
    app_repo = ApplicationRepository(session)

    job = Job(
        job_id="job-mc-java-001",
        title="Software Engineer",
        company="Mastercard",
        description="Core Java Payments Platform Engineering",
        source="USER_SUBMITTED_URL",
        url="https://mastercard.jobs/software-engineer",
    )
    session.add(job)
    session.flush()

    app = Application(
        application_id="app-mc-java-001",
        job_id_str="job-mc-java-001",
        job_id=job.id,
        company="Mastercard",
        role="Software Engineer",
        source="USER_SUBMITTED_URL",
        resume_strategy="BACKEND_JAVA",
        match_score=88.5,
        recommendation="APPLY",
        status=ApplicationStatus.READY_TO_APPLY,
        canonical_job_url="https://mastercard.jobs/software-engineer",
    )
    session.add(app)
    session.commit()

    # Mock application package from prep_service
    mock_prep = MagicMock()
    mock_pkg = MagicMock()
    mock_pkg.selected_resume_strategy = "BACKEND_JAVA"
    mock_pkg.resume_pdf_path = "/tmp/fake_resume.pdf"
    mock_pkg.resume_tex_path = None
    mock_pkg.cover_letter = CoverLetter(
        job_id="job-mc-java-001",
        company="Mastercard",
        title="Software Engineer",
        letter_text="Dear Mastercard Team, I am writing to express my enthusiasm for the Software Engineer role...",
        subject="Application for Software Engineer - Mastercard",
        word_count=250,
        validation=CoverLetterValidation(is_valid=True, total_words=250),
    )
    mock_pkg.answers = [
        ApplicationAnswer(
            question_id="java_experience",
            question_text="How many years of Java experience do you have?",
            answer="5+ years of enterprise Java in high-throughput payments systems.",
            classification=QuestionClassification.ANSWERABLE_FROM_EVIDENCE,
            confidence=0.95,
            provenance=[],
            rationale="Verified from candidate Java payments work history.",
        )
    ]
    mock_pkg.user_inputs_required = []
    mock_prep.get_application_package.return_value = mock_pkg

    dash_svc = DashboardService(db=session, prep_service=mock_prep)
    detail = dash_svc.get_application_detail("app-mc-java-001")

    # Invariants:
    assert detail.company == "Mastercard"
    assert detail.role == "Software Engineer"
    assert detail.source == "USER_SUBMITTED_URL"
    assert detail.selected_strategy == "BACKEND_JAVA"
    assert detail.match_score == 88.5
    assert len(detail.prepared_answers) == 1
    assert detail.prepared_answers[0].question_text == "How many years of Java experience do you have?"
    assert detail.cover_letter_subject == "Application for Software Engineer - Mastercard"
    assert "Mastercard Team" in (detail.cover_letter_text or "")
    assert detail.is_external_unverified is False


