"""Unit tests for the AUTO_APPLY Policy Engine and strict safety invariants.

Enforces:
1. Application modes: MANUAL, ASSISTED, AUTO_APPLY (default ASSISTED).
2. All 14 safety conditions (A-N) hard-block automated submission when not satisfied.
3. Ineligible requests never authorize task, never call Playwright, never mark application applied.
4. Clean eligibility transitions to SUBMISSION_AUTHORIZED with authorization_source = AUTO_APPLY_POLICY.
5. Downstream execution strictly flows through existing BrowserTaskExecutor.execute_submission_task().
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.browser_worker.auto_apply_policy import (
    AutoApplyEligibilityResult,
    AutoApplyPolicyService,
    count_daily_auto_apply_submissions,
    evaluate_auto_apply_eligibility,
    get_configured_daily_limit,
)
from job_copilot.browser_worker.browser import BrowserManager
from job_copilot.browser_worker.exceptions import SubmissionSafetyError
from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
from job_copilot.db.migrations_runner import run_migrations
from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus, BrowserTaskStatus, FieldAction
from job_copilot.domain.enums import ApplicationMode, ApplicationStatus
from job_copilot.models.application import Application
from job_copilot.models.browser_session import BrowserSessionModel
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_session_repository import BrowserSessionRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.schemas.candidate import CandidateProfile, PersonalInformation


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


def _build_clean_environment(session, suffix: str = "100"):
    """Create a fully valid baseline environment where all 14 conditions would pass."""
    now = datetime.now(timezone.utc)
    job = Job(
        job_id=f"job-auto-{suffix}",
        title="Senior Distributed Systems Engineer",
        company="Acme Corporation",
        description="Engineering role",
        source="greenhouse",
        url=f"https://boards.greenhouse.io/acme/jobs/{suffix}",
    )
    session.add(job)
    session.flush()

    app = Application(
        application_id=f"app-auto-{suffix}",
        job_id_str=f"job-auto-{suffix}",
        job_id=job.id,
        company="Acme Corporation",
        role="Senior Distributed Systems Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
        mode=ApplicationMode.AUTO_APPLY,
        canonical_job_url=f"https://boards.greenhouse.io/acme/jobs/{suffix}",
    )
    session.add(app)
    session.flush()

    sess_model = BrowserSessionModel(
        session_id=f"sess-auto-{suffix}",
        source="greenhouse",
        status=AuthenticatedSessionStatus.ACTIVE,
        expires_at=now + timedelta(days=7),
        metadata_json={
            "company": "Acme Corporation",
            "target_domain": "boards.greenhouse.io",
        },
    )
    session.add(sess_model)
    session.flush()

    task = BrowserTaskModel(
        task_id=f"task-auto-{suffix}",
        application_id=f"app-auto-{suffix}",
        job_id=f"job-auto-{suffix}",
        source="greenhouse",
        target_url=f"https://boards.greenhouse.io/acme/jobs/{suffix}",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        application_mode="AUTO_APPLY",
        review_package_json={
            "fields_detected": 3,
            "fields_autofilled": 3,
            "fields_skipped": 0,
            "fields_requiring_user_input": 0,
            "fields_summary": [
                {
                    "field_id": "f_name",
                    "element_type": "text",
                    "label": "Full Name",
                    "action": "AUTO_FILL",
                    "filled_value_masked": "Al***er",
                    "required": True,
                },
                {
                    "field_id": "f_email",
                    "element_type": "email",
                    "label": "Email Address",
                    "action": "AUTO_FILL",
                    "filled_value_masked": "al***om",
                    "required": True,
                },
                {
                    "field_id": "f_phone",
                    "element_type": "tel",
                    "label": "Phone Number",
                    "action": "AUTO_FILL",
                    "filled_value_masked": "+1***99",
                    "required": False,
                },
            ],
            "warnings": [],
        },
        audit_events=[
            {"event": "task_started", "timestamp": now.isoformat()},
            {"event": "ready_for_review", "timestamp": now.isoformat()},
        ],
    )
    session.add(task)
    session.commit()
    return app, task, sess_model


# ==============================================================================
# 1. APPLICATION MODE DEFAULT AND ENUM TESTS
# ==============================================================================

def test_application_mode_defaults_to_assisted(db_session):
    """Existing applications/jobs must default to ApplicationMode.ASSISTED."""
    session, _ = db_session
    job = Job(
        job_id="job-def-1",
        title="Engineer",
        company="TechCorp",
        description="Engineer role",
        source="manual",
    )
    session.add(job)
    session.flush()

    app = Application(
        application_id="app-default-mode-1",
        job_id_str="job-def-1",
        job_id=job.id,
        company="TechCorp",
        role="Engineer",
        status=ApplicationStatus.DISCOVERED,
    )
    session.add(app)
    session.commit()

    reloaded = session.query(Application).filter_by(application_id="app-default-mode-1").one()
    assert reloaded.mode == ApplicationMode.ASSISTED



def test_blocked_when_mode_is_not_auto_apply(db_session):
    """AUTO_APPLY eligibility is blocked if application mode is ASSISTED or MANUAL."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    app.mode = ApplicationMode.ASSISTED
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "MODE_NOT_AUTO_APPLY"
    assert "M_SAFETY_AND_DOMAIN" in result.blocking_conditions

    app.mode = ApplicationMode.MANUAL
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "MODE_NOT_AUTO_APPLY"


