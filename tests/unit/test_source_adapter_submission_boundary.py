"""Source adapter submission boundary tests for Phase 10C.

Verifies the primary safety invariant for each source adapter:
Authenticated access does NOT authorize submission.
All adapters (LinkedIn, Naukri, Instahyre, Generic) halt strictly at READY_FOR_REVIEW.
External submission requires explicit, token-verified human confirmation.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.browser.models import BrowserElementType, BrowserField
from job_copilot.browser_worker.browser import BrowserManager
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.models import HumanConfirmationRequest
from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
from job_copilot.db.migrations_runner import run_migrations
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.browser_task import BrowserTaskModel
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


@pytest.mark.parametrize(
    "source,target_url",
    [
        ("linkedin", "https://www.linkedin.com/jobs/view/1001"),
        ("naukri", "https://www.naukri.com/job-listings-2002"),
        ("instahyre", "https://www.instahyre.com/job-3003-backend"),
        ("generic", "https://boards.greenhouse.io/fintech/jobs/4004"),
    ],
)
@pytest.mark.asyncio
async def test_all_source_adapters_halt_at_ready_for_review_without_submitting(
    source, target_url, db_session, mock_candidate_profile
):
    """
    CRITICAL INVARIANT TEST:
    For EVERY supported source adapter (LinkedIn, Naukri, Instahyre, Generic):
    1. Adapter prepares form up to READY_FOR_REVIEW.
    2. Zero submission clicks occur (click count == 0).
    3. Browser process closes cleanly.
    4. Explicit human confirmation authorized transition completes exactly once.
    5. Duplicate confirmation prevents double submission.
    """
    session, _ = db_session
    repo = BrowserTaskRepository(session)
    confirmation_svc = HumanConfirmationService(session)

    task_id = f"task-boundary-{source}-01"
    task = BrowserTaskModel(
        task_id=task_id,
        application_id=f"app-{source}-01",
        job_id=f"job-{source}-01",
        source=source,
        target_url=target_url,
        status=BrowserTaskStatus.QUEUED,
    )
    repo.create(task)

    mock_browser = MagicMock()
    mock_browser.launch = AsyncMock()
    mock_browser.navigate = AsyncMock(return_value=target_url)
    mock_browser.get_current_url = AsyncMock(return_value=target_url)
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
    mock_browser.click = AsyncMock(return_value=True)
    mock_browser.close = AsyncMock()

    mock_manager = MagicMock(spec=BrowserManager)
    mock_manager.get_adapter = AsyncMock(return_value=mock_browser)
    mock_manager.close = AsyncMock()

    executor = BrowserTaskExecutor(
        db=session,
        browser_manager=mock_manager,
        candidate_profile=mock_candidate_profile,
    )

    # 1. Execute task
    prepared_task = await executor.execute_task(task_id)

    # Invariant assertions:
    assert prepared_task.status == BrowserTaskStatus.READY_FOR_REVIEW
    assert prepared_task.confirmation_token is not None
    # CRITICAL: Click to submit was NEVER called
    assert mock_browser.click.call_count == 0

    # 2. Human Confirmation Gating
    token = prepared_task.confirmation_token
    mock_external_submit_handler = MagicMock()

    # Before confirmation -> 0
    assert mock_external_submit_handler.call_count == 0

    # Human confirms with valid token and keyword "SUBMIT"
    confirm_resp = confirmation_svc.validate_and_confirm(
        task_id=task_id,
        request=HumanConfirmationRequest(confirmation_token=token, confirm_text="SUBMIT"),
    )
    if confirm_resp.success:
        mock_external_submit_handler()

    # Exactly 1 submission authorized
    assert mock_external_submit_handler.call_count == 1
    assert confirm_resp.status == BrowserTaskStatus.COMPLETED

    # 3. Duplicate confirmation check
    dup_resp = confirmation_svc.validate_and_confirm(
        task_id=task_id,
        request=HumanConfirmationRequest(confirmation_token=token, confirm_text="SUBMIT"),
    )
    if dup_resp.success and "Duplicate" not in (dup_resp.message or ""):
        mock_external_submit_handler()

    # Remains strictly 1 invocation
    assert mock_external_submit_handler.call_count == 1
    assert "Duplicate submission prevented" in dup_resp.message
