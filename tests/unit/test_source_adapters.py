"""Unit tests for Phase 10C Source Adapters (LinkedIn, Naukri, Instahyre, Generic)."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.browser.models import BrowserElementType, BrowserField
from job_copilot.browser_worker.adapters import (
    GenericPortalAdapter,
    InstahyreAdapter,
    LinkedInAdapter,
    NaukriAdapter,
    SourceAdapterRegistry,
)
from job_copilot.browser_worker.browser import BrowserManager
from job_copilot.browser_worker.exceptions import DomainSecurityError
from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
from job_copilot.db.migrations_runner import run_migrations
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.application import Application
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.schemas.candidate import CandidateLink, CandidateProfile, PersonalInformation
from job_copilot.schemas.job import JobCreate


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
            links=[
                CandidateLink(label="LinkedIn", url="https://linkedin.com/in/alexmercer"),
                CandidateLink(label="GitHub", url="https://github.com/alexmercer"),
            ],
        )
    )


# ==============================================================================
# 1. Source Adapter Registry Tests
# ==============================================================================


def test_source_adapter_registry_resolution():
    """Verify adapter resolution by source name, domain matching, fallback, and rejection."""
    registry = SourceAdapterRegistry()

    # 1. Direct source match
    assert isinstance(registry.get_adapter(source="linkedin"), LinkedInAdapter)
    assert isinstance(registry.get_adapter(source="naukri"), NaukriAdapter)
    assert isinstance(registry.get_adapter(source="instahyre"), InstahyreAdapter)
    assert isinstance(registry.get_adapter(source="generic"), GenericPortalAdapter)

    # 2. Target URL domain resolution
    assert isinstance(registry.get_adapter(target_url="https://www.linkedin.com/jobs/view/12345"), LinkedInAdapter)
    assert isinstance(registry.get_adapter(target_url="https://www.naukri.com/job-listings-123"), NaukriAdapter)
    assert isinstance(registry.get_adapter(target_url="https://instahyre.com/job-123"), InstahyreAdapter)
    assert isinstance(registry.get_adapter(target_url="https://boards.greenhouse.io/corp/jobs/1"), GenericPortalAdapter)
    assert isinstance(registry.get_adapter(target_url="https://jobs.lever.co/corp/apply"), GenericPortalAdapter)

    # 3. Disallowed / Unknown domain rejection
    with pytest.raises(DomainSecurityError, match="No registered source adapter supports URL"):
        registry.get_adapter(target_url="https://untrusted-phishing-portal.com/apply")


# ==============================================================================
# 2. LinkedIn Adapter Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_linkedin_adapter_url_and_detection(db_session, mock_candidate_profile):
    """Verify LinkedInAdapter URL validation, login detection, CAPTCHA detection, and preparation."""
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    adapter = LinkedInAdapter()

    assert adapter.validate_url("https://www.linkedin.com/jobs/view/12345") is True
    assert adapter.validate_url("https://malicious.com/linkedin.com") is False

    task = BrowserTaskModel(
        task_id="task-li-001",
        application_id="app-li-001",
        source="linkedin",
        target_url="https://www.linkedin.com/jobs/view/12345",
        status=BrowserTaskStatus.QUEUED,
    )
    repo.create(task)

    mock_browser = MagicMock()
    mock_browser.launch = AsyncMock()
    mock_browser.navigate = AsyncMock(return_value="https://www.linkedin.com/jobs/view/12345")
    mock_browser.get_current_url = AsyncMock(return_value="https://www.linkedin.com/jobs/view/12345")
    mock_browser.wait_for_dom_idle = AsyncMock()
    mock_browser.screenshot = AsyncMock(return_value=None)
    mock_browser.is_captcha_present = AsyncMock(return_value=False)
    mock_browser.is_login_page = AsyncMock(return_value=False)
    mock_browser.inspect_page = AsyncMock(
        return_value=[
            BrowserField(field_id="f1", label="Full Name", element_type=BrowserElementType.INPUT_TEXT),
            BrowserField(field_id="f2", label="Email", element_type=BrowserElementType.INPUT_EMAIL),
        ]
    )
    mock_browser.fill_field = AsyncMock(return_value=True)
    mock_browser.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_browser)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(
        db=session,
        browser_manager=mock_manager,
        candidate_profile=mock_candidate_profile,
    )

    result = await executor.execute_task("task-li-001")
    assert result.status == BrowserTaskStatus.READY_FOR_REVIEW
    assert result.review_package_json["fields_autofilled"] == 2


# ==============================================================================
# 3. Naukri Adapter Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_naukri_adapter_url_and_detection(db_session, mock_candidate_profile):
    """Verify NaukriAdapter URL validation and login-wall pause behavior."""
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    adapter = NaukriAdapter()

    assert adapter.validate_url("https://www.naukri.com/job-listings-devops") is True

    task = BrowserTaskModel(
        task_id="task-nk-001",
        source="naukri",
        target_url="https://www.naukri.com/nlogin/login",
        status=BrowserTaskStatus.QUEUED,
    )
    repo.create(task)

    mock_browser = MagicMock()
    mock_browser.launch = AsyncMock()
    mock_browser.navigate = AsyncMock(return_value="https://www.naukri.com/nlogin/login")
    mock_browser.get_current_url = AsyncMock(return_value="https://www.naukri.com/nlogin/login")
    mock_browser.wait_for_dom_idle = AsyncMock()
    mock_browser.screenshot = AsyncMock(return_value=None)
    mock_browser.is_captcha_present = AsyncMock(return_value=False)
    mock_browser.is_login_page = AsyncMock(return_value=True)
    mock_browser.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_browser)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(
        db=session,
        browser_manager=mock_manager,
        candidate_profile=mock_candidate_profile,
    )

    result = await executor.execute_task("task-nk-001")
    assert result.status == BrowserTaskStatus.LOGIN_REQUIRED


# ==============================================================================
# 4. Instahyre Adapter Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_instahyre_adapter_url_and_captcha(db_session, mock_candidate_profile):
    """Verify InstahyreAdapter CAPTCHA detection and pause."""
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    adapter = InstahyreAdapter()

    assert adapter.validate_url("https://www.instahyre.com/job-1234-backend-engineer") is True

    task = BrowserTaskModel(
        task_id="task-ih-001",
        source="instahyre",
        target_url="https://www.instahyre.com/job-1234-backend-engineer",
        status=BrowserTaskStatus.QUEUED,
    )
    repo.create(task)

    mock_browser = MagicMock()
    mock_browser.launch = AsyncMock()
    mock_browser.navigate = AsyncMock(return_value="https://www.instahyre.com/job-1234-backend-engineer")
    mock_browser.get_current_url = AsyncMock(return_value="https://www.instahyre.com/job-1234-backend-engineer")
    mock_browser.wait_for_dom_idle = AsyncMock()
    mock_browser.screenshot = AsyncMock(return_value=None)
    mock_browser.is_captcha_present = AsyncMock(return_value=True)
    mock_browser.is_login_page = AsyncMock(return_value=False)
    mock_browser.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_browser)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(
        db=session,
        browser_manager=mock_manager,
        candidate_profile=mock_candidate_profile,
    )

    result = await executor.execute_task("task-ih-001")
    assert result.status == BrowserTaskStatus.CAPTCHA_REQUIRED


# ==============================================================================
# 5. Duplicate Application Guard Test (Phase 8 Integration)
# ==============================================================================


from job_copilot.schemas.application import ApplicationCreate

@pytest.mark.asyncio
async def test_duplicate_application_guard_blocks_preparation(db_session, mock_candidate_profile):
    """Verify that targeting an already SUBMITTED application blocks the task immediately."""
    session, _ = db_session
    task_repo = BrowserTaskRepository(session)
    app_repo = ApplicationRepository(session)

    job_repo = JobRepository(session)
    job = job_repo.create(JobCreate(title="Staff Engineer", company="Fintech Giant", location="Pune, India", source="linkedin", description="Staff Backend Role"))

    tracked_app = Application(
        application_id="app-dup-guard-101",
        job_id_str="job-dup-guard-101",
        job_id=job.id,
        company="Fintech Giant",
        role="Staff Engineer",
        source="linkedin",
        status=ApplicationStatus.APPLIED,
    )
    session.add(tracked_app)
    session.commit()
    session.refresh(tracked_app)

    # Create browser task for same application
    task = BrowserTaskModel(
        task_id="task-dup-guard-01",
        application_id="app-dup-guard-101",
        source="linkedin",
        target_url="https://www.linkedin.com/jobs/view/999",
        status=BrowserTaskStatus.QUEUED,
    )
    task_repo.create(task)

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(
        db=session,
        browser_manager=mock_manager,
        candidate_profile=mock_candidate_profile,
    )

    result = await executor.execute_task("task-dup-guard-01")
    assert result.status == BrowserTaskStatus.BLOCKED
    assert "DUPLICATE_APPLICATION" in result.pause_reason