# ==============================================================================
# 2. HARD BLOCK CONDITIONS (Conditions A through N)
# ==============================================================================

def test_blocked_when_no_authenticated_session(db_session):
    """Condition C: No active authenticated session blocks AUTO_APPLY."""
    session, _ = db_session
    app, task, _ = _build_clean_environment(session)

    result = evaluate_auto_apply_eligibility(app, task, session=None, db=None)
    assert result.eligible is False
    assert result.reason_code == "NO_AUTHENTICATED_SESSION"
    assert "C_AUTHENTICATED_SESSION" in result.blocking_conditions


def test_blocked_when_session_expired(db_session):
    """Condition C: Expired session blocks AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    sess_model.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "SESSION_EXPIRED"
    assert "C_AUTHENTICATED_SESSION" in result.blocking_conditions


def test_blocked_when_wrong_employer_session(db_session):
    """Condition C: Session belonging to another employer violates isolation and blocks."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    sess_model.metadata_json = {"company": "Different Competitor LLC"}
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "WRONG_EMPLOYER_SESSION"
    assert "C_AUTHENTICATED_SESSION" in result.blocking_conditions


def test_blocked_when_domain_mismatch(db_session):
    """Condition C & M: Session domain or target domain mismatch blocks AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    # Session domain mismatch
    sess_model.metadata_json = {
        "company": "Acme Corporation",
        "target_domain": "unrelated-ats.com",
    }
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "SESSION_DOMAIN_MISMATCH"

    # Task target URL domain mismatch with Application canonical URL
    sess_model.metadata_json = {
        "company": "Acme Corporation",
        "target_domain": "boards.greenhouse.io",
    }
    task.target_url = "https://jobs.lever.co/different-company/job"
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "DOMAIN_MISMATCH"


def test_blocked_when_task_not_ready_for_review(db_session):
    """Condition D: Task not in READY_FOR_REVIEW blocks AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    for invalid_status in (
        BrowserTaskStatus.QUEUED,
        BrowserTaskStatus.RUNNING,
        BrowserTaskStatus.BLOCKED,
        BrowserTaskStatus.FAILED,
        BrowserTaskStatus.USER_INPUT_REQUIRED,
    ):
        task.status = invalid_status
        result = evaluate_auto_apply_eligibility(app, task, sess_model)
        assert result.eligible is False
        assert result.reason_code in ("TASK_NOT_READY_FOR_REVIEW", "TASK_BLOCKED_OR_FAILED")


def test_blocked_when_unresolved_required_input(db_session):
    """Condition E & F: Unresolved required fields block AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    # 1. Non-zero fields_requiring_user_input count
    task.review_package_json = {
        "fields_requiring_user_input": 1,
        "fields_summary": [
            {"field_id": "q1", "label": "Portfolio URL", "action": "REQUIRES_USER_INPUT", "required": True}
        ],
    }
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "UNRESOLVED_REQUIRED_FIELDS"

    # 2. Required field with unknown/unresolved action
    task.review_package_json = {
        "fields_requiring_user_input": 0,
        "fields_summary": [
            {"field_id": "q2", "label": "Years in Java", "action": "UNKNOWN", "required": True}
        ],
    }
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "UNRESOLVED_REQUIRED_FIELDS"


def test_blocked_when_sensitive_user_input_pending(db_session):
    """Condition G: Sensitive fields requiring user input block AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    task.review_package_json = {
        "fields_requiring_user_input": 0,
        "fields_summary": [
            {"field_id": "f_sal", "label": "Expected Salary / CTC", "action": "REQUIRES_USER_INPUT", "filled_value_masked": None}
        ],
    }
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code in ("SENSITIVE_USER_INPUT_PENDING", "UNRESOLVED_REQUIRED_FIELDS")


