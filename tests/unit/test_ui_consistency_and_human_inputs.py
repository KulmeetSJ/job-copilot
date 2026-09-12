"""
Regression tests for:
1. Persistent human inputs across reload and Reprepare (Bug 1)
2. Barclays application identity resolution and placeholder elimination (Bug 2)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from job_copilot.api.app import app
from job_copilot.db.database import get_db
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.base import Base
from job_copilot.models.application import Application
from job_copilot.models.job import Job
from job_copilot.schemas.dashboard import HumanInputAnswerItem, HumanInputSubmitRequest
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.dashboard_service import DashboardService
from job_copilot.services.discovery_service import DiscoveryService
from job_copilot.services.job_intelligence_service import JobIntelligenceService
from job_copilot.services.tracking_service import TrackingService


BARCLAYS_SAMPLE_JD = """
Software Engineer – Infrastructure
Barclays | London, UK | Hybrid

About the Role:
Barclays is seeking a Software Engineer – Infrastructure to design and maintain our core banking backend platforms.
You will build scalable infrastructure services, automated deployment pipelines, and microservices in Python and Java.

Requirements:
- Proven experience in backend infrastructure, cloud computing, and CI/CD pipelines.
- Proficiency in Python, Linux, and Kubernetes.
- Experience with high-availability systems in financial services.
"""


@pytest.fixture
def test_env(tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create temporary isolated directories for data
    apps_dir = tmp_path / "applications"
    jobs_dir = tmp_path / "jobs"
    tracking_dir = tmp_path / "tracking"
    apps_dir.mkdir(parents=True, exist_ok=True)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    tracking_dir.mkdir(parents=True, exist_ok=True)

    master_profile_path = Path("data/candidate/master_profile.yaml")

    prep_service = ApplicationPrepService(
        master_profile_path=master_profile_path,
        applications_data_dir=apps_dir,
        jobs_data_dir=jobs_dir,
    )

    intel_service = JobIntelligenceService(
        master_profile_path=master_profile_path,
        jobs_data_dir=jobs_dir,
    )

    tracking_service = TrackingService(tracking_dir=tracking_dir)

    dashboard_service = DashboardService(
        db=session,
        prep_service=prep_service,
        tracking_service=tracking_service,
        intelligence_service=intel_service,
    )

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[lambda: dashboard_service] = lambda: dashboard_service
    client = TestClient(app)

    yield {
        "db": session,
        "dashboard_service": dashboard_service,
        "prep_service": prep_service,
        "tracking_service": tracking_service,
        "client": client,
        "apps_dir": apps_dir,
    }

    app.dependency_overrides.clear()
    session.close()


def test_saved_sensitive_answers_survive_reload(test_env):
    """
    Regression Test 1: Saved sensitive answers (visa sponsorship & salary)
    persist across detail reloads and populate current_value in Application Review.
    """
    svc = test_env["dashboard_service"]
    client = test_env["client"]

    # 1. Ingest a job opportunity
    with patch("job_copilot.ingestion.sources.url.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url="https://jobs.example.com/software-engineer",
            raw_description=BARCLAYS_SAMPLE_JD,
        )
        analyzed = svc.analyze_user_submitted_url("https://jobs.example.com/software-engineer")

    app_id = analyzed.application_id
    assert app_id is not None
    assert analyzed.needs_user_input_count > 0

    # 2. Save user inputs for sensitive questions
    save_payload = HumanInputSubmitRequest(
        answers=[
            HumanInputAnswerItem(
                question_id="q-sponsorship",
                question_text="Will you require visa sponsorship?",
                answer_value="Authorized to work with No sponsorship required.",
            ),
            HumanInputAnswerItem(
                question_id="q-salary",
                question_text="What are your salary expectations?",
                answer_value="$160,000 USD base salary",
            ),
        ]
    )
    submit_res = svc.submit_user_inputs(app_id, save_payload)

    # Verify submit response contains hydrated current_values
    uir_map = {u.question_id: u.current_value for u in submit_res.user_inputs_required}
    assert uir_map.get("q-sponsorship") == "Authorized to work with No sponsorship required."
    assert uir_map.get("q-salary") == "$160,000 USD base salary"

    # 3. Simulate page reload / fresh get_application_detail call
    reloaded = svc.get_application_detail(app_id)
    reloaded_uir_map = {u.question_id: u.current_value for u in reloaded.user_inputs_required}
    assert reloaded_uir_map.get("q-sponsorship") == "Authorized to work with No sponsorship required."
    assert reloaded_uir_map.get("q-salary") == "$160,000 USD base salary"

    # Verify prepared answers have the human inputs and no longer require input
    prep_ans_map = {a.field_name: a for a in reloaded.prepared_answers}
    assert prep_ans_map["q-sponsorship"].answer_text == "Authorized to work with No sponsorship required."
    assert prep_ans_map["q-sponsorship"].requires_user_input is False
    assert "USER_INPUT" in prep_ans_map["q-sponsorship"].source_evidence


def test_saved_sensitive_answers_survive_reprepare(test_env):
    """
    Regression Test 2: Saved sensitive answers survive package regeneration / Reprepare.
    Reprepare must never erase existing human inputs.
    """
    svc = test_env["dashboard_service"]

    # 1. Ingest job
    with patch("job_copilot.ingestion.sources.url.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url="https://jobs.example.com/backend-role",
            raw_description=BARCLAYS_SAMPLE_JD,
        )
        analyzed = svc.analyze_user_submitted_url("https://jobs.example.com/backend-role")

    app_id = analyzed.application_id

    # 2. Save human answers
    svc.submit_user_inputs(
        app_id,
        HumanInputSubmitRequest(
            answers=[
                HumanInputAnswerItem(
                    question_id="q-sponsorship",
                    question_text="Will you require visa sponsorship?",
                    answer_value="Permanent Resident - No sponsorship needed",
                ),
                HumanInputAnswerItem(
                    question_id="q-salary",
                    question_text="What are your salary expectations?",
                    answer_value="140k GBP",
                ),
            ]
        ),
    )

    # 3. Trigger Reprepare (prepare_application)
    reprepared_detail = svc.prepare_application(app_id)

    # Verify user inputs survived package regeneration
    uir_map = {u.question_id: u.current_value for u in reprepared_detail.user_inputs_required}
    assert uir_map.get("q-sponsorship") == "Permanent Resident - No sponsorship needed"
    assert uir_map.get("q-salary") == "140k GBP"

    prep_ans_map = {a.field_name: a for a in reprepared_detail.prepared_answers}
    assert prep_ans_map["q-sponsorship"].answer_text == "Permanent Resident - No sponsorship needed"
    assert prep_ans_map["q-sponsorship"].requires_user_input is False


def test_overview_and_application_review_resolve_same_identity(test_env):
    """
    Regression Test 3: Overview and Application Review resolve the exact same
    application/job identity, company, role, and canonical URL.
    """
    svc = test_env["dashboard_service"]

    barclays_url = "https://search.jobs.barclays/job/-/-/13015/98832951728?src=JB-12860"

    with patch("job_copilot.ingestion.sources.url.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url=barclays_url,
            raw_description=BARCLAYS_SAMPLE_JD,
        )
        overview_resp = svc.analyze_user_submitted_url(barclays_url)

    # Overview attributes
    assert overview_resp.company == "Barclays"
    assert "Software Engineer" in overview_resp.title
    assert overview_resp.canonical_url == barclays_url

    # Query list_applications (which feeds the Review dropdown)
    apps_list = svc.list_applications()
    matching_apps = [a for a in apps_list if a.company == "Barclays"]
    assert len(matching_apps) >= 1
    dropdown_app = matching_apps[0]

    # Application Review detail query using dropdown's ID
    review_resp = svc.get_application_detail(dropdown_app.application_id)

    # Identity alignment invariant: exact same company, role, and canonical URL
    assert review_resp.company == overview_resp.company
    assert review_resp.role == overview_resp.title
    assert review_resp.canonical_job_url == overview_resp.canonical_url
    assert review_resp.match_score == overview_resp.match_score


def test_barclays_displays_real_company_role_source(test_env):
    """
    Regression Test 4: Barclays application displays its real company (Barclays),
    role (Software Engineer – Infrastructure), and source (user_submitted_url).
    """
    svc = test_env["dashboard_service"]
    barclays_url = "https://search.jobs.barclays/job/-/-/13015/98832951728?src=JB-12860"

    with patch("job_copilot.ingestion.sources.url.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url=barclays_url,
            raw_description=BARCLAYS_SAMPLE_JD,
        )
        analyzed = svc.analyze_user_submitted_url(barclays_url)

    detail = svc.get_application_detail(analyzed.application_id)
    assert detail.company == "Barclays"
    assert detail.role == "Software Engineer – Infrastructure"
    assert detail.source == "user_submitted_url"
    assert detail.canonical_job_url == barclays_url


def test_barclays_shows_same_needs_input_count(test_env):
    """
    Regression Test 5: Barclays shows the same Needs Input count in both
    Overview (analyze response) and Application Review.
    """
    svc = test_env["dashboard_service"]
    barclays_url = "https://search.jobs.barclays/job/-/-/13015/98832951728?src=JB-12860"

    with patch("job_copilot.ingestion.sources.url.UrlJobSource.fetch") as mock_fetch:
        from job_copilot.ingestion.models import RawJob
        mock_fetch.return_value = RawJob(
            source="user_submitted_url",
            source_url=barclays_url,
            raw_description=BARCLAYS_SAMPLE_JD,
        )
        overview_resp = svc.analyze_user_submitted_url(barclays_url)

    review_detail = svc.get_application_detail(overview_resp.application_id)

    # Needs input count in overview vs review
    assert overview_resp.needs_user_input_count == len(review_detail.user_inputs_required)
    assert len(review_detail.user_inputs_required) == 2  # Visa sponsorship and salary expectations


def test_no_fallback_placeholders_when_resolution_fails(test_env):
    """
    Regression Test 6: No fallback company/role/source ('Company unavailable',
    'Role unavailable', 'Source unavailable', 'Target Company', 'GENERAL_SWE')
    is generated when resolution fails; an explicit ValueError is raised instead.
    """
    svc = test_env["dashboard_service"]

    # Non-existent random application ID
    with pytest.raises(ValueError) as exc_info:
        svc.get_application_detail("app-nonexistent-999999")

    err_msg = str(exc_info.value).lower()
    assert "could not resolve canonical application data" in err_msg or "not found" in err_msg
