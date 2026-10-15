"""Regression tests for featured jobs removal and fail-closed job verification.

Proves:
1. Curated fixtures cannot be seeded into the production job database.
2. Hardcoded featured jobs never appear as live openings.
3. Generic career-home URLs cannot pass job-posting verification.
4. Closed/expired jobs cannot proceed to resume preparation.
5. Unverifiable jobs are marked unverified and require human review.
6. Real ingested jobs retain their correct canonical IDs.
7. Existing human-review and no-automatic-submission safeguards still pass.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from job_copilot.domain.enums import ApplicationStatus
from job_copilot.domain.featured_jobs import CURATED_FEATURED_JOBS
from job_copilot.copilot.models import CopilotJob, PriorityBand, QueueStatus
from job_copilot.models.base import Base
from job_copilot.models.application import Application
from job_copilot.models.job import Job
from job_copilot.services.dashboard_service import DashboardService
from job_copilot.services.job_verification_service import (
    JobVerificationService,
    JobVerificationStatus,
    JobVerificationResult,
)


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
    service.get_queue.return_value = []
    service.get_job.return_value = None
    service.orchestrator = None
    return service


@pytest.fixture
def mock_tracking_service():
    service = MagicMock()
    service.get_metrics.return_value = {
        "applied_count": 0,
        "interviews_scheduled": 0,
        "offers_received": 0,
        "rejections": 0,
        "pending_review": 0,
        "success_rate": 0.0,
    }
    service.get_recent_applications.return_value = []
    service.get_application.return_value = None
    service.get_application_by_job_id.return_value = None
    return service


@pytest.fixture
def dashboard_service(in_memory_db, mock_copilot_service, mock_tracking_service):
    return DashboardService(
        db=in_memory_db,
        copilot_service=mock_copilot_service,
        tracking_service=mock_tracking_service,
    )


# Invariant 1: Curated fixtures cannot be seeded into the production database
def test_curated_fixtures_cannot_be_seeded_into_database(dashboard_service, in_memory_db):
    assert len(CURATED_FEATURED_JOBS) == 0

    # _ensure_curated_job_exists is a deprecated no-op that returns None
    result = dashboard_service._ensure_curated_job_exists(in_memory_db, "featured-barclays-cloud")
    assert result is None

    # No jobs or applications created
    assert in_memory_db.query(Job).count() == 0
    assert in_memory_db.query(Application).count() == 0

    # Attempting to prepare an unseeded curated ID raises KeyError fail-closed
    with pytest.raises(KeyError, match="not found"):
        dashboard_service.prepare_application("featured-barclays-cloud")

    assert in_memory_db.query(Job).count() == 0
    assert in_memory_db.query(Application).count() == 0


# Invariant 2: Hardcoded featured jobs never appear as live openings
def test_hardcoded_featured_jobs_never_appear_as_live_openings(dashboard_service, mock_copilot_service):
    # Empty queue returns empty featured openings
    mock_copilot_service.get_queue.return_value = []
    overview = dashboard_service.get_overview()

    assert overview.featured_openings == []

    # Injecting only non-curated genuine jobs into copilot queue returns genuine jobs only
    real_job = CopilotJob(
        job_id="job-real-aws-01",
        title="Cloud Platform Engineer",
        company="RealCorp",
        location="Remote",
        source="career_site",
        priority_score=88.5,
        priority_band=PriorityBand.HIGH,
        queue_status=QueueStatus.NEW,
        match_score=88.5,
        canonical_url="https://jobs.realcorp.com/postings/cloud-01",
    )
    mock_copilot_service.get_queue.return_value = [real_job]

    overview_with_real = dashboard_service.get_overview()
    assert len(overview_with_real.featured_openings) == 1
    featured = overview_with_real.featured_openings[0]
    assert featured.job_id == "job-real-aws-01"
    assert featured.company == "RealCorp"
    assert featured.match_score == 88.5
    assert featured.canonical_url == "https://jobs.realcorp.com/postings/cloud-01"


# Invariant 3: Generic career-home URLs cannot pass job-posting verification
@pytest.mark.parametrize(
    "generic_url",
    [
        "https://mycareer.hsbc.com",
        "https://mycareer.hsbc.com/",
        "https://stripe.com/jobs",
        "https://stripe.com/careers",
        "https://mastercard.wd1.myworkdayjobs.com",
        "https://mastercard.wd1.myworkdayjobs.com/careers",
        "https://careers.google.com/jobs",
        "https://amazon.jobs/en",
        "https://careers.microsoft.com/us/en",
    ],
)
def test_generic_career_home_urls_cannot_pass_verification(generic_url):
    verifier = JobVerificationService()
    is_generic, reason = verifier.is_generic_careers_url(generic_url)
    assert is_generic is True
    assert len(reason) > 0

    result = verifier.verify_url_vacancy(generic_url)
    assert result.status == JobVerificationStatus.INVALID_GENERIC_URL
    assert result.is_available is False
    assert result.is_verified is False


def test_prepare_application_blocks_generic_career_url(dashboard_service, in_memory_db):
    # Ingest a job with a generic careers URL
    job = Job(
        job_id="job-generic-stripe",
        title="Backend Engineer",
        company="Stripe",
        url="https://stripe.com/jobs",
        description="Senior Backend Engineer role with Go and Ruby.",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    with pytest.raises(ValueError, match="generic company careers homepage"):
        dashboard_service.prepare_application("job-generic-stripe")


# Invariant 4: Closed/expired jobs cannot proceed to resume preparation
def test_closed_or_expired_jobs_cannot_proceed_to_resume_preparation(dashboard_service, in_memory_db):
    # Case A: Explicit lifecycle_status EXPIRED in DB
    job_expired = Job(
        job_id="job-expired-01",
        title="DevOps Engineer",
        company="OldCo",
        url="https://example.com/jobs/devops-expired",
        description="Kubernetes and Terraform infrastructure engineer.",
        lifecycle_status="EXPIRED",
    )
    in_memory_db.add(job_expired)
    in_memory_db.commit()

    with pytest.raises(ValueError, match="Job is closed or expired"):
        dashboard_service.prepare_application("job-expired-01")

    # Case B: Live URL returns closed/expired notice
    job_closed_online = Job(
        job_id="job-closed-online-02",
        title="Data Engineer",
        company="ClosedCorp",
        url="https://jobs.closedcorp.com/vacancies/data-02",
        description="Python and PySpark pipelines.",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job_closed_online)
    in_memory_db.commit()

    # Mock fetch returning closed body text
    dashboard_service.verification_service._default_fetch = MagicMock(
        return_value=(
            200,
            "https://jobs.closedcorp.com/vacancies/data-02",
            "<html><body>This position has been filled and is no longer available.</body></html>",
        )
    )

    with pytest.raises(ValueError, match="closed or expired"):
        dashboard_service.prepare_application("job-closed-online-02")


# Invariant 5: Unverifiable jobs are marked unverified and require human review
def test_unverifiable_jobs_are_marked_unverified_and_require_human_review(dashboard_service, in_memory_db):
    job_unverifiable = Job(
        job_id="job-unverifiable-03",
        title="Site Reliability Engineer",
        company="NetworkFlakyCorp",
        url="https://jobs.flakycorp.com/postings/sre-03",
        description="SRE on AWS, Prometheus, Grafana, Terraform.",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job_unverifiable)
    in_memory_db.commit()

    # Mock network timeout
    dashboard_service.verification_service._default_fetch = MagicMock(
        side_effect=TimeoutError("Network timeout connecting to host")
    )

    # Fail-closed without explicit manual verification confirmation
    with pytest.raises(ValueError, match="Unverified jobs require manual review"):
        dashboard_service.prepare_application("job-unverifiable-03", manual_verification_confirmed=False)

    # Permitted only when user explicitly confirms manual verification
    prep_result = dashboard_service.prepare_application("job-unverifiable-03", manual_verification_confirmed=True)
    assert prep_result.job_id == "job-unverifiable-03"
    assert prep_result.application_id is not None


# Invariant 6: Real ingested jobs retain their correct canonical IDs
def test_real_ingested_jobs_retain_their_correct_canonical_ids(dashboard_service, in_memory_db):
    canonical_job_id = "job-canonical-999-prod"
    canonical_app_id = "app-canonical-777-prod"

    job = Job(
        job_id=canonical_job_id,
        title="Staff Security Engineer",
        company="SecureTech",
        url="https://jobs.securetech.com/positions/staff-sec-999",
        description="Application security, threat modeling, Go, AWS security controls.",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    application = Application(
        application_id=canonical_app_id,
        job_id=job.id,
        job_id_str=canonical_job_id,
        company="SecureTech",
        role="Staff Security Engineer",
        status=ApplicationStatus.DISCOVERED,
    )
    in_memory_db.add(application)
    in_memory_db.commit()

    # Verify queue mapping resolves exact canonical IDs without manufacturing fallbacks
    queue_item = dashboard_service._to_dashboard_queue_item(
        CopilotJob(
            job_id=canonical_job_id,
            title="Staff Security Engineer",
            company="SecureTech",
            location="Remote",
            source="greenhouse",
            priority_score=95.0,
            priority_band=PriorityBand.CRITICAL,
            queue_status=QueueStatus.NEW,
            canonical_url="https://jobs.securetech.com/positions/staff-sec-999",
        )
    )

    assert queue_item.job_id == canonical_job_id
    assert queue_item.tracking_application_id == canonical_app_id
    assert "app-barclays-ce0266" not in queue_item.tracking_application_id

    # Mock live verification of the real job URL
    dashboard_service.verification_service._default_fetch = MagicMock(
        return_value=(
            200,
            "https://jobs.securetech.com/positions/staff-sec-999",
            "<html><body>Staff Security Engineer vacancy open for applications</body></html>",
        )
    )

    prep_res = dashboard_service.prepare_application(canonical_app_id)
    assert prep_res.job_id == canonical_job_id
    assert prep_res.application_id == canonical_app_id


# Invariant 7: Safeguards: Human review required and no automatic submission
def test_human_review_and_no_automatic_submission_safeguards_still_pass(dashboard_service, in_memory_db):
    job = Job(
        job_id="job-safe-001",
        title="Full Stack Engineer",
        company="SafetyFirst",
        url="https://jobs.safetyfirst.com/openings/fs-001",
        description="React and Python full stack development.",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    dashboard_service.verification_service._default_fetch = MagicMock(
        return_value=(
            200,
            "https://jobs.safetyfirst.com/openings/fs-001",
            "<html><body>Full Stack Engineer. Apply now!</body></html>",
        )
    )

    result = dashboard_service.prepare_application("job-safe-001")

    # Application prepared but NEVER automatically submitted
    app = in_memory_db.query(Application).filter_by(job_id_str="job-safe-001").first()
    assert app is not None
    assert app.status in (ApplicationStatus.READY_TO_APPLY, ApplicationStatus.PREPARING)
    assert app.status != ApplicationStatus.APPLIED
    assert result.status != "SUBMITTED"
    assert result.submitted_at is None
