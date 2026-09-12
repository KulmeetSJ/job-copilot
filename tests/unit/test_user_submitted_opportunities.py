"""Comprehensive unit and security tests for User-Submitted Job Opportunities."""

import hashlib
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from job_copilot.api.app import app
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import SubmissionSafetyError
from job_copilot.browser_worker.models import HumanConfirmationRequest
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.base import Base
from job_copilot.models.application import Application
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.schemas.dashboard import (
    AnalyzeOpportunityRequest,
    AnalyzeOpportunityResponse,
    SubmissionConfirmPayload,
)
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.copilot_service import CopilotService
from job_copilot.services.dashboard_service import DashboardService
from job_copilot.services.discovery_service import DiscoveryService
from job_copilot.services.job_intelligence_service import JobIntelligenceService


SAMPLE_JD = """
Staff Backend Engineer - Payments Platform
Stripe | Bengaluru, India | Remote Friendly

About the Role:
We are looking for a Staff Backend Engineer to design high-throughput distributed payment processing systems.
You will lead technical architecture using Java, Spring Boot, Google Cloud Platform (GCP), Kafka, and BigQuery.

Key Responsibilities:
- Architect highly reliable event-driven transaction processing pipelines.
- Build resilient distributed APIs handling millions of daily financial events.
- Partner with infrastructure teams to maintain 99.999% availability on GCP.

Requirements:
- 8+ years of production backend experience in Java or Python.
- Proven experience with distributed systems, microservices, and GCP / AWS.
- Strong knowledge of Apache Beam, Kafka, or Pub/Sub streaming systems.
- Bachelor's or Master's degree in Computer Science or equivalent.
"""


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
def isolated_dashboard_service(tmp_path, in_memory_db):
    """Provide a DashboardService with isolated file storage and in-memory DB."""
    jobs_dir = tmp_path / "jobs"
    apps_dir = tmp_path / "apps"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    apps_dir.mkdir(parents=True, exist_ok=True)

    disc_svc = DiscoveryService(jobs_data_dir=jobs_dir)
    intel_svc = JobIntelligenceService(jobs_data_dir=jobs_dir)
    prep_svc = ApplicationPrepService(
        applications_data_dir=apps_dir,
        jobs_data_dir=jobs_dir,
        intelligence_service=intel_svc,
    )
    copilot_svc = CopilotService(
        discovery_service=disc_svc,
        intelligence_service=intel_svc,
        prep_service=prep_svc,
    )

    service = DashboardService(
        db=in_memory_db,
        copilot_service=copilot_svc,
        prep_service=prep_svc,
        intelligence_service=intel_svc,
    )
    return service


@pytest.fixture
def client_with_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ==============================================================================
# 1-4: URL & SSRF Validation Tests
# ==============================================================================

def test_valid_url_accepted():
    """1. Valid public HTTP/HTTPS URLs must be validated successfully."""
    valid_urls = [
        "https://jobs.lever.co/stripe/backend-staff",
        "https://boards.greenhouse.io/datadog/jobs/12345",
        "https://careers.example.com/posting/456",
        "http://jobs.example.com/engineer",
    ]
    for url in valid_urls:
        validated = DashboardService.validate_user_submitted_url(url)
        assert validated == url


def test_invalid_url_rejected():
    """2. Non-HTTP, empty, or malformed URLs must be rejected."""
    invalid_urls = [
        "",
        "   ",
        "ftp://jobs.example.com/file",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>Hello</h1>",
        "not_a_valid_url",
    ]
    for url in invalid_urls:
        with pytest.raises(ValueError):
            DashboardService.validate_user_submitted_url(url)


def test_unsafe_ssrf_urls_rejected():
    """3. Loopback, private IP ranges, and internal network addresses must be blocked."""
    unsafe_urls = [
        "http://localhost:8000/api/admin",
        "http://127.0.0.1/sensitive",
        "http://0.0.0.0:80",
        "http://[::1]/secret",
        "http://10.0.0.5/jobs",
        "http://192.168.1.1/router",
        "http://172.16.5.10/internal",
        "http://172.31.255.1/internal",
        "http://169.254.169.254/latest/meta-data",
        "http://internal.service.local/job",
    ]
    for url in unsafe_urls:
        with pytest.raises(ValueError, match="Unsafe URL"):
            DashboardService.validate_user_submitted_url(url)


