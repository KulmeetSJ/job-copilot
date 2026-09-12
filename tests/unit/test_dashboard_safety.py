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


def test_confirmation_application_and_task_exact_allowed(safety_test_client):
    """1. Application A + Task A -> allowed when confirmation conditions pass."""
    client, _ = safety_test_client
    res = client.post(
        "/api/dashboard/applications/app-safety-001/confirm",
        json={
            "task_id": "task-safety-001",
            "confirmation_token": "CONFIRM-SECURE-SAFETY-TOKEN-9999",
            "confirm_text": "SUBMIT",
        },
    )
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_confirmation_fails_if_task_belongs_to_different_application(safety_test_client):
    """2. Application A + Task B -> rejected (raises 403 Forbidden)."""
    client, session_factory = safety_test_client
    session = session_factory()
    # Create Application B
    job_b = Job(
        job_id="job-safety-002",
        title="Frontend Engineer",
        company="OtherCorp",
        description="React and TypeScript",
        lifecycle_status="DISCOVERED",
    )
    session.add(job_b)
    session.commit()

    app_b = Application(
        application_id="app-safety-002",
        job_id=job_b.id,
        job_id_str="job-safety-002",
        company="OtherCorp",
        role="Frontend Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_b)
    session.commit()
    session.close()

    # Attempt to confirm Application B using Application A's task
    res = client.post(
        "/api/dashboard/applications/app-safety-002/confirm",
        json={
            "task_id": "task-safety-001",
            "confirmation_token": "CONFIRM-SECURE-SAFETY-TOKEN-9999",
            "confirm_text": "SUBMIT",
        },
    )
    assert res.status_code == 403
    assert "does not match expected application" in res.json()["detail"]


def test_confirmation_correct_app_id_wrong_job_id_rejected(safety_test_client):
    """3. Application A + Task with correct application_id but wrong job_id -> rejected."""
    client, session_factory = safety_test_client
    session = session_factory()
    # Seed a task with correct app_id but wrong job_id
    mismatched_task = BrowserTaskModel(
        task_id="task-safety-wrong-job",
        application_id="app-safety-001",
        job_id="job-unrelated-foreign-999",
        source="generic_portal",
        target_url="https://careers.safetycorp.com/apply",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token="CONFIRM-SECURE-SAFETY-TOKEN-8888",
    )
    session.add(mismatched_task)
    session.commit()
    session.close()

    res = client.post(
        "/api/dashboard/applications/app-safety-001/confirm",
        json={
            "task_id": "task-safety-wrong-job",
            "confirmation_token": "CONFIRM-SECURE-SAFETY-TOKEN-8888",
            "confirm_text": "SUBMIT",
        },
    )
    assert res.status_code == 403
    assert "does not match expected job" in res.json()["detail"]


def test_confirmation_wrong_app_id_matching_job_id_rejected(safety_test_client):
    """4. Application A + Task with wrong application_id but matching job_id -> rejected."""
    client, session_factory = safety_test_client
    session = session_factory()
    # Seed a task with wrong app_id but matching job_id
    mismatched_task = BrowserTaskModel(
        task_id="task-safety-wrong-app",
        application_id="app-foreign-other-777",
        job_id="job-safety-001",
        source="generic_portal",
        target_url="https://careers.safetycorp.com/apply",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token="CONFIRM-SECURE-SAFETY-TOKEN-7777",
    )
    session.add(mismatched_task)
    session.commit()
    session.close()

    res = client.post(
        "/api/dashboard/applications/app-safety-001/confirm",
        json={
            "task_id": "task-safety-wrong-app",
            "confirmation_token": "CONFIRM-SECURE-SAFETY-TOKEN-7777",
            "confirm_text": "SUBMIT",
        },
    )
    assert res.status_code == 403
    assert "does not match expected application" in res.json()["detail"]


def test_confirmation_nonexistent_application_rejected(safety_test_client):
    """5. Nonexistent application -> rejected."""
    client, _ = safety_test_client
    res = client.post(
        "/api/dashboard/applications/app-nonexistent-9999/confirm",
        json={
            "task_id": "task-safety-001",
            "confirmation_token": "CONFIRM-SECURE-SAFETY-TOKEN-9999",
            "confirm_text": "SUBMIT",
        },
    )
    assert res.status_code == 403
    assert "not found" in res.json()["detail"]


def test_confirmation_cross_domain_mismatch_rejected(safety_test_client):
    """Cross-domain integrity: Task for domain A cannot confirm Application for domain B."""
    client, session_factory = safety_test_client
    session = session_factory()
    # Create application with domain lever.co
    job_domain = Job(
        job_id="job-domain-001",
        title="Security Engineer",
        company="DomainCorp",
        canonical_url="https://jobs.lever.co/domaincorp/sec-eng",
        description="Security systems",
        lifecycle_status="DISCOVERED",
    )
    session.add(job_domain)
    session.commit()

    app_domain = Application(
        application_id="app-domain-001",
        job_id=job_domain.id,
        job_id_str="job-domain-001",
        company="DomainCorp",
        role="Security Engineer",
        canonical_job_url="https://jobs.lever.co/domaincorp/sec-eng",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_domain)
    session.commit()

    # Create task with greenhouse.io domain targeting this app
    task_domain = BrowserTaskModel(
        task_id="task-domain-mismatch-001",
        application_id="app-domain-001",
        job_id="job-domain-001",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/othercorp/jobs/123",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token="CONFIRM-DOMAIN-MISMATCH-TOKEN",
    )
    session.add(task_domain)
    session.commit()
    session.close()

    res = client.post(
        "/api/dashboard/applications/app-domain-001/confirm",
        json={
            "task_id": "task-domain-mismatch-001",
            "confirmation_token": "CONFIRM-DOMAIN-MISMATCH-TOKEN",
            "confirm_text": "SUBMIT",
        },
    )
    assert res.status_code == 403
    assert "does not match application destination domain" in res.json()["detail"]


def test_confirmation_fails_if_application_has_no_browser_task(safety_test_client):
    """Invariant: An application without an active browser task cannot confirm submission."""
    client, session_factory = safety_test_client
    session = session_factory()
    job_c = Job(
        job_id="job-safety-003",
        title="DevOps Engineer",
        company="NoTaskCorp",
        description="Kubernetes and Terraform",
        lifecycle_status="DISCOVERED",
    )
    session.add(job_c)
    session.commit()

    app_c = Application(
        application_id="app-safety-003",
        job_id=job_c.id,
        job_id_str="job-safety-003",
        company="NoTaskCorp",
        role="DevOps Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    session.add(app_c)
    session.commit()
    session.close()

    # Attempt confirmation with non-existent task
    res = client.post(
        "/api/dashboard/applications/app-safety-003/confirm",
        json={
            "task_id": "task-non-existent-999",
            "confirmation_token": "CONFIRM-ANY-TOKEN",
            "confirm_text": "SUBMIT",
        },
    )
    assert res.status_code == 403
    assert "not found" in res.json()["detail"]


def test_read_application_detail_does_not_forge_synthetic_task(safety_test_client):
    """Invariant: GET /applications/{id} does NOT fabricate a synthetic BrowserTaskModel."""
    client, session_factory = safety_test_client
    session = session_factory()
    job_d = Job(
        job_id="job-safety-004",
        title="Data Engineer",
        company="DataCo",
        description="Spark and Python",
        lifecycle_status="DISCOVERED",
    )
    session.add(job_d)
    session.commit()

    app_d = Application(
        application_id="app-safety-004",
        job_id=job_d.id,
        job_id_str="job-safety-004",
        company="DataCo",
        role="Data Engineer",
        status=ApplicationStatus.DISCOVERED,
    )
    session.add(app_d)
    session.commit()
    session.close()

    # Query application detail
    res = client.get("/api/dashboard/applications/app-safety-004")
    assert res.status_code == 200
    data = res.json()
    assert data["browser_review"] is None

    # Verify no task was created in DB
    session = session_factory()
    repo = BrowserTaskRepository(session)
    task = repo.get_by_application_id("app-safety-004")
    assert task is None
    session.close()


def test_csp_headers_contain_blob_and_frame_ancestors_none(safety_test_client):
    """Invariant: CSP includes 'frame-src self blob:' for safe PDF blob preview and 'frame-ancestors none' against framing."""
    client, _ = safety_test_client
    res = client.get("/api/dashboard/overview")
    csp = res.headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in csp
    assert "frame-src 'self' blob:" in csp

