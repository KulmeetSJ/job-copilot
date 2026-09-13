"""Unit tests for Phase 11 DashboardService."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.browser_worker.exceptions import DomainSecurityError
from job_copilot.copilot.models import CopilotJob, PriorityBand, QueueStatus
from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus, BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.base import Base
from job_copilot.models.application import Application, ApplicationEventModel
from job_copilot.models.browser_session import BrowserSessionModel
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.schemas.dashboard import HumanInputSubmitRequest, HumanInputAnswerItem, SubmissionConfirmPayload
from job_copilot.services.dashboard_service import DashboardService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.models import ApplicationLifecycleStatus, ApplicationRecord, EventSource
from job_copilot.tracking.store import TrackingStore


from sqlalchemy.pool import StaticPool


@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_copilot_service():
    service = MagicMock()
    service.get_queue.return_value = [
        CopilotJob(
            job_id="job-stripe-001",
            title="Senior Backend Engineer",
            company="Stripe",
            location="Bengaluru",
            source="manual",
            priority_score=92.0,
            priority_band=PriorityBand.CRITICAL,
            queue_status=QueueStatus.NEW,
            match_score=92.0,
            recommendation_tier="STRONG_APPLY",
        ),
        CopilotJob(
            job_id="job-hsbc-002",
            title="Lead Software Engineer",
            company="HSBC",
            location="Pune",
            source="manual",
            priority_score=85.0,
            priority_band=PriorityBand.HIGH,
            queue_status=QueueStatus.REVIEW,
            match_score=88.0,
            recommendation_tier="STRONG_APPLY",
        ),
    ]
    service.get_sources_health.return_value = []
    service.get_sources.return_value = []
    return service


def test_dashboard_overview_aggregation(in_memory_db, mock_copilot_service):
    """Test dashboard overview metrics calculation."""
    # Seed an application
    job = Job(
        job_id="job-stripe-001",
        title="Senior Backend Engineer",
        company="Stripe",
        description="Java Spring Boot engineer",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-stripe-001",
        job_id=job.id,
        job_id_str="job-stripe-001",
        company="Stripe",
        role="Senior Backend Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    service = DashboardService(db=in_memory_db, copilot_service=mock_copilot_service)
    overview = service.get_overview()

    assert overview.queue_counts.critical == 1
    assert overview.queue_counts.high == 1
    assert overview.queue_counts.total_active == 2
    assert overview.pipeline_counts.ready_for_review >= 1


def test_dashboard_queue_retrieval(in_memory_db, mock_copilot_service):
    """Test priority queue filtering and response mapping."""
    service = DashboardService(db=in_memory_db, copilot_service=mock_copilot_service)
    queue = service.get_queue()

    assert queue.total_count == 2
    assert queue.critical_count == 1
    assert queue.high_count == 1
    assert queue.items[0].company == "Stripe"
    assert queue.items[0].match_score == 92.0


def test_dashboard_job_detail_explanation(in_memory_db, mock_copilot_service):
    """Test job detail match explanation with 7 dimensions and Fact vs Inference."""
    job = Job(
        job_id="job-hsbc-002",
        title="Lead Software Engineer",
        company="HSBC",
        description="Seeking a Senior Java and Spring Boot engineer with GCP experience in Fintech payments.",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    mock_copilot_service.get_job.return_value = CopilotJob(
        job_id="job-hsbc-002",
        title="Lead Software Engineer",
        company="HSBC",
        match_score=88.0,
        priority_score=85.0,
        priority_band=PriorityBand.HIGH,
        recommendation_tier="STRONG_APPLY",
    )

    service = DashboardService(db=in_memory_db, copilot_service=mock_copilot_service)
    detail = service.get_job_detail("job-hsbc-002")

    assert detail.company == "HSBC"
    assert detail.match_score >= 70.0
    assert len(detail.dimension_scores) == 7
    # Verify Fact vs Inference vs Recommendation separation
    assert len(detail.explanation.facts) > 0
    assert len(detail.explanation.recommendations) > 0


def test_dashboard_human_input_submission_safe(in_memory_db):
    """Test submitting human answers stores in application state without mutating candidate files."""
    job = Job(
        job_id="job-test-input-001",
        title="Backend Engineer",
        company="TestCorp",
        description="Software engineer",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-test-input-001",
        job_id=job.id,
        job_id_str="job-test-input-001",
        company="TestCorp",
        role="Backend Engineer",
        status=ApplicationStatus.PREPARING,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    service = DashboardService(db=in_memory_db)
    payload = HumanInputSubmitRequest(
        answers=[
            HumanInputAnswerItem(
                question_id="work_auth",
                question_text="Are you authorized to work in the country?",
                answer_value="Yes, Citizen",
            ),
            HumanInputAnswerItem(
                question_id="notice_period",
                question_text="What is your notice period?",
                answer_value="30 days",
            ),
        ]
    )

    updated = service.submit_user_inputs("app-test-input-001", payload)
    assert updated.application_id == "app-test-input-001"
    assert len(updated.user_notes) > 0
    assert "work_auth='Yes, Citizen'" in updated.user_notes[0]


def test_record_portal_opened_persists_timeline_event_without_submitting(in_memory_db, tmp_path):
    """Test APPLY records PORTAL_OPENED event without auto-submitting or changing applied status."""
    track_store = TrackingStore(tracking_dir=tmp_path / "tracking")
    tracking_service = TrackingService(store=track_store)
    service = DashboardService(db=in_memory_db, tracking_service=tracking_service)

    job = Job(
        job_id="job-stripe-portal-01",
        title="Staff Infrastructure Engineer",
        company="Stripe",
        description="Core infra engineer",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-stripe-portal-01",
        job_id=job.id,
        job_id_str="job-stripe-portal-01",
        company="Stripe",
        role="Staff Infrastructure Engineer",
        canonical_job_url="https://boards.greenhouse.io/stripe/jobs/123",
        source="greenhouse",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    track_rec = ApplicationRecord(
        application_id="app-stripe-portal-01",
        job_id="job-stripe-portal-01",
        company="Stripe",
        role="Staff Infrastructure Engineer",
        current_status=ApplicationLifecycleStatus.PREPARED,
    )
    track_store.save_application(track_rec)

    detail = service.record_portal_opened("app-stripe-portal-01")

    # Status must NOT be APPLIED - never auto-submits
    assert detail.status != "SUBMITTED"
    assert detail.application_id == "app-stripe-portal-01"

    app_db = in_memory_db.query(Application).filter_by(application_id="app-stripe-portal-01").first()
    assert app_db.status == ApplicationStatus.READY_TO_APPLY

    # DB Event check
    events = in_memory_db.query(ApplicationEventModel).filter_by(application_id="app-stripe-portal-01").all()
    portal_events = [e for e in events if e.event_type == "PORTAL_OPENED"]
    assert len(portal_events) == 1
    assert portal_events[0].source == "USER"
    assert "https://boards.greenhouse.io/stripe/jobs/123" in portal_events[0].metadata_json.get("target_url", "")

    # Tracking store check
    saved_rec = track_store.get_application("app-stripe-portal-01")
    assert saved_rec.current_status == ApplicationLifecycleStatus.PREPARED
    tracking_portal_events = [e for e in saved_rec.events if e.metadata and e.metadata.get("stage") == "PORTAL_OPENED"]
    assert len(tracking_portal_events) == 1


def test_record_portal_opened_rejects_missing_url(in_memory_db):
    """Test record_portal_opened raises ValueError if canonical_job_url is missing."""
    service = DashboardService(db=in_memory_db)
    job = Job(job_id="job-no-url", title="Engineer", company="Acme", description="Engineer job description")
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-no-url",
        job_id=job.id,
        job_id_str="job-no-url",
        company="Acme",
        role="Engineer",
        canonical_job_url=None,
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    with pytest.raises(ValueError, match="Original job URL unavailable"):
        service.record_portal_opened("app-no-url")


def test_record_portal_opened_rejects_disallowed_domain(in_memory_db):
    """Test record_portal_opened raises DomainSecurityError for unsafe / SSRF domains."""
    service = DashboardService(db=in_memory_db)
    job = Job(job_id="job-bad-domain", title="Engineer", company="Acme", description="Engineer job description")
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-bad-domain",
        job_id=job.id,
        job_id_str="job-bad-domain",
        company="Acme",
        role="Engineer",
        canonical_job_url="http://169.254.169.254/latest/meta-data",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    with pytest.raises(DomainSecurityError):
        service.record_portal_opened("app-bad-domain")


def test_record_portal_opened_rejects_placeholder_identity(in_memory_db):
    """Test record_portal_opened raises ValueError if application has placeholder identity."""
    service = DashboardService(db=in_memory_db)
    job = Job(job_id="job-placeholder-id", title="Engineer", company="Target Company", description="Placeholder description")
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-placeholder-id",
        job_id=job.id,
        job_id_str="job-placeholder-id",
        company="Target Company",
        role="Role unavailable",
        canonical_job_url="https://boards.greenhouse.io/test/jobs/1",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    with pytest.raises(ValueError, match="Invalid canonical identity"):
        service.record_portal_opened("app-placeholder-id")


def test_continue_application_missing_session_sets_login_required(in_memory_db):
    """Test continue_application sets task to LOGIN_REQUIRED with prompt when no active session."""
    service = DashboardService(db=in_memory_db)

    job = Job(
        job_id="job-login-req-01",
        title="Senior Python Engineer",
        company="Stripe",
        description="Python backend platform engineer",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-login-req-01",
        job_id=job.id,
        job_id_str="job-login-req-01",
        company="Stripe",
        role="Senior Python Engineer",
        canonical_job_url="https://boards.greenhouse.io/stripe/jobs/456",
        source="greenhouse",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    detail = service.continue_application("app-login-req-01")

    assert detail.browser_review is not None
    assert detail.browser_review.status == BrowserTaskStatus.LOGIN_REQUIRED.value
    expected_msg = "Log in to the employer portal first, then connect an authenticated browser session to Job Copilot."
    assert detail.browser_review.pause_reason == expected_msg
    assert detail.blocker_instruction == expected_msg


def test_continue_application_with_active_session_enqueues_task(in_memory_db):
    """Test continue_application enqueues browser task when authenticated session is active."""
    service = DashboardService(db=in_memory_db)

    session = BrowserSessionModel(
        session_id="sess-gh-active-01",
        source="greenhouse",
        status=AuthenticatedSessionStatus.ACTIVE,
    )
    in_memory_db.add(session)

    job = Job(
        job_id="job-continue-queued-01",
        title="Backend Engineer",
        company="Stripe",
        description="Backend platform engineer",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-continue-queued-01",
        job_id=job.id,
        job_id_str="job-continue-queued-01",
        company="Stripe",
        role="Backend Engineer",
        canonical_job_url="https://boards.greenhouse.io/stripe/jobs/789",
        source="greenhouse",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    detail = service.continue_application("app-continue-queued-01")

    assert detail.browser_review is not None
    assert detail.browser_review.status == BrowserTaskStatus.QUEUED.value

    task = in_memory_db.query(BrowserTaskModel).filter_by(application_id="app-continue-queued-01").first()
    assert task is not None
    assert task.status == BrowserTaskStatus.QUEUED


def test_continue_application_rejects_disallowed_domain(in_memory_db):
    """Test continue_application blocks execution on disallowed / SSRF domains."""
    service = DashboardService(db=in_memory_db)
    job = Job(job_id="job-continue-ssrf", title="Engineer", company="Stripe", description="Engineer role")
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-continue-ssrf",
        job_id=job.id,
        job_id_str="job-continue-ssrf",
        company="Stripe",
        role="Engineer",
        canonical_job_url="http://127.0.0.1:8080/exploit",
        source="custom",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    with pytest.raises(DomainSecurityError):
        service.continue_application("app-continue-ssrf")


def test_mark_submitted_manually_records_manual_event_and_status(in_memory_db, tmp_path):
    """Test manual submission records source='MANUAL_CANDIDATE', updates tracking, completes tasks."""
    track_store = TrackingStore(tracking_dir=tmp_path / "tracking")
    tracking_service = TrackingService(store=track_store)
    service = DashboardService(db=in_memory_db, tracking_service=tracking_service)

    job = Job(
        job_id="job-manual-sub-01",
        title="Full Stack Engineer",
        company="Linear",
        description="Full stack product engineer",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-manual-sub-01",
        job_id=job.id,
        job_id_str="job-manual-sub-01",
        company="Linear",
        role="Full Stack Engineer",
        canonical_job_url="https://jobs.lever.co/linear/123",
        source="lever",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)

    task = BrowserTaskModel(
        task_id="task-bw-manual-01",
        application_id="app-manual-sub-01",
        job_id="job-manual-sub-01",
        source="lever",
        target_url="https://jobs.lever.co/linear/123",
        status=BrowserTaskStatus.LOGIN_REQUIRED,
    )
    in_memory_db.add(task)
    in_memory_db.commit()

    track_rec = ApplicationRecord(
        application_id="app-manual-sub-01",
        job_id="job-manual-sub-01",
        company="Linear",
        role="Full Stack Engineer",
        current_status=ApplicationLifecycleStatus.PREPARED,
    )
    track_store.save_application(track_rec)

    notes = "Completed manually in Lever portal, confirmation #LIN-994"
    detail = service.mark_application_submitted_manually("app-manual-sub-01", user_notes=notes)

    # Application status must be SUBMITTED
    assert detail.status == "SUBMITTED"
    assert detail.submitted_at is not None

    # DB Application check
    app_db = in_memory_db.query(Application).filter_by(application_id="app-manual-sub-01").first()
    assert app_db.status == ApplicationStatus.APPLIED
    assert app_db.submitted_at is not None

    # Event check
    events = in_memory_db.query(ApplicationEventModel).filter_by(application_id="app-manual-sub-01").all()
    sub_events = [e for e in events if e.event_type == "SUBMITTED"]
    assert len(sub_events) == 1
    assert sub_events[0].source == "MANUAL_CANDIDATE"
    assert notes in sub_events[0].notes
    assert sub_events[0].metadata_json.get("submission_mode") == "MANUAL"

    # Browser task should be COMPLETED
    in_memory_db.refresh(task)
    assert task.status == BrowserTaskStatus.COMPLETED

    # Tracking store check
    saved_rec = track_store.get_application("app-manual-sub-01")
    assert saved_rec.current_status == ApplicationLifecycleStatus.SUBMITTED
    tracking_sub_events = [e for e in saved_rec.events if e.event_type == ApplicationLifecycleStatus.SUBMITTED]
    assert len(tracking_sub_events) == 1
    assert tracking_sub_events[0].source == EventSource.MANUAL
    assert notes in tracking_sub_events[0].notes


def test_prepare_application_rejects_placeholder_identity(in_memory_db):
    """Test prepare_application refuses to accept placeholder company or role."""
    service = DashboardService(db=in_memory_db)
    job = Job(
        job_id="job-dummy-id",
        title="Role unavailable",
        company="Target Company",
        description="Placeholder job description",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    with pytest.raises(ValueError, match="Cannot prepare application"):
        service.prepare_application("job-dummy-id")


def test_prepare_application_does_not_fabricate_dummy_url(in_memory_db):
    """Test prepare_application leaves canonical_job_url as None rather than generating a dummy URL."""
    service = DashboardService(db=in_memory_db)
    job = Job(
        job_id="job-valid-no-url",
        title="Platform Engineer",
        company="CloudFlare",
        description="Platform systems engineer",
        url=None,
        canonical_url=None,
        source="referral",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    detail = service.prepare_application("job-valid-no-url")
    assert detail.canonical_job_url is None


def test_portal_opened_state_is_backend_driven(in_memory_db, tmp_path):
    """Test that portal-opened state is entirely determined by backend application/timeline state."""
    track_store = TrackingStore(tracking_dir=tmp_path / "tracking")
    tracking_service = TrackingService(store=track_store)
    service = DashboardService(db=in_memory_db, tracking_service=tracking_service)

    job = Job(
        job_id="job-backend-driven-01",
        title="Site Reliability Engineer",
        company="Datadog",
        description="Core infra and SRE",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-backend-driven-01",
        job_id=job.id,
        job_id_str="job-backend-driven-01",
        company="Datadog",
        role="Site Reliability Engineer",
        canonical_job_url="https://boards.greenhouse.io/datadog/jobs/5544",
        source="greenhouse",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    # 1. Initially, no portal opened event on backend
    initial_detail = service.get_application_detail("app-backend-driven-01")
    assert not any(evt.event_type == "PORTAL_OPENED" for evt in initial_detail.timeline)

    # 2. Record portal opened via backend service
    updated_detail = service.record_portal_opened("app-backend-driven-01")
    assert any(evt.event_type == "PORTAL_OPENED" for evt in updated_detail.timeline)

    # 3. Simulate page reload / separate client request fetching detail fresh from backend
    reloaded_detail = service.get_application_detail("app-backend-driven-01")
    portal_events = [evt for evt in reloaded_detail.timeline if evt.event_type == "PORTAL_OPENED"]
    assert len(portal_events) == 1
    assert portal_events[0].source == "USER"


def test_continue_does_not_assume_ordinary_browser_login_available(in_memory_db):
    """Test continue application does not assume ordinary browser login is available to remote worker."""
    service = DashboardService(db=in_memory_db)

    job = Job(
        job_id="job-no-assumed-auth",
        title="Security Engineer",
        company="Stripe",
        description="Application security",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    # Application where portal was opened, but user has NOT connected browser session
    app = Application(
        application_id="app-no-assumed-auth",
        job_id=job.id,
        job_id_str="job-no-assumed-auth",
        company="Stripe",
        role="Security Engineer",
        canonical_job_url="https://boards.greenhouse.io/stripe/jobs/1122",
        source="greenhouse",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    # Pre-record portal opened event
    service.record_portal_opened("app-no-assumed-auth")

    # Continue must check for real authenticated session; finding none, must pause with clear required prompt
    detail = service.continue_application("app-no-assumed-auth")
    assert detail.browser_review is not None
    assert detail.browser_review.status == BrowserTaskStatus.LOGIN_REQUIRED.value
    expected_prompt = "Log in to the employer portal first, then connect an authenticated browser session to Job Copilot."
    assert detail.browser_review.pause_reason == expected_prompt
    assert detail.blocker_type == "LOGIN"
    assert detail.blocker_instruction == expected_prompt


def test_continue_never_submits_automatically(in_memory_db):
    """Test continue_application with active session queues task but never submits automatically."""
    service = DashboardService(db=in_memory_db)

    # Register an active authenticated session
    session = BrowserSessionModel(
        session_id="sess-active-valid-99",
        source="greenhouse",
        status=AuthenticatedSessionStatus.ACTIVE,
    )
    in_memory_db.add(session)

    job = Job(
        job_id="job-never-auto-submit",
        title="Cloud Engineer",
        company="Stripe",
        description="Cloud engineering role",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-never-auto-submit",
        job_id=job.id,
        job_id_str="job-never-auto-submit",
        company="Stripe",
        role="Cloud Engineer",
        canonical_job_url="https://boards.greenhouse.io/stripe/jobs/3344",
        source="greenhouse",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    detail = service.continue_application("app-never-auto-submit")

    # Browser task is QUEUED for filling safe fields, NOT completed or authorized
    assert detail.browser_review is not None
    assert detail.browser_review.status == BrowserTaskStatus.QUEUED.value

    # Application status must NEVER be APPLIED
    db_app = in_memory_db.query(Application).filter_by(application_id="app-never-auto-submit").first()
    assert db_app.status == ApplicationStatus.READY_TO_APPLY
    assert db_app.submitted_at is None
    assert detail.status != "SUBMITTED"

    # No submission event on timeline
    submission_events = [evt for evt in detail.timeline if evt.event_type == "SUBMITTED"]
    assert len(submission_events) == 0


def test_manual_submission_remains_distinct_from_automated_submission(in_memory_db, tmp_path):
    """Test that manual submission is distinct from automated submission and requires candidate confirmation."""
    track_store = TrackingStore(tracking_dir=tmp_path / "tracking")
    tracking_service = TrackingService(store=track_store)
    service = DashboardService(db=in_memory_db, tracking_service=tracking_service)

    job = Job(
        job_id="job-distinct-paths",
        title="Lead Platform Engineer",
        company="Linear",
        description="Platform architecture",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-distinct-paths",
        job_id=job.id,
        job_id_str="job-distinct-paths",
        company="Linear",
        role="Lead Platform Engineer",
        canonical_job_url="https://jobs.lever.co/linear/9900",
        source="lever",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    track_rec = ApplicationRecord(
        application_id="app-distinct-paths",
        job_id="job-distinct-paths",
        company="Linear",
        role="Lead Platform Engineer",
        current_status=ApplicationLifecycleStatus.PREPARED,
    )
    track_store.save_application(track_rec)

    # Manual submission requires explicit call to mark_application_submitted_manually
    manual_notes = "Candidate applied manually on Lever, ref #LIN-8821"
    detail = service.mark_application_submitted_manually("app-distinct-paths", user_notes=manual_notes)

    # Status updated
    assert detail.status == "SUBMITTED"
    assert detail.submitted_at is not None

    # Source is strictly MANUAL_CANDIDATE in DB and EventSource.MANUAL in TrackingStore
    db_events = in_memory_db.query(ApplicationEventModel).filter_by(application_id="app-distinct-paths").all()
    sub_events = [e for e in db_events if e.event_type == "SUBMITTED"]
    assert len(sub_events) == 1
    assert sub_events[0].source == "MANUAL_CANDIDATE"
    assert sub_events[0].metadata_json.get("submission_mode") == "MANUAL"
    assert manual_notes in sub_events[0].notes

    saved_rec = track_store.get_application("app-distinct-paths")
    tracking_sub_events = [e for e in saved_rec.events if e.event_type == ApplicationLifecycleStatus.SUBMITTED]
    assert len(tracking_sub_events) == 1
    assert tracking_sub_events[0].source == EventSource.MANUAL