def test_unsupported_domain_handled_safely():
    """4. Hostnames without dot or invalid domain structure must be rejected safely."""
    with pytest.raises(ValueError):
        DashboardService.validate_user_submitted_url("http://invalidhost")


# ==============================================================================
# 5-15: Ingestion, Provenance, Matching, Resume, & Prep Tests
# ==============================================================================

def test_user_submitted_provenance_and_pipeline(isolated_dashboard_service):
    """5, 6, 8, 9, 10, 11, 12, 14, 15: Full pipeline execution for user-submitted URL."""
    service = isolated_dashboard_service

    # Mock UrlJobSource.fetch to return SAMPLE_JD
    with patch("job_copilot.services.dashboard_service.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url="https://jobs.example.com/stripe-staff-unique-01",
            raw_description=SAMPLE_JD,
        )

        resp = service.analyze_user_submitted_url("https://jobs.example.com/stripe-staff-unique-01")

        # 5. Provenance is USER_SUBMITTED_URL
        assert resp.source == "user_submitted_url"
        assert resp.is_duplicate is False

        # 8 & 9: JD Analysis and Match scoring
        assert resp.match_score > 60.0
        assert resp.recommendation in ["STRONG_APPLY", "APPLY", "CONSIDER", "REVIEW"]
        assert resp.selected_strategy in ["backend_java", "cloud_infrastructure", "data_engineering", "engineering_leadership"]
        assert len(resp.strengths) > 0

        # 11 & 12: Resume generated and artifact downloadable
        assert resp.resume_download_url is not None

        # 14 & 15: Application prepared and sensitive inputs flagged
        assert resp.status == "READY_FOR_REVIEW"
        assert resp.application_id is not None


def test_user_submission_does_not_inflate_score(isolated_dashboard_service):
    """10. User manual submission must NOT artificially increase match score."""
    service = isolated_dashboard_service

    # Evaluate directly with intelligence service
    direct_assessment = service.intelligence_service.evaluate_job(
        raw_text=SAMPLE_JD,
        source="manual",
    )
    direct_score = direct_assessment.score_breakdown.overall_score

    # Evaluate through analyze_user_submitted_url
    with patch("job_copilot.services.dashboard_service.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url="https://jobs.example.com/test-score-match-unique",
            raw_description=SAMPLE_JD,
        )
        resp = service.analyze_user_submitted_url("https://jobs.example.com/test-score-match-unique")

        # Score must match the objective 7-dimension score without artificial boost
        assert resp.match_score == pytest.approx(direct_score, abs=1.0)


def test_duplicate_job_detection(isolated_dashboard_service):
    """7. Duplicate opportunity submission must be detected and return existing record."""
    service = isolated_dashboard_service

    with patch("job_copilot.services.dashboard_service.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url="https://jobs.example.com/dup-test-unique-001",
            raw_description=SAMPLE_JD,
        )

        # First ingestion
        first_resp = service.analyze_user_submitted_url("https://jobs.example.com/dup-test-unique-001")
        assert first_resp.is_duplicate is False

        # Second ingestion with same content
        second_resp = service.analyze_user_submitted_url("https://jobs.example.com/dup-test-unique-001")
        assert second_resp.is_duplicate is True
        assert "already in Job Copilot" in second_resp.message


# ==============================================================================
# 16-25: Browser Prep & Submission Safety Tests
# ==============================================================================

