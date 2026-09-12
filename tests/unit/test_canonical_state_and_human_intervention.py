"""
Unit and regression tests for Canonical Application State, Human Intervention Architecture (Option B),
Dashboard Consistency, Safe Retry Flow, and Blocker Handling.
"""
import pytest
import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

from job_copilot.models.application import Application, ApplicationStatus
from job_copilot.models.job import Job
from job_copilot.models.browser_task import BrowserTaskModel, BrowserTaskStatus
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.services.dashboard_service import DashboardService, resolve_canonical_application_state, normalize_company_display
from job_copilot.schemas.dashboard import RetrySubmissionPayload
from job_copilot.tracking.models import ApplicationLifecycleStatus, FunnelMetrics
from job_copilot.tracking.lifecycle import STAGE_ORDER


def test_normalize_company_display():
    """Verify company display name normalizes scraped quirks like 'Mastercard We' -> 'Mastercard'."""
    assert normalize_company_display("Mastercard We") == "Mastercard"
    assert normalize_company_display("Mastercard We (Acquired)") == "Mastercard"
    assert normalize_company_display("Google LLC") == "Google LLC"
    assert normalize_company_display("Stripe") == "Stripe"
    assert normalize_company_display("") == "Company unavailable"
    assert normalize_company_display(None) == "Company unavailable"


def test_canonical_state_resolver_for_mastercard_historical_and_unverified(db_session):
    """
    CRITICAL BLOCKER #2:
    Verify resolve_canonical_application_state returns SUBMISSION_UNVERIFIED for app-usr-2a43a63d
    regardless of whether DB has APPLIED, and regardless of task status.
    """
    session = db_session
    job = Job(job_id="job-mc-001", title="Software Engineer", company="Mastercard We", description="Payment systems", source="USER_SUBMITTED_URL", url="https://mastercard.jobs/1")
    session.add(job)
    session.flush()

    # Mastercard historical record with legacy APPLIED status
    mc_app = Application(
        application_id="app-usr-2a43a63d",
        job_id_str="job-mc-001",
        job_id=job.id,
        company="Mastercard We",
        role="Software Engineer",
        status=ApplicationStatus.APPLIED,
    )
    session.add(mc_app)
    session.commit()

    canonical_state = resolve_canonical_application_state(mc_app, None)
    assert canonical_state == ApplicationLifecycleStatus.SUBMISSION_UNVERIFIED


def test_overview_and_tracking_canonical_consistency(db_session):
    """
    CRITICAL BLOCKER #3 & BUG #11:
    Overview metrics and Tracking view must NOT classify Mastercard historical or unverified record
    as a confirmed/submitted application.
    Submitted count = 0, Unverified count = 1.
    """
    from job_copilot.models.application import ApplicationEventModel

    session = db_session
    job = Job(job_id="job-mc-001", title="Software Engineer", company="Mastercard We", description="Payment systems", source="USER_SUBMITTED_URL", url="https://mastercard.jobs/1")
    session.add(job)
    session.flush()

    mc_app = Application(
        application_id="app-usr-2a43a63d",
        job_id_str="job-mc-001",
        job_id=job.id,
        company="Mastercard We",
        role="Software Engineer",
        status=ApplicationStatus.APPLIED,
    )
    session.add(mc_app)
    session.flush()

    # Legacy submitted event
    event = ApplicationEventModel(
        event_id="evt-mc-legacy-01",
        application_id_ref=mc_app.id,
        application_id="app-usr-2a43a63d",
        job_id="job-mc-001",
        event_type="SUBMITTED",
        source="USER",
        notes="Historical internal record",
    )
    session.add(event)
    session.commit()

    dash_svc = DashboardService(db=session)
    overview = dash_svc.get_overview()

    # Overview invariants:
    assert overview.pipeline_counts.submitted == 0
    assert overview.pipeline_counts.submission_unverified == 1

    # Recent activity must clearly mark historical unverified record
    assert len(overview.recent_activity) >= 1
    recent = overview.recent_activity[0]
    assert recent["event_type"] == "SUBMISSION_UNVERIFIED"
    assert "Historical" in (recent["notes"] or "")

    # Tracking / list_applications invariants:
    apps_list = dash_svc.list_applications()
    mc_matches = [
        a for a in apps_list 
        if getattr(a, "application_id", "") == "app-usr-2a43a63d" or (isinstance(a, dict) and a.get("application_id") == "app-usr-2a43a63d")
    ]
    assert len(mc_matches) == 1
    mc_rec = mc_matches[0]
    mc_company = mc_rec["company"] if isinstance(mc_rec, dict) else mc_rec.company
    mc_status = mc_rec["current_status"] if isinstance(mc_rec, dict) else getattr(mc_rec.current_status, "value", str(mc_rec.current_status))
    mc_submitted_at = mc_rec["submitted_at"] if isinstance(mc_rec, dict) else mc_rec.submitted_at

    assert mc_company == "Mastercard"
    assert mc_status == ApplicationLifecycleStatus.SUBMISSION_UNVERIFIED.value
    assert mc_submitted_at is None