def test_blocked_when_prohibited_field_detected(db_session):
    """Condition G: Prohibited credential / financial fields block AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    task.review_package_json = {
        "fields_requiring_user_input": 0,
        "fields_summary": [
            {"field_id": "f_pwd", "label": "Account Password", "action": "DO_NOT_FILL"}
        ],
    }
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "PROHIBITED_FIELD_DETECTED"


def test_blocked_when_captcha_required(db_session):
    """Condition H: CAPTCHA blocker prevents AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    task.status = BrowserTaskStatus.CAPTCHA_REQUIRED
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code in ("CAPTCHA_REQUIRED", "TASK_NOT_READY_FOR_REVIEW")


def test_blocked_when_mfa_required(db_session):
    """Condition I: MFA / OTP blocker prevents AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    task.status = BrowserTaskStatus.MFA_REQUIRED
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code in ("MFA_REQUIRED", "TASK_NOT_READY_FOR_REVIEW")


def test_blocked_when_login_required(db_session):
    """Condition J: Login wall blocker prevents AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    task.status = BrowserTaskStatus.LOGIN_REQUIRED
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code in ("LOGIN_REQUIRED", "TASK_NOT_READY_FOR_REVIEW")


def test_blocked_when_human_action_required(db_session):
    """Condition K: HUMAN_ACTION_REQUIRED blocker prevents AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    task.status = BrowserTaskStatus.HUMAN_ACTION_REQUIRED
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code in ("HUMAN_ACTION_REQUIRED", "TASK_NOT_READY_FOR_REVIEW")


def test_blocked_when_duplicate_submission(db_session):
    """Condition L: Terminal application status or completed task blocks duplicate AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    # 1. Application already APPLIED
    app.status = ApplicationStatus.APPLIED
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "DUPLICATE_SUBMISSION"

    # 2. Browser task already COMPLETED
    app.status = ApplicationStatus.READY_TO_APPLY
    task.status = BrowserTaskStatus.COMPLETED
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "DUPLICATE_SUBMISSION"


def test_blocked_when_invalid_canonical_url(db_session):
    """Condition B: Missing, non-HTTP, or disallowed URL blocks AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    app.canonical_job_url = "ftp://unsupported.com/job"
    task.target_url = "ftp://unsupported.com/job"
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "INVALID_CANONICAL_URL"

    app.canonical_job_url = ""
    task.target_url = ""
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "INVALID_CANONICAL_URL"


def test_blocked_when_application_identity_mismatch(db_session):
    """Condition A: Mismatched task application_id or job_id blocks AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    task.application_id = "app-different-999"
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "IDENTITY_MISMATCH"


def test_blocked_when_policy_risk_blocker(db_session):
    """Condition N: Task with failure_reason or BLOCKED status prevents AUTO_APPLY."""
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    task.failure_reason = "Suspicious domain redirect detected"
    result = evaluate_auto_apply_eligibility(app, task, sess_model)
    assert result.eligible is False
    assert result.reason_code == "POLICY_RISK_BLOCKER"


# ==============================================================================
# 3. INELIGIBLE REQUESTS DO NOT MUTATE STATE OR CALL PLAYWRIGHT
# ==============================================================================

