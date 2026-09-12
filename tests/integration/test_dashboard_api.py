"""Integration tests for Phase 11 Dashboard API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.api.app import app
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.base import Base
from job_copilot.models.application import Application
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


def test_api_dashboard_confirm_flow(client_with_db):
    """Ensure POST /api/dashboard/applications/{id}/confirm enforces exact SUBMIT keyword."""
    client, _ = client_with_db

    # 1. Invalid keyword fails
    bad_payload = {
        "task_id": "task-bw-confirm-001",
        "confirmation_token": "CONFIRM-VALID-TEST-TOKEN-12345",
        "confirm_text": "APPROVE",  # NOT SUBMIT
    }
    bad_res = client.post("/api/dashboard/applications/app-api-test-001/confirm", json=bad_payload)
    assert bad_res.status_code in (400, 403)

    # 2. Valid SUBMIT keyword succeeds
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
    assert data["status"] == "COMPLETED"


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