from job_copilot.tracking.analytics import AnalyticsEngine
from job_copilot.tracking.models import ApplicationRecord, ApplicationLifecycleStatus, FunnelMetrics


def test_analytics_excludes_unverified_from_successful_submissions():
    """
    BUG #12:
    Analytics funnel must count unverified records separately and NOT inflate successful submissions.
    """
    records = [
        ApplicationRecord(
            application_id="app-usr-2a43a63d",
            job_id="job-mc-001",
            company="Mastercard",
            role="Software Engineer",
            current_status=ApplicationLifecycleStatus.SUBMISSION_UNVERIFIED,
        ),
        ApplicationRecord(
            application_id="app-verified-01",
            job_id="job-stripe-001",
            company="Stripe",
            role="Backend Engineer",
            current_status=ApplicationLifecycleStatus.SUBMITTED,
        ),
    ]
    funnel = AnalyticsEngine.compute_funnel(records, events=[])
    assert funnel.submission_unverified == 1
    assert funnel.submitted == 1
    # If only 1 verified submission exists, submitted count is exactly 1 (not 2)


def test_option_b_safe_manual_takeover_for_captcha_login_mfa(db_session):
    """
    CRITICAL BLOCKER #1:
    Option B (Safe Manual Takeover) must be strictly enforced.
    When CAPTCHA, LOGIN, MFA, or HUMAN_ACTION_REQUIRED occurs in containerized headless Playwright:
    - can_resume is False
    - blocker_instruction clearly directs user to complete application manually in employer portal
    - No misleading resume automation claim is made.
    """
    session = db_session
    task_repo = BrowserTaskRepository(session)

    job = Job(job_id="job-blocker-01", title="Backend Engineer", company="Secure Corp", description="Backend systems", source="lever", url="https://jobs.lever.co/secure/1")
    session.add(job)
    session.flush()

    app = Application(
        application_id="app-blocker-01",
        job_id_str="job-blocker-01",
        job_id=job.id,
        company="Secure Corp",
        role="Backend Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app)
    session.commit()

    for blocker_status, expected_type in [
        (BrowserTaskStatus.CAPTCHA_REQUIRED, "CAPTCHA"),
        (BrowserTaskStatus.LOGIN_REQUIRED, "LOGIN"),
        (BrowserTaskStatus.MFA_REQUIRED, "MFA"),
        (BrowserTaskStatus.HUMAN_ACTION_REQUIRED, "HUMAN_ACTION"),
    ]:
        task = BrowserTaskModel(
            task_id=f"task-{blocker_status.value}",
            application_id="app-blocker-01",
            job_id="job-blocker-01",
            source="lever",
            target_url="https://jobs.lever.co/secure/1",
            status=blocker_status,
        )
        task_repo.create(task)

        dash_svc = DashboardService(db=session)
        detail = dash_svc.get_application_detail("app-blocker-01")

        assert detail.blocker_type == expected_type
        assert detail.can_resume is False
        assert "manually" in detail.blocker_instruction.lower()


def test_user_input_required_allows_resume(db_session):
    """
    If the blocker is purely USER_INPUT_REQUIRED (form field clarification),
    can_resume is True because the user answers directly in the dashboard UI.
    """
    session = db_session
    task_repo = BrowserTaskRepository(session)

    job = Job(job_id="job-input-01", title="Frontend Engineer", company="UI Corp", description="UI role", source="greenhouse", url="https://boards.greenhouse.io/ui/1")
    session.add(job)
    session.flush()

    app = Application(
        application_id="app-input-01",
        job_id_str="job-input-01",
        job_id=job.id,
        company="UI Corp",
        role="Frontend Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app)
    session.commit()

    task = BrowserTaskModel(
        task_id="task-input-01",
        application_id="app-input-01",
        job_id="job-input-01",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/ui/1",
        status=BrowserTaskStatus.USER_INPUT_REQUIRED,
    )
    task_repo.create(task)

    dash_svc = DashboardService(db=session)
    detail = dash_svc.get_application_detail("app-input-01")

    assert detail.blocker_type == "USER_INPUT"
    assert detail.can_resume is True


def test_retry_submission_safety_and_historical_mastercard_protection(db_session):
    """
    BUG #8:
    1. Historical Mastercard record MUST NOT be retryable via automated retry.
    2. General unverified submissions require explicit duplicate risk acknowledgement.
    3. Retry resets tokens and transitions to READY_FOR_REVIEW for fresh human confirmation.
    """
    session = db_session
    task_repo = BrowserTaskRepository(session)

    # 1. Historical Mastercard protection
    job_mc = Job(job_id="job-mc-hist", title="Software Engineer", company="Mastercard", description="Payments", source="USER_SUBMITTED_URL", url="https://mastercard.jobs/1")
    session.add(job_mc)
    session.flush()

    app_mc = Application(
        application_id="app-usr-2a43a63d",
        job_id_str="job-mc-hist",
        job_id=job_mc.id,
        company="Mastercard",
        role="Software Engineer",
        status=ApplicationStatus.APPLIED,
    )
    session.add(app_mc)
    session.commit()

    dash_svc = DashboardService(db=session)

    # Attempting to retry historical Mastercard must fail
    with pytest.raises(ValueError, match="Historical unverified Mastercard record"):
        dash_svc.retry_submission("app-usr-2a43a63d", RetrySubmissionPayload(acknowledge_duplicate_risk=True))

    # 2. General unverified application retry flow
    job_gen = Job(job_id="job-gen-01", title="Backend Engineer", company="Acme Corp", description="Backend", source="greenhouse", url="https://boards.greenhouse.io/acme/1")
    session.add(job_gen)
    session.flush()

    app_gen = Application(
        application_id="app-gen-01",
        job_id_str="job-gen-01",
        job_id=job_gen.id,
        company="Acme Corp",
        role="Backend Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_gen)
    session.commit()

    task_gen = BrowserTaskModel(
        task_id="task-gen-01",
        application_id="app-gen-01",
        job_id="job-gen-01",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/acme/1",
        status=BrowserTaskStatus.SUBMISSION_UNVERIFIED,
        confirmation_token="OLD_EXPIRED_TOKEN_123",
        confirmation_expires_at=datetime.now(timezone.utc),
    )
    task_repo.create(task_gen)

    # Failing to acknowledge duplicate risk must be rejected
    with pytest.raises(ValueError, match="Explicit acknowledgement of duplicate application risk is required"):
        dash_svc.retry_submission("app-gen-01", RetrySubmissionPayload(acknowledge_duplicate_risk=False))

    # Valid retry request with duplicate risk acknowledged
    updated_detail = dash_svc.retry_submission("app-gen-01", RetrySubmissionPayload(acknowledge_duplicate_risk=True, user_notes="Manual verification complete"))

    # Invariants:
    assert updated_detail.status == "READY_FOR_REVIEW"
    # Stale token cleared and fresh confirmation token generated
    task_reloaded = task_repo.get_by_task_id("task-gen-01")
    assert task_reloaded.status == BrowserTaskStatus.READY_FOR_REVIEW
    assert task_reloaded.confirmation_token != "OLD_EXPIRED_TOKEN_123"
    assert task_reloaded.confirmation_token is not None


def test_candidate_truth_files_remain_unchanged():
    """Verify that candidate truth YAML files have not been modified or mutated."""
    expected_hashes = {
        "evidence.yaml": "c0d249794a2976972693f6b2d06e74db130e7c5d5c61202658cce7ebf2756303",
        "master_profile.yaml": "b77c799a8494ead7e3b7b8ee6b5fcbb125f7f512313c8dad745b1127800af433",
        "preferences.yaml": "66b5ff3f6fa8117de378bc7cadd026e9d2230dcbd40e6f0b6587c2edc281380a",
        "review_required.yaml": "422625a4b4cbfb549058de9db4d56c2e4e6de4443d4e53fad4b66e80eb0304b1",
    }
    for filename, expected_hash in expected_hashes.items():
        filepath = f"data/candidate/{filename}"
        with open(filepath, "rb") as f:
            computed_hash = hashlib.sha256(f.read()).hexdigest()
        assert computed_hash == expected_hash, f"Candidate truth file {filename} was unexpectedly modified!"