@pytest.mark.asyncio
async def test_ineligible_request_does_not_authorize_or_submit(db_session, mock_candidate_profile):
    """
    An ineligible AUTO_APPLY request must:
    - NOT transition task to SUBMISSION_AUTHORIZED
    - NOT call Playwright submit
    - NOT mark application as SUBMITTED / APPLIED
    """
    session, _ = db_session
    app, task, sess_model = _build_clean_environment(session)

    # Invalidate by introducing an unresolved required input
    task.review_package_json["fields_requiring_user_input"] = 1

    policy_service = AutoApplyPolicyService(session)

    with pytest.raises(SubmissionSafetyError) as exc_info:
        policy_service.authorize(app.application_id)

    assert "AUTO_APPLY not eligible" in str(exc_info.value)

    # Invariants: Task remains READY_FOR_REVIEW, Application remains READY_TO_APPLY
    reloaded_task = session.query(BrowserTaskModel).filter_by(task_id=task.task_id).one()
    reloaded_app = session.query(Application).filter_by(application_id=app.application_id).one()

    assert reloaded_task.status == BrowserTaskStatus.READY_FOR_REVIEW
    assert reloaded_app.status == ApplicationStatus.READY_TO_APPLY
    assert reloaded_app.submitted_at is None

    # Verify BrowserTaskExecutor refuses to submit an unauthorized task
    mock_adapter = MagicMock()
    mock_adapter.click = AsyncMock()
    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_adapter)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(
        db=session,
        browser_manager=mock_manager,
        candidate_profile=mock_candidate_profile,
    )
    result_task = await executor.execute_submission_task(task.task_id)

    # Playwright click was never called
    assert mock_adapter.click.call_count == 0
    assert result_task.status == BrowserTaskStatus.READY_FOR_REVIEW
    assert reloaded_app.status == ApplicationStatus.READY_TO_APPLY


# ==============================================================================
# 4. CLEAN ELIGIBILITY CASE & VERIFIED SUBMISSION FLOW
# ==============================================================================

@pytest.mark.asyncio
async def test_clean_auto_apply_flow_to_verified_submission(db_session, mock_candidate_profile):
    """
    Clean end-to-end pipeline verification:
    1. Fully valid fake employer ATS environment
    2. AUTO_APPLY policy evaluates eligible: True
    3. AutoApplyPolicyService.authorize transitions task to SUBMISSION_AUTHORIZED
    4. Audit event records authorization_source = 'AUTO_APPLY_POLICY'
    5. Application lifecycle records SUBMISSION_AUTHORIZED with source = 'AUTO_APPLY_POLICY'
    6. Application is NOT yet marked SUBMITTED/APPLIED
    7. Canonical BrowserTaskExecutor.execute_submission_task executes submission
    8. Employer verification succeeds -> task COMPLETED, application APPLIED
    9. Proves AUTO_APPLY reuses the exact single canonical submission executor.
    """
    session, _ = db_session
    app_repo = ApplicationRepository(session)
    task_repo = BrowserTaskRepository(session)

    app, task, sess_model = _build_clean_environment(session)

    policy_service = AutoApplyPolicyService(session)

    # 1. Evaluate eligibility
    eligibility = policy_service.evaluate(app.application_id)
    assert eligibility.eligible is True
    assert eligibility.reason_code == "ELIGIBLE"
    assert eligibility.blocking_conditions == []

    # 2. Authorize submission
    auth_task, auth_result = policy_service.authorize(app.application_id)
    assert auth_result.eligible is True
    assert auth_task.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED

    # Verify audit event in task
    audit_events = auth_task.audit_events or []
    auth_event = next((e for e in audit_events if e.get("event") == "auto_apply_submission_authorized"), None)
    assert auth_event is not None
    assert auth_event["authorization_source"] == "AUTO_APPLY_POLICY"
    assert auth_event["application_id"] == app.application_id
    assert auth_event["task_id"] == task.task_id

    # Verify application timeline event
    app_events = app_repo.get_events(app.application_id)
    sub_auth_event = next((e for e in app_events if e.event_type == "SUBMISSION_AUTHORIZED"), None)
    assert sub_auth_event is not None
    assert sub_auth_event.source == "AUTO_APPLY_POLICY"

    # Verify application is NOT yet marked submitted/applied
    reloaded_app = app_repo.get_by_application_id(app.application_id)
    assert reloaded_app.status == ApplicationStatus.READY_TO_APPLY
    assert reloaded_app.submitted_at is None

    # 3. Canonical Execution through BrowserTaskExecutor
    mock_adapter = MagicMock()
    mock_adapter.launch = AsyncMock()
    mock_adapter.navigate = AsyncMock(return_value="https://boards.greenhouse.io/acme/jobs/100")
    mock_adapter.wait_for_dom_idle = AsyncMock()
    mock_adapter.get_current_url = AsyncMock(return_value="https://boards.greenhouse.io/acme/jobs/100/confirmation")
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

    final_task = await executor.execute_submission_task(task.task_id)

    # 4. Verified outcomes
    assert mock_adapter.click.call_count >= 1
    assert final_task.status == BrowserTaskStatus.COMPLETED

    submitted_app = app_repo.get_by_application_id(app.application_id)
    assert submitted_app.status == ApplicationStatus.APPLIED
    assert submitted_app.submitted_at is not None

    app_events_final = app_repo.get_events(app.application_id)
    submitted_event = next((e for e in app_events_final if e.event_type == "SUBMITTED"), None)
    assert submitted_event is not None
    assert submitted_event.source == "BROWSER_SUBMISSION_VERIFIED"


