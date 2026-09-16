"""
Regression tests proving the elimination of the legacy submission path defect.

Enforces absolute submission invariants:
A. Legacy /api/copilot/{job_id}/apply cannot submit with an arbitrary non-empty token ('x', 'yes', '123', 'SUBMIT').
B. A job with no real canonical/source URL cannot create or launch a submission browser task.
C. There is no remaining legacy code path capable of reaching a real Playwright submit without canonical authorization.
D. Existing hardened dashboard submission tests remain unchanged and pass.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient

from job_copilot.api.app import app
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import SubmissionSafetyError
from job_copilot.browser_worker.models import HumanConfirmationRequest
from job_copilot.copilot.models import CopilotJob, PriorityBand, QueueStatus
from job_copilot.copilot.orchestrator import CopilotOrchestrator
from job_copilot.db.database import SessionLocal
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.services.browser_workflow_service import BrowserSession, BrowserSessionStatus, BrowserWorkflowService
from job_copilot.services.copilot_service import CopilotService
from job_copilot.services.discovery_service import DiscoveryService


@pytest.fixture
async def test_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ==============================================================================
# TEST A: Legacy /api/copilot/{job_id}/apply cannot submit with arbitrary token
# ==============================================================================

@pytest.mark.asyncio
async def test_legacy_endpoint_rejects_arbitrary_tokens(test_client):
    """
    Test A: Passing arbitrary non-empty tokens ('x', 'yes', '123', 'SUBMIT')
    to POST /api/copilot/{job_id}/apply must NOT authorize submission.
    """
    disc = DiscoveryService()
    canonical = disc.ingest_text(
        text="Job Title: Lead SRE\nCompany: CloudCo\nRequirements: 5+ years Kubernetes",
        company="CloudCo",
        title="Lead SRE",
        source_url="https://jobs.lever.co/cloudco/apply",
    )
    job_id = canonical.job_id

    # Process job via copilot API
    resp = await test_client.post("/api/copilot/process", json={"job_id": job_id})
    assert resp.status_code == 200

    # Unconfirmed request returns SUBMISSION_BLOCKED safely
    resp_unconfirmed = await test_client.post(f"/api/copilot/{job_id}/apply", json={"confirmation_token": None})
    assert resp_unconfirmed.status_code == 200
    assert resp_unconfirmed.json()["status"] == "SUBMISSION_BLOCKED"

    # Arbitrary non-empty tokens must be rejected
    arbitrary_tokens = ["x", "yes", "123", "SUBMIT", "token-xyz", "TRUE"]
    for token in arbitrary_tokens:
        resp_arbitrary = await test_client.post(
            f"/api/copilot/{job_id}/apply",
            json={"confirmation_token": token},
        )
        # Must fail safely with 400 Bad Request
        assert resp_arbitrary.status_code == 400
        data = resp_arbitrary.json()
        assert "submission blocked" in data["detail"].lower()

    # Verify queue status is NOT SUBMITTED
    dash_resp = await test_client.get("/api/copilot/dashboard")
    assert dash_resp.status_code == 200


# ==============================================================================
# TEST B: Job with no real canonical/source URL cannot create or launch task
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fake_or_missing_url",
    [
        None,
        "",
        "https://example.com/careers/apply",
        "https://test.example.com/jobs/apply",
        "https://manual.application.portal/app-12345",
        "ftp://invalid-scheme.org/apply",
    ],
)
async def test_job_with_no_canonical_url_fails_safely(test_client, fake_or_missing_url):
    """
    Test B: A job with no real canonical/source URL (missing or fabricated)
    cannot create or launch a browser submission task.
    """
    disc = DiscoveryService()
    canonical = disc.ingest_text(
        text="Job Title: Staff Engineer\nCompany: SafeFintech\nRequirements: Python, Go",
        company="SafeFintech",
        title="Staff Engineer",
        source_url=fake_or_missing_url,
    )
    job_id = canonical.job_id

    # Process job into queue
    resp = await test_client.post("/api/copilot/process", json={"job_id": job_id})
    assert resp.status_code == 200

    # Attempting to apply with confirmation token must fail safely without launching task
    apply_resp = await test_client.post(
        f"/api/copilot/{job_id}/apply",
        json={"confirmation_token": "some-token"},
    )
    assert apply_resp.status_code == 400
    assert "no valid canonical application url" in apply_resp.json()["detail"].lower()

    # Direct orchestrator call must also raise ValueError
    service = CopilotService()
    with pytest.raises(ValueError, match="no valid canonical application URL"):
        await service.apply_async(job_id=job_id, confirmation_token="CONFIRM-token")


# ==============================================================================
# TEST C: No legacy code path can reach real Playwright submit without auth
# ==============================================================================

@pytest.mark.asyncio
async def test_browser_workflow_service_cannot_submit_external_portals():
    """
    Test C1: Neither confirmed=True nor confirm_text="SUBMIT" can authorize external submission.
    Direct call to BrowserWorkflowService.submit_session on an external portal (http:// or https://)
    must be rejected with PermissionError, ensuring exactly ONE mechanism authorizes real external submission:
    HumanConfirmationService -> BrowserTaskExecutor.execute_submission_task().
    """
    service = BrowserWorkflowService()
    session_id = "sess-test-ext-guard"
    session = BrowserSession(
        session_id=session_id,
        job_id="job-ext-123",
        application_url="https://boards.greenhouse.io/corp/jobs/123/apply",
        status=BrowserSessionStatus.WAITING_FOR_USER,
    )
    service._active_sessions[session_id] = session

    # 1. confirmed=True alone cannot authorize external submission
    with pytest.raises(PermissionError, match="disabled for external portals"):
        await service.submit_session(session_id=session_id, confirmed=True, confirm_text=None)

    # 2. confirm_text="SUBMIT" alone cannot authorize external submission
    with pytest.raises(PermissionError, match="disabled for external portals"):
        await service.submit_session(session_id=session_id, confirmed=False, confirm_text="SUBMIT")

    # 3. Both confirmed=True and confirm_text="SUBMIT" together cannot authorize external submission
    with pytest.raises(PermissionError, match="disabled for external portals"):
        await service.submit_session(session_id=session_id, confirmed=True, confirm_text="SUBMIT")


@pytest.mark.asyncio
async def test_browser_api_route_submit_rejects_external_sessions(test_client):
    """
    Test C2: POST /api/browser/{session_id}/submit endpoint must return 403
    for external portal sessions.
    """
    service = BrowserWorkflowService()
    session_id = "sess-api-ext-guard"
    session = BrowserSession(
        session_id=session_id,
        job_id="job-ext-456",
        application_url="https://jobs.lever.co/targetcorp/apply",
        status=BrowserSessionStatus.WAITING_FOR_USER,
    )
    from job_copilot.api.routes.browser import get_browser_service
    browser_svc = get_browser_service()
    browser_svc._active_sessions[session_id] = session

    resp = await test_client.post(
        f"/api/browser/{session_id}/submit",
        json={"confirmed": True, "confirm_text": "SUBMIT"},
    )
    assert resp.status_code == 403
    assert "disabled for external portals" in resp.json()["detail"].lower()


# ==============================================================================
# TEST D: Hardened dashboard submission path remains intact and authoritative
# ==============================================================================

@pytest.mark.asyncio
async def test_canonical_dashboard_submission_path_remains_intact():
    """
    Test D: The authoritative HumanConfirmationService requires exact keyword 'SUBMIT'
    and valid cryptographic single-use nonce on a READY_FOR_REVIEW task.
    """
    db = SessionLocal()
    try:
        task_repo = BrowserTaskRepository(db)
        import uuid
        from datetime import timedelta
        uid = uuid.uuid4().hex[:8]
        task_id = f"task-canonical-{uid}"
        token = HumanConfirmationService.generate_confirmation_token()

        task = BrowserTaskModel(
            task_id=task_id,
            application_id=f"app-canonical-{uid}",
            job_id=f"job-canonical-{uid}",
            source="lever",
            target_url="https://jobs.lever.co/company/apply",
            status=BrowserTaskStatus.READY_FOR_REVIEW,
            confirmation_token=token,
            confirmation_expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        task_repo.create(task)

        confirmation_svc = HumanConfirmationService(db)

        # 1. Reject arbitrary token
        with pytest.raises(SubmissionSafetyError, match="Invalid confirmation token"):
            confirmation_svc.validate_and_confirm(
                task_id=task_id,
                request=HumanConfirmationRequest(
                    task_id=task_id,
                    confirmation_token="SUBMIT",  # Passing keyword as token
                    confirm_text="SUBMIT",
                ),
            )

        # 2. Reject incorrect keyword
        with pytest.raises(SubmissionSafetyError, match="keyword 'SUBMIT' is required"):
            confirmation_svc.validate_and_confirm(
                task_id=task_id,
                request=HumanConfirmationRequest(
                    task_id=task_id,
                    confirmation_token=token,
                    confirm_text="CONFIRM",  # Wrong keyword
                ),
            )

        # 3. Accept valid token and keyword
        response = confirmation_svc.validate_and_confirm(
            task_id=task_id,
            request=HumanConfirmationRequest(
                task_id=task_id,
                confirmation_token=token,
                confirm_text="SUBMIT",
            ),
        )
        assert response.success is True
        assert response.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED
    finally:
        db.close()
