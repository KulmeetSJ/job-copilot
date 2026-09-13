"""Integration tests for Phase 11 Dashboard API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.api.app import app
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus, BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.base import Base
from job_copilot.models.application import Application
from job_copilot.models.browser_session import BrowserSessionModel
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job


from sqlalchemy.pool import StaticPool


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

    # Seed data
    session = TestingSessionLocal()
    job = Job(
        job_id="job-api-test-001",
        title="Staff Backend Engineer",
        company="Datadog",
        description="Senior distributed systems engineer with Go, Python, and AWS.",
        lifecycle_status="DISCOVERED",
    )
    session.add(job)
    session.commit()

    app_record = Application(
        application_id="app-api-test-001",
        job_id=job.id,
        job_id_str="job-api-test-001",
        company="Datadog",
        role="Staff Backend Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_record)

    job2 = Job(
        job_id="job-api-test-002",
        title="Frontend Engineer",
        company="Datadog",
        description="React and TypeScript",
        lifecycle_status="DISCOVERED",
    )
    session.add(job2)
    session.commit()

    app_record2 = Application(
        application_id="app-other-unrelated-002",
        job_id=job2.id,
        job_id_str="job-api-test-002",
        company="Datadog",
        role="Frontend Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_record2)
    session.commit()

    # Seed browser task for confirmation test
    task = BrowserTaskModel(
        task_id="task-bw-confirm-001",
        application_id="app-api-test-001",
        job_id="job-api-test-001",
        source="datadog_portal",
        target_url="https://careers.datadog.com/jobs/123",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token="CONFIRM-VALID-TEST-TOKEN-12345",
    )
    session.add(task)
    session.commit()
    session.close()

    yield client, TestingSessionLocal

    app.dependency_overrides.clear()


def test_api_dashboard_overview(client_with_db):
    """Ensure GET /api/dashboard/overview returns aggregated statistics."""
    client, _ = client_with_db
    res = client.get("/api/dashboard/overview")
    assert res.status_code == 200
    data = res.json()
    assert "queue_counts" in data
    assert "pipeline_counts" in data
    assert "recent_activity" in data


def test_api_dashboard_queue(client_with_db):
    """Ensure GET /api/dashboard/queue returns opportunities list."""
    client, _ = client_with_db
    res = client.get("/api/dashboard/queue")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total_count" in data


def test_api_dashboard_job_detail(client_with_db):
    """Ensure GET /api/dashboard/jobs/{id} returns 7-dimensional breakdown."""
    client, _ = client_with_db
    res = client.get("/api/dashboard/jobs/job-api-test-001")
    assert res.status_code == 200
    data = res.json()
    assert data["company"] == "Datadog"
    assert "dimension_scores" in data
    assert "explanation" in data
    assert "facts" in data["explanation"]


def test_api_dashboard_applications_and_detail(client_with_db):
    """Ensure GET /api/dashboard/applications and /applications/{id} work."""
    client, _ = client_with_db
    res = client.get("/api/dashboard/applications")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    detail_res = client.get("/api/dashboard/applications/app-api-test-001")
    assert detail_res.status_code == 200
    data = detail_res.json()
    assert data["company"] == "Datadog"
    assert "timeline" in data
    assert "user_inputs_required" in data


def test_api_dashboard_human_input(client_with_db):
    """Ensure POST /api/dashboard/applications/{id}/input safely records human input."""
    client, _ = client_with_db
    payload = {
        "answers": [
            {
                "question_id": "visa_status",
                "question_text": "Do you require visa sponsorship?",
                "answer_value": "No",
            }
        ]
    }
    res = client.post("/api/dashboard/applications/app-api-test-001/input", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert any("visa_status='No'" in note for note in data["user_notes"])


def test_api_dashboard_confirm_flow(client_with_db, monkeypatch):
    """Ensure POST /api/dashboard/applications/{id}/confirm enforces auth, ownership, token, and exact SUBMIT keyword."""
    client, SessionLocal = client_with_db

    # 1. Invalid keyword fails with 400 Bad Request
    bad_payload = {
        "task_id": "task-bw-confirm-001",
        "confirmation_token": "CONFIRM-VALID-TEST-TOKEN-12345",
        "confirm_text": "APPROVE",  # NOT SUBMIT
    }
    bad_res = client.post("/api/dashboard/applications/app-api-test-001/confirm", json=bad_payload)
    assert bad_res.status_code == 400
    assert "SUBMIT" in bad_res.json()["detail"]

    # 2. Missing or empty task_id fails with 403 Forbidden
    missing_task_payload = {
        "task_id": "",
        "confirmation_token": "CONFIRM-VALID-TEST-TOKEN-12345",
        "confirm_text": "SUBMIT",
    }
    res_no_task = client.post("/api/dashboard/applications/app-api-test-001/confirm", json=missing_task_payload)
    assert res_no_task.status_code == 403

    # 3. Mismatched application_id (task belongs to another application) fails with 403 Forbidden
    mismatched_app_payload = {
        "task_id": "task-bw-confirm-001",
        "confirmation_token": "CONFIRM-VALID-TEST-TOKEN-12345",
        "confirm_text": "SUBMIT",
    }
    res_mismatch = client.post("/api/dashboard/applications/app-other-unrelated-002/confirm", json=mismatched_app_payload)
    assert res_mismatch.status_code == 403
    assert "does not match expected application" in res_mismatch.json()["detail"]

    # 4. Invalid confirmation token fails with 403 Forbidden
    bad_token_payload = {
        "task_id": "task-bw-confirm-001",
        "confirmation_token": "WRONG-TOKEN-ABC",
        "confirm_text": "SUBMIT",
    }
    res_bad_token = client.post("/api/dashboard/applications/app-api-test-001/confirm", json=bad_token_payload)
    assert res_bad_token.status_code == 403
    assert "Invalid confirmation token" in res_bad_token.json()["detail"]

    # 5. Valid SUBMIT keyword and valid token succeeds with 200 OK
    valid_payload = {
        "task_id": "task-bw-confirm-001",
        "confirmation_token": "CONFIRM-VALID-TEST-TOKEN-12345",
        "confirm_text": "SUBMIT",
        "user_notes": "Confirmed by operator test",
    }
    good_res = client.post("/api/dashboard/applications/app-api-test-001/confirm", json=valid_payload)
    assert good_res.status_code == 200
    data = good_res.json()
    assert data["success"] is True
    assert data["status"] == "SUBMISSION_AUTHORIZED"
    assert data["submission_reference"] is not None

    # 6. Duplicate submission returns idempotent prevention message
    dup_res = client.post("/api/dashboard/applications/app-api-test-001/confirm", json=valid_payload)
    assert dup_res.status_code == 200
    assert "Duplicate submission prevented" in dup_res.json()["message"]



def test_api_dashboard_sources_and_sessions(client_with_db):
    """Ensure GET /api/dashboard/sources and /sessions work without secret leakage."""
    client, _ = client_with_db
    sources_res = client.get("/api/dashboard/sources")
    assert sources_res.status_code == 200

    sessions_res = client.get("/api/dashboard/sessions")
    assert sessions_res.status_code == 200
    # Verify no cookies or storage state is present in payload
    assert "cookies" not in str(sessions_res.json()).lower()
    assert "password" not in str(sessions_res.json()).lower()


def test_artifact_download_authentication_enforcement(client_with_db, monkeypatch, tmp_path):
    """Verify GET /api/dashboard/artifacts/{id}/content enforces authentication, returns 401 without auth, and streams binary on success."""
    from pathlib import Path
    from job_copilot.models.artifact import ArtifactModel
    from job_copilot.domain.artifact_enums import ArtifactType, ArtifactStatus
    from job_copilot.storage.local_store import LocalArtifactStore
    from job_copilot.services.artifact_service import ArtifactService

    client, SessionLocal = client_with_db
    db = SessionLocal()

    # Create test artifact in local store and DB
    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")
    service = ArtifactService(db=db, store=store)
    storage_key = "artifacts/job-api-test-001/app-api-test-001/resume.pdf"
    store.put(storage_key, b"%PDF-1.4 Fake PDF Content for Test", content_type="application/pdf")

    from job_copilot.domain.artifact_enums import ArtifactType, ArtifactStatus, StorageProvider
    import hashlib

    raw_pdf = b"%PDF-1.4 Fake PDF Content for Test"
    art_record = ArtifactModel(
        artifact_id="art-test-pdf-001",
        application_id="app-api-test-001",
        job_id="job-api-test-001",
        artifact_type=ArtifactType.TAILORED_RESUME_PDF,
        storage_provider=StorageProvider.LOCAL,
        storage_key=storage_key,
        original_filename="Resume_Datadog.pdf",
        content_type="application/pdf",
        size_bytes=len(raw_pdf),
        sha256=hashlib.sha256(raw_pdf).hexdigest(),
        status=ArtifactStatus.ACTIVE,
    )
    db.add(art_record)
    db.commit()

    # Set mock artifact service on dashboard service dependency if needed, or monkeypatch store
    monkeypatch.setattr("job_copilot.services.dashboard_service.ArtifactService", lambda db: service)

    # 1. Enforce DASHBOARD_API_KEY
    from job_copilot.config import settings
    monkeypatch.setattr(settings, "dashboard_api_key", "secret-test-key-xyz")

    # Without auth header -> 401 Unauthorized
    res_no_auth = client.get("/api/dashboard/artifacts/art-test-pdf-001/content")
    assert res_no_auth.status_code == 401
    assert "Invalid or missing dashboard authentication credentials" in res_no_auth.json()["detail"]

    # With invalid auth header -> 401 Unauthorized
    res_bad_auth = client.get(
        "/api/dashboard/artifacts/art-test-pdf-001/content",
        headers={"X-API-Key": "wrong-key"}
    )
    assert res_bad_auth.status_code == 401

    # With valid auth header -> 200 OK
    res_auth = client.get(
        "/api/dashboard/artifacts/art-test-pdf-001/content",
        headers={"X-API-Key": "secret-test-key-xyz"}
    )
    assert res_auth.status_code == 200
    assert res_auth.content == b"%PDF-1.4 Fake PDF Content for Test"
    assert res_auth.headers["content-type"] == "application/pdf"
    assert 'filename="Resume_Datadog.pdf"' in res_auth.headers["content-disposition"]

    # 2. Non-existent artifact ID -> 404
    res_404 = client.get(
        "/api/dashboard/artifacts/non-existent-artifact-id/content",
        headers={"X-API-Key": "secret-test-key-xyz"}
    )
    assert res_404.status_code == 404


def test_no_secrets_in_compiled_frontend_bundle():
    """Verify that the compiled frontend static bundle never contains API keys or cloud credentials."""
    from pathlib import Path
    static_dir = Path("src/job_copilot/static")
    if not static_dir.exists():
        pytest.skip("Frontend bundle not yet built")

    js_files = list(static_dir.glob("**/*.js"))
    assert len(js_files) > 0, "Expected at least one JS bundle in static assets"

    for js_file in js_files:
        content = js_file.read_text(encoding="utf-8")
        assert "VITE_DASHBOARD_API_KEY" not in content
        assert "S3_SECRET_ACCESS_KEY" not in content
        assert "AWS_SECRET_ACCESS_KEY" not in content
        assert "AKIAIOSFODNN7EXAMPLE" not in content
        assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in content


def test_api_portal_opened_and_continue_and_manual_submit_flow(client_with_db):
    """Ensure POST portal-opened, continue, and mark-submitted work via API."""
    client, SessionLocal = client_with_db
    session = SessionLocal()

    job = Job(
        job_id="job-api-portal-flow-01",
        title="Platform Security Engineer",
        company="Stripe",
        description="Infra security engineer",
        source="greenhouse",
        canonical_url="https://boards.greenhouse.io/stripe/jobs/9988",
    )
    session.add(job)
    session.commit()

    app_record = Application(
        application_id="app-api-portal-flow-01",
        job_id=job.id,
        job_id_str="job-api-portal-flow-01",
        company="Stripe",
        role="Platform Security Engineer",
        canonical_job_url="https://boards.greenhouse.io/stripe/jobs/9988",
        source="greenhouse",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_record)
    session.commit()
    session.close()

    # 1. POST /portal-opened
    res_portal = client.post("/api/dashboard/applications/app-api-portal-flow-01/portal-opened")
    assert res_portal.status_code == 200
    data_portal = res_portal.json()
    assert data_portal["status"] != "SUBMITTED"
    assert any(evt["event_type"] == "PORTAL_OPENED" for evt in data_portal["timeline"])

    # 2. POST /continue (without active session -> LOGIN_REQUIRED)
    res_continue = client.post("/api/dashboard/applications/app-api-portal-flow-01/continue")
    assert res_continue.status_code == 200
    data_continue = res_continue.json()
    assert data_continue["browser_review"]["status"] == "LOGIN_REQUIRED"
    assert data_continue["browser_review"]["pause_reason"] == "Log in to the employer portal first, then connect an authenticated browser session to Job Copilot."
    assert data_continue["blocker_instruction"] == "Log in to the employer portal first, then connect an authenticated browser session to Job Copilot."

    # 3. POST /mark-submitted
    manual_notes = "Finished application manually on Stripe Greenhouse portal #GH-771"
    res_manual = client.post(
        "/api/dashboard/applications/app-api-portal-flow-01/mark-submitted",
        json={"user_notes": manual_notes},
    )
    assert res_manual.status_code == 200
    data_manual = res_manual.json()
    assert data_manual["status"] == "SUBMITTED"
    assert data_manual["submitted_at"] is not None
    assert any(evt["event_type"] == "SUBMITTED" and evt["source"] == "MANUAL_CANDIDATE" for evt in data_manual["timeline"])


def test_api_portal_opened_and_continue_ssrf_protection(client_with_db):
    """Ensure POST portal-opened and continue reject disallowed/SSRF domains with 400 Bad Request."""
    client, SessionLocal = client_with_db
    session = SessionLocal()

    job = Job(
        job_id="job-api-ssrf-01",
        title="Software Engineer",
        company="Internal Corp",
        description="Software engineer",
        source="custom",
        canonical_url="http://169.254.169.254/latest/meta-data",
    )
    session.add(job)
    session.commit()

    app_record = Application(
        application_id="app-api-ssrf-01",
        job_id=job.id,
        job_id_str="job-api-ssrf-01",
        company="Internal Corp",
        role="Software Engineer",
        canonical_job_url="http://169.254.169.254/latest/meta-data",
        source="custom",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_record)
    session.commit()
    session.close()

    # 1. portal-opened on SSRF URL -> 400 Bad Request
    res_portal = client.post("/api/dashboard/applications/app-api-ssrf-01/portal-opened")
    assert res_portal.status_code == 400
    assert "Security Violation" in res_portal.json()["detail"] or "disallowed" in res_portal.json()["detail"].lower()

    # 2. continue on SSRF URL -> 400 Bad Request
    res_continue = client.post("/api/dashboard/applications/app-api-ssrf-01/continue")
    assert res_continue.status_code == 400
    assert "Security Violation" in res_continue.json()["detail"] or "disallowed" in res_continue.json()["detail"].lower()


def test_api_portal_opened_backend_driven_across_requests(client_with_db):
    """Ensure portal opened state is maintained on backend across requests and does not rely on client storage."""
    client, SessionLocal = client_with_db
    session = SessionLocal()

    job = Job(
        job_id="job-api-backend-01",
        title="Backend Infrastructure Engineer",
        company="Stripe",
        description="Infra platform",
        source="greenhouse",
        canonical_url="https://boards.greenhouse.io/stripe/jobs/1100",
    )
    session.add(job)
    session.commit()

    app_record = Application(
        application_id="app-api-backend-01",
        job_id=job.id,
        job_id_str="job-api-backend-01",
        company="Stripe",
        role="Backend Infrastructure Engineer",
        canonical_job_url="https://boards.greenhouse.io/stripe/jobs/1100",
        source="greenhouse",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_record)
    session.commit()
    session.close()

    # Initial GET has no portal opened event
    res1 = client.get("/api/dashboard/applications/app-api-backend-01")
    assert res1.status_code == 200
    assert not any(evt["event_type"] == "PORTAL_OPENED" for evt in res1.json()["timeline"])

    # POST portal opened
    res_post = client.post("/api/dashboard/applications/app-api-backend-01/portal-opened")
    assert res_post.status_code == 200
    assert any(evt["event_type"] == "PORTAL_OPENED" for evt in res_post.json()["timeline"])

    # Subsequent GET (as from a refreshed page or different browser/device) has portal opened event
    res2 = client.get("/api/dashboard/applications/app-api-backend-01")
    assert res2.status_code == 200
    timeline = res2.json()["timeline"]
    portal_evts = [evt for evt in timeline if evt["event_type"] == "PORTAL_OPENED"]
    assert len(portal_evts) == 1
    assert portal_evts[0]["source"] == "USER"


def test_api_continue_with_valid_session_queues_task_and_never_submits(client_with_db):
    """Ensure Continue with active authenticated session queues browser task and never submits automatically."""
    client, SessionLocal = client_with_db
    session = SessionLocal()

    browser_sess = BrowserSessionModel(
        session_id="sess-active-lever-01",
        source="lever",
        status=AuthenticatedSessionStatus.ACTIVE,
    )
    session.add(browser_sess)

    job = Job(
        job_id="job-api-continue-never-sub",
        title="Software Engineer",
        company="Linear",
        description="Linear app engineer",
        source="lever",
        canonical_url="https://jobs.lever.co/linear/4455",
    )
    session.add(job)
    session.commit()

    app_record = Application(
        application_id="app-api-continue-never-sub",
        job_id=job.id,
        job_id_str="job-api-continue-never-sub",
        company="Linear",
        role="Software Engineer",
        canonical_job_url="https://jobs.lever.co/linear/4455",
        source="lever",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_record)
    session.commit()
    session.close()

    res_continue = client.post("/api/dashboard/applications/app-api-continue-never-sub/continue")
    assert res_continue.status_code == 200
    data = res_continue.json()

    # Browser review task is QUEUED
    assert data["browser_review"]["status"] == "QUEUED"

    # Status must NOT be SUBMITTED
    assert data["status"] != "SUBMITTED"
    assert data["submitted_at"] is None
    assert not any(evt["event_type"] == "SUBMITTED" for evt in data["timeline"])