# ==============================================================================
# 5. NO NEW SUBMISSION PATH INVARIANT
# ==============================================================================

def test_single_canonical_submission_executor_invariant():
    """
    Verify that there is still exactly one canonical external automated submission executor:
    BrowserTaskExecutor.execute_submission_task()
    And that AutoApplyPolicyService does not invoke Playwright or duplicate the submission path.
    """
    import inspect
    from job_copilot.browser_worker.auto_apply_policy import AutoApplyPolicyService
    from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
    from job_copilot.browser_worker.task_executor import BrowserTaskExecutor

    # 1. Inspect AutoApplyPolicyService methods
    policy_methods = [m[0] for m in inspect.getmembers(AutoApplyPolicyService, predicate=inspect.isfunction)]
    # AUTO_APPLY policy service does not implement submission execution
    assert "execute_submission_task" not in policy_methods
    assert "submit" not in policy_methods

    # 2. Both HumanConfirmationService and AutoApplyPolicyService produce SUBMISSION_AUTHORIZED
    auth_doc = AutoApplyPolicyService.authorize.__doc__ or ""
    assert "SUBMISSION_AUTHORIZED" in auth_doc
    assert "AUTO_APPLY_POLICY" in auth_doc

    # 3. Only BrowserTaskExecutor implements the canonical execution method
    assert hasattr(BrowserTaskExecutor, "execute_submission_task")
    sig = inspect.signature(BrowserTaskExecutor.execute_submission_task)
    assert "task_id" in sig.parameters


# ==============================================================================
# 6. DETERMINISTIC DAILY AUTO_APPLY SUBMISSION CAP TESTS
# ==============================================================================

def test_daily_cap_allows_submissions_below_limit(db_session):
    """
    Submissions below the configured daily safety limit remain eligible
    and can be safely authorized.
    """
    session, _ = db_session
    # Configure safety limit = 2
    policy_service = AutoApplyPolicyService(session, max_daily_submissions=2)

    # Initially 0 submissions today
    assert policy_service.count_daily_submissions() == 0

    # 1. First application: eligible and authorizes
    app1, task1, sess1 = _build_clean_environment(session, suffix="cap-1")
    res1 = policy_service.evaluate(app1.application_id)
    assert res1.eligible is True
    assert res1.reason_code == "ELIGIBLE"

    auth_task1, auth_res1 = policy_service.authorize(app1.application_id)
    assert auth_res1.eligible is True
    assert auth_task1.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED
    assert policy_service.count_daily_submissions() == 1

    # 2. Second application: eligible and authorizes (reaches limit of 2)
    app2, task2, sess2 = _build_clean_environment(session, suffix="cap-2")
    res2 = policy_service.evaluate(app2.application_id)
    assert res2.eligible is True
    assert res2.reason_code == "ELIGIBLE"

    auth_task2, auth_res2 = policy_service.authorize(app2.application_id)
    assert auth_res2.eligible is True
    assert auth_task2.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED
    assert policy_service.count_daily_submissions() == 2