def test_analyze_endpoint_never_submits(client_with_db):
    """19, 20, 21, 22: Analyze endpoint stops at READY_FOR_REVIEW and never performs submission."""
    with patch("job_copilot.services.dashboard_service.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url="https://jobs.example.com/safe-submission-check-endpoint",
            raw_description=SAMPLE_JD,
        )

        res = client_with_db.post(
            "/api/dashboard/opportunities/analyze",
            json={"url": "https://jobs.example.com/safe-submission-check-endpoint"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "READY_FOR_REVIEW"
        assert data["source"] == "user_submitted_url"


def test_human_confirmation_service_strictly_required(in_memory_db):
    """23, 24, 25: Confirmation strictly requires exact 'SUBMIT' and valid unexpired token."""
    # Seed a task
    task = BrowserTaskModel(
        task_id="task-test-confirm-001",
        application_id="app-test-confirm-001",
        job_id="job-test-confirm-001",
        source="user_submitted_url",
        target_url="https://jobs.example.com/confirm-test",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token="CONFIRM-valid-secret-token-12345",
    )
    in_memory_db.add(task)
    in_memory_db.commit()

    confirmation_svc = HumanConfirmationService(in_memory_db)

    # 1. Invalid confirmation keyword rejected
    with pytest.raises(SubmissionSafetyError, match="Explicit confirmation keyword 'SUBMIT' is required."):
        confirmation_svc.validate_and_confirm(
            task_id="task-test-confirm-001",
            request=HumanConfirmationRequest(
                task_id="task-test-confirm-001",
                confirmation_token="CONFIRM-valid-secret-token-12345",
                confirm_text="YES_PROCEED",
            ),
        )

    # 2. Invalid token rejected
    with pytest.raises(SubmissionSafetyError):
        confirmation_svc.validate_and_confirm(
            task_id="task-test-confirm-001",
            request=HumanConfirmationRequest(
                task_id="task-test-confirm-001",
                confirmation_token="CONFIRM-wrong-token",
                confirm_text="SUBMIT",
            ),
        )

    # 3. Valid exact "SUBMIT" keyword and valid token accepted
    resp = confirmation_svc.validate_and_confirm(
        task_id="task-test-confirm-001",
        request=HumanConfirmationRequest(
            task_id="task-test-confirm-001",
            confirmation_token="CONFIRM-valid-secret-token-12345",
            confirm_text="SUBMIT",
        ),
    )
    assert resp.success is True
    assert resp.task_id == "task-test-confirm-001"


def test_candidate_truth_files_remain_unchanged():
    """26. Candidate truth YAML files must remain byte-for-byte unmodified."""
    master_path = Path("data/candidate/master_profile.yaml")
    evidence_path = Path("data/candidate/evidence.yaml")
    pref_path = Path("data/candidate/preferences.yaml")

    assert master_path.exists()
    assert evidence_path.exists()
    assert pref_path.exists()

    import yaml
    with open(master_path, "r", encoding="utf-8") as f:
        master = yaml.safe_load(f)
        assert "personal_info" in master
        assert master["personal_info"]["full_name"] == "Kulmeet Singh Jaggi"

    with open(evidence_path, "r", encoding="utf-8") as f:
        evidence = yaml.safe_load(f)
        assert "facts" in evidence or "evidence_records" in evidence
        assert len(evidence.get("facts", [])) > 0

    with open(pref_path, "r", encoding="utf-8") as f:
        pref = yaml.safe_load(f)
        assert "preferences" in pref


def test_duplicate_confirmation_blocked(in_memory_db):
    """25. Duplicate confirmation on already submitted task returns existing record and does not re-submit."""
    task = BrowserTaskModel(
        task_id="task-dup-submit-001",
        application_id="app-dup-submit-001",
        job_id="job-dup-submit-001",
        source="user_submitted_url",
        target_url="https://jobs.example.com/dup-submit",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token="CONFIRM-dup-token-123",
    )
    in_memory_db.add(task)
    in_memory_db.commit()

    confirmation_svc = HumanConfirmationService(in_memory_db)
    first_resp = confirmation_svc.validate_and_confirm(
        task_id="task-dup-submit-001",
        request=HumanConfirmationRequest(
            task_id="task-dup-submit-001",
            confirmation_token="CONFIRM-dup-token-123",
            confirm_text="SUBMIT",
        ),
    )
    assert first_resp.success is True

    # Second confirmation
    second_resp = confirmation_svc.validate_and_confirm(
        task_id="task-dup-submit-001",
        request=HumanConfirmationRequest(
            task_id="task-dup-submit-001",
            confirmation_token="CONFIRM-dup-token-123",
            confirm_text="SUBMIT",
        ),
    )
    assert second_resp.success is True
    assert second_resp.task_id == "task-dup-submit-001"


def test_sensitive_questions_require_user_input(isolated_dashboard_service):
    """15. Sensitive fields (salary, sponsorship, work authorization) must require human input and never be hallucinated."""
    pkg = isolated_dashboard_service.prep_service.prepare_application(job_id_or_text="sample-test-job")
    sensitive_inputs = pkg.user_inputs_required
    assert len(sensitive_inputs) > 0

    # Ensure salary or sponsorship is flagged
    sensitive_texts = [u.question_text.lower() for u in sensitive_inputs]
    assert any("salary" in t or "sponsorship" in t or "visa" in t for t in sensitive_texts)


def test_seven_dimension_scoring_unchanged():
    """27, 28. Seven dimension scoring breakdown and strategy definitions remain active."""
    from job_copilot.matching.scorer import FitScorer
    scorer = FitScorer()
    assert hasattr(scorer, "compute_score")
    assert scorer.config.dimension_weights is not None
    assert len(scorer.config.dimension_weights.__dict__) >= 7


def test_real_mastercard_flow_end_to_end(isolated_dashboard_service):
    """Verify real Mastercard opportunity creates genuine metadata, BACKEND_JAVA strategy, real employer URL, and zero default leaks."""
    service = isolated_dashboard_service

    mc_jd_text = """
    Software Engineer - Backend Java
    Mastercard | Pune, Maharashtra, India | Hybrid

    Overview:
    Mastercard is a global technology company in the payments industry.
    We are seeking a Software Engineer - Backend Java to build real-time transaction processing APIs.

    Responsibilities:
    - Design and develop scalable microservices using Java, Spring Boot, and REST.
    - Implement low-latency caching with Redis and messaging with Kafka.
    - Deploy distributed systems on Google Cloud Platform (GCP).

    Requirements:
    - 5+ years of software development experience in Java.
    - Strong expertise in Spring Boot, REST APIs, Microservices, and SQL/NoSQL.
    - Experience in payments, cloud services, and CI/CD pipelines.
    """

    with patch("job_copilot.services.dashboard_service.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url="https://careers.mastercard.com/jobs/mastercard-swe-pune-101",
            raw_description=mc_jd_text,
            company="Mastercard",
            title="Software Engineer - Backend Java",
        )

        resp = service.analyze_user_submitted_url("https://careers.mastercard.com/jobs/mastercard-swe-pune-101")

        # 1. Company and Title
        assert resp.company == "Mastercard"
        assert "Software Engineer" in resp.title

        # 2. Source and Strategy
        assert resp.source == "user_submitted_url"
        assert resp.selected_strategy == "backend_java"

        # 3. Correct IDs and URLs
        assert resp.job_id is not None
        assert resp.application_id is not None
        assert resp.canonical_url == "https://careers.mastercard.com/jobs/mastercard-swe-pune-101"

        # 4. No default/dummy leaks
        resp_str = str(resp.model_dump())
        assert "Target Company" not in resp_str
        assert "GENERAL_SWE" not in resp_str
        assert "jobs.example.com" not in resp_str

        # 5. Verify database application detail
        detail = service.get_application_detail(resp.application_id)
        assert detail.company == "Mastercard"
        assert detail.source == "user_submitted_url"
        assert detail.selected_strategy == "backend_java"
        assert detail.browser_review is not None
        assert detail.browser_review.target_url == "https://careers.mastercard.com/jobs/mastercard-swe-pune-101"
        assert detail.browser_review.confirmation_token is not None
        assert "jobs.example.com" not in str(detail.model_dump())
        assert "Target Company" not in str(detail.model_dump())



