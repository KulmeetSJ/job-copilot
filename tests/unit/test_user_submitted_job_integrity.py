"""Regression and data integrity tests for user-submitted opportunity ingestion and pipeline lifecycle."""

from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from job_copilot.domain.enums import ApplicationStatus, ResumeStrategy
from job_copilot.ingestion.models import RawJob
from job_copilot.models.application import Application
from job_copilot.models.browser_task import BrowserTaskModel, BrowserTaskStatus
from job_copilot.models.job import Job
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.dashboard_service import DashboardService, resolve_canonical_application_state
from job_copilot.services.discovery_service import DiscoveryService
from job_copilot.services.copilot_service import CopilotService


def test_user_submitted_workday_url_end_to_end_integrity(db_session: Session, tmp_path):
    """
    Verify submitting a Workday URL extracts real company, title, provenance,
    canonical strategy, and never generates 'Target Company' or 'GENERAL_SWE'.
    """
    discovery_service = DiscoveryService(jobs_data_dir=tmp_path / "jobs")
    copilot_service = CopilotService(discovery_service=discovery_service)
    service = DashboardService(db=db_session, copilot_service=copilot_service)
    workday_url = "https://mastercard.wd1.myworkdayjobs.com/en-US/CorporateCareers/job/Pune-India/Software-Engineer-II-Backend_R-202612"

    mock_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Software Engineer II - Backend - Mastercard Careers - Workday</title>
        <meta property="og:site_name" content="Mastercard" />
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Software Engineer II - Backend",
            "hiringOrganization": {
                "@type": "Organization",
                "name": "Mastercard"
            },
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "addressLocality": "Pune",
                    "addressCountry": "India"
                }
            },
            "description": "We are seeking a Software Engineer II - Backend to join Mastercard in Pune. Requirements: Java, Spring Boot, Microservices, REST APIs, PostgreSQL, Kafka, GCP. 2+ years experience required."
        }
        </script>
    </head>
    <body>
        <div id="root">Loading Workday Application...</div>
    </body>
    </html>
    """

    mock_raw_job = RawJob(
        source="user_submitted_url",
        source_url=workday_url,
        company="Mastercard",
        title="Software Engineer II - Backend",
        location="Pune, India",
        raw_description=mock_html,
    )

    with patch("job_copilot.services.dashboard_service.UrlJobSource.fetch", return_value=mock_raw_job):
        response = service.analyze_user_submitted_url(workday_url)

    assert response.company == "Mastercard"
    assert "Mastercard" in response.company
    assert "We" not in response.company
    assert response.company != "Target Company"
    assert response.source == "user_submitted_url"
    assert response.selected_strategy in ["backend_java", "cloud_devops", "data_engineering", "full_stack", "sre_devops"]
    assert response.selected_strategy != "GENERAL_SWE"
    assert response.selected_strategy != "general_swe"

    # Verify persisted DB records
    job_repo = JobRepository(db_session)
    db_job = job_repo.get_by_job_id(response.job_id)
    assert db_job is not None
    assert db_job.company == "Mastercard"
    assert db_job.source == "user_submitted_url"

    app_repo = ApplicationRepository(db_session)
    db_app = app_repo.get_by_application_id(response.application_id)
    assert db_app is not None
    assert db_app.company == "Mastercard"
    assert db_app.source == "user_submitted_url"
    assert db_app.resume_strategy in ["backend_java", "cloud_devops", "data_engineering", "full_stack", "sre_devops"]


def test_prep_service_rejects_missing_id_as_raw_jd():
    """
    Verify ApplicationPrepService raises explicit ValueError when given a missing ID,
    preventing ID strings from being reinterpreted as JD text yielding 'Target Company'.
    """
    prep_service = ApplicationPrepService()
    nonexistent_id = "app-usr-nonexistent-12345"

    with pytest.raises(ValueError, match="not found"):
        prep_service.prepare_application(job_id_or_text=nonexistent_id)


def test_canonical_strategy_enumeration():
    """Verify exactly 5 canonical strategies and alias normalization."""
    canonical_set = {"backend_java", "cloud_devops", "data_engineering", "full_stack", "sre_devops"}
    assert {s.value for s in ResumeStrategy} == canonical_set

    # Test alias mappings
    assert ResumeStrategy.normalize("GENERAL_SWE") == "backend_java"
    assert ResumeStrategy.normalize("general_swe") == "backend_java"
    assert ResumeStrategy.normalize("cloud_infrastructure") == "cloud_devops"
    assert ResumeStrategy.normalize("cloud_data") == "data_engineering"
    assert ResumeStrategy.normalize("platform_devops") == "sre_devops"
    assert ResumeStrategy.normalize(None) == "backend_java"


def test_overview_unverified_status_not_counted_as_submitted(db_session: Session):
    """
    Verify historical unverified Mastercard record remains SUBMISSION_UNVERIFIED
    and does not inflate submitted count.
    """
    app = Application(
        application_id="app-usr-2a43a63d",
        job_id=999,
        job_id_str="mastercard-software-engineer-backend-java-b5bb2c",
        company="Mastercard",
        role="Software Engineer - Backend Java",
        source="user_submitted_url",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    task = BrowserTaskModel(
        task_id="task-mastercard-001",
        application_id="app-usr-2a43a63d",
        job_id="mastercard-software-engineer-backend-java-b5bb2c",
        status=BrowserTaskStatus.SUBMISSION_UNVERIFIED,
    )

    canonical_state = resolve_canonical_application_state(app=app, browser_task=task)
    assert canonical_state == "SUBMISSION_UNVERIFIED"
    assert canonical_state != "SUBMITTED"