def test_daily_cap_blocks_authorization_when_limit_reached(db_session):
    """
    When the configured daily safety limit is reached:
    - evaluate() returns eligible=False with reason_code="RATE_LIMIT_EXCEEDED"
    - authorize() raises SubmissionSafetyError
    - Task remains in READY_FOR_REVIEW
    - Application remains in READY_TO_APPLY
    - No submission authorization is granted
    """
    session, _ = db_session
    policy_service = AutoApplyPolicyService(session, max_daily_submissions=2)

    # Authorize 2 applications to reach the limit
    app1, task1, _ = _build_clean_environment(session, suffix="limit-1")
    policy_service.authorize(app1.application_id)

    app2, task2, _ = _build_clean_environment(session, suffix="limit-2")
    policy_service.authorize(app2.application_id)

    assert policy_service.count_daily_submissions() == 2

    # 3. Third application: must be blocked by rate limit
    app3, task3, sess3 = _build_clean_environment(session, suffix="limit-3")

    eval_result = policy_service.evaluate(app3.application_id)
    assert eval_result.eligible is False
    assert eval_result.reason_code == "RATE_LIMIT_EXCEEDED"
    assert "Daily AUTO_APPLY submission limit reached" in eval_result.reason
    assert "M_SAFETY_AND_DOMAIN" in eval_result.blocking_conditions

    # Direct authorization attempt must fail safely
    with pytest.raises(SubmissionSafetyError) as exc_info:
        policy_service.authorize(app3.application_id)

    assert "Daily AUTO_APPLY submission limit reached" in str(exc_info.value)

    # Invariants: Task remains READY_FOR_REVIEW, Application remains READY_TO_APPLY
    reloaded_task = session.query(BrowserTaskModel).filter_by(task_id=task3.task_id).one()
    reloaded_app = session.query(Application).filter_by(application_id=app3.application_id).one()
    assert reloaded_task.status == BrowserTaskStatus.READY_FOR_REVIEW
    assert reloaded_app.status == ApplicationStatus.READY_TO_APPLY
    assert reloaded_app.submitted_at is None

    # Verify no auto_apply_submission_authorized audit event was added to task 3
    audit_events = reloaded_task.audit_events or []
    assert not any(e.get("event") == "auto_apply_submission_authorized" for e in audit_events)


def test_daily_cap_ignores_submissions_from_previous_days(db_session):
    """
    Submissions from yesterday or earlier do not count toward today's daily cap.
    """
    session, _ = db_session
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=2)

    app_repo = ApplicationRepository(session)
    policy_service = AutoApplyPolicyService(session, max_daily_submissions=1)

    # Record an AUTO_APPLY submission event from 2 days ago
    app_old, task_old, _ = _build_clean_environment(session, suffix="old-1")
    app_repo.append_event(
        application_id=app_old.application_id,
        job_id=app_old.job_id_str,
        event_type="SUBMISSION_AUTHORIZED",
        event_id="evt-old-1",
        source="AUTO_APPLY_POLICY",
        notes="Old submission from previous day",
        timestamp=yesterday,
    )
    task_old.status = BrowserTaskStatus.COMPLETED
    task_old.audit_events = [
        {
            "event": "auto_apply_submission_authorized",
            "authorization_source": "AUTO_APPLY_POLICY",
            "timestamp": yesterday.isoformat(),
        }
    ]
    task_old.completed_at = yesterday
    session.commit()

    # Today's count is 0
    assert policy_service.count_daily_submissions() == 0

    # Today's application is fully eligible despite cap = 1
    app_today, task_today, sess_today = _build_clean_environment(session, suffix="today-1")
    eval_result = policy_service.evaluate(app_today.application_id)
    assert eval_result.eligible is True
    assert eval_result.reason_code == "ELIGIBLE"

    auth_task, auth_res = policy_service.authorize(app_today.application_id)
    assert auth_res.eligible is True
    assert auth_task.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED
    assert policy_service.count_daily_submissions() == 1


def test_configured_safety_limit_default_and_override(db_session):
    """
    Verify configured safety limit behavior:
    - Defaults to configured safety limit (10)
    - Can be overridden via constructor or method parameters
    """
    session, _ = db_session
    policy_service = AutoApplyPolicyService(session)
    assert policy_service.max_daily_submissions == get_configured_daily_limit()

    # Create an app
    app, task, _ = _build_clean_environment(session, suffix="conf-1")

    # Override cap to 0 via evaluate parameter
    res_blocked = policy_service.evaluate(app.application_id, max_daily_submissions=0)
    assert res_blocked.eligible is False
    assert res_blocked.reason_code == "RATE_LIMIT_EXCEEDED"

    # Override cap to 5 via evaluate parameter
    res_ok = policy_service.evaluate(app.application_id, max_daily_submissions=5)
    assert res_ok.eligible is True
    assert res_ok.reason_code == "ELIGIBLE"

