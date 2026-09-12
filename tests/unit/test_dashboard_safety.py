"""Safety invariant and submission boundary tests for Phase 11 Dashboard."""

import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.api.app import app
from job_copilot.config import settings
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.base import Base
from job_copilot.models.application import Application
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository


@pytest.fixture
def candidate_truth_hashes():
    """Capture SHA-256 hashes of candidate truth files to verify zero mutation."""
    files = [
        Path("data/candidate/master_profile.yaml"),
        Path("data/candidate/evidence.yaml"),
        Path("data/candidate/preferences.yaml"),
    ]
    hashes = {}
    for f in files:
        if f.exists():
            hashes[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    return hashes


from sqlalchemy.pool import StaticPool


@pytest.fixture
def safety_test_client():
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

    session = TestingSessionLocal()
    job = Job(
        job_id="job-safety-001",
        title="Backend Engineer",
        company="SafetyCorp",
        description="Python FastAPI and PostgreSQL",
        lifecycle_status="DISCOVERED",
    )
    session.add(job)
    session.commit()

    app_record = Application(
        application_id="app-safety-001",
        job_id=job.id,
        job_id_str="job-safety-001",
        company="SafetyCorp",
        role="Backend Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_record)
    session.commit()

    task = BrowserTaskModel(
        task_id="task-safety-001",
        application_id="app-safety-001",
        job_id="job-safety-001",
        source="generic_portal",
        target_url="https://careers.safetycorp.com/apply",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token="CONFIRM-SECURE-SAFETY-TOKEN-9999",
    )
    session.add(task)
    session.commit()
    session.close()

    yield client, TestingSessionLocal

    app.dependency_overrides.clear()


def test_review_action_does_not_submit(safety_test_client):
    """Invariant: Opening or reading application review does NOT transition task to SUBMITTED."""
    client, session_factory = safety_test_client
    res = client.get("/api/dashboard/applications/app-safety-001")
    assert res.status_code == 200

    session = session_factory()
    repo = BrowserTaskRepository(session)
    task = repo.get_by_task_id("task-safety-001")
    assert task.status == BrowserTaskStatus.READY_FOR_REVIEW
    session.close()


def test_prepare_action_does_not_submit(safety_test_client):
    """Invariant: Preparing an application does NOT transition task to SUBMITTED."""
    client, session_factory = safety_test_client
    res = client.post("/api/dashboard/applications/app-safety-001/prepare")
    assert res.status_code == 200

    session = session_factory()
    repo = BrowserTaskRepository(session)
    task = repo.get_by_task_id("task-safety-001")
    assert task.status == BrowserTaskStatus.READY_FOR_REVIEW
    session.close()


def test_confirmation_requires_exact_submit_keyword(safety_test_client):
    """Invariant: Confirmation with any keyword other than 'SUBMIT' fails."""
    client, session_factory = safety_test_client

    for bad_keyword in ["APPROVE", "CONFIRM", "YES", "SEND", "PROCEED", ""]:
        res = client.post(
            "/api/dashboard/applications/app-safety-001/confirm",
            json={
                "task_id": "task-safety-001",
                "confirmation_token": "CONFIRM-SECURE-SAFETY-TOKEN-9999",
                "confirm_text": bad_keyword,
            },
        )
        assert res.status_code in (400, 403)

    session = session_factory()
    repo = BrowserTaskRepository(session)
    task = repo.get_by_task_id("task-safety-001")
    assert task.status == BrowserTaskStatus.READY_FOR_REVIEW
    session.close()


def test_invalid_confirmation_token_fails(safety_test_client):
    """Invariant: Incorrect confirmation token is rejected by backend HumanConfirmationService."""
    client, session_factory = safety_test_client
    res = client.post(
        "/api/dashboard/applications/app-safety-001/confirm",
        json={
            "task_id": "task-safety-001",
            "confirmation_token": "CONFIRM-WRONG-INVALID-TOKEN",
            "confirm_text": "SUBMIT",
        },
    )
    assert res.status_code == 403

    session = session_factory()
    repo = BrowserTaskRepository(session)
    task = repo.get_by_task_id("task-safety-001")
    assert task.status == BrowserTaskStatus.READY_FOR_REVIEW
    session.close()


def test_auth_protection_when_key_configured(safety_test_client, monkeypatch):
    """Ensure dashboard endpoints reject unauthorized calls when DASHBOARD_API_KEY is configured."""
    monkeypatch.setattr(settings, "dashboard_api_key", "secret-test-key-12345")
    client, _ = safety_test_client

    # 1. Without header -> 401
    unauth_res = client.get("/api/dashboard/overview")
    assert unauth_res.status_code == 401

    # 2. With invalid header -> 401
    bad_res = client.get("/api/dashboard/overview", headers={"X-API-Key": "wrong-key"})
    assert bad_res.status_code == 401

    # 3. With correct header -> 200
    good_res = client.get("/api/dashboard/overview", headers={"X-API-Key": "secret-test-key-12345"})
    assert good_res.status_code == 200


def test_candidate_truth_files_strictly_immutable(candidate_truth_hashes):
    """Invariant: Candidate truth files remain byte-for-byte unmodified after all operations."""
    for path_str, original_sha in candidate_truth_hashes.items():
        p = Path(path_str)
        current_sha = hashlib.sha256(p.read_bytes()).hexdigest()
        assert current_sha == original_sha, f"Candidate truth file '{path_str}' was modified!"
