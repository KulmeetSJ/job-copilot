"""Unit tests for Local Interactive Browser Agent Protocol, Device Pairing, and Security Boundaries."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.browser_agent.client import AgentProtocolClient
from job_copilot.browser_agent.config import (
    AgentConfig,
    clear_agent_config,
    load_agent_config,
    save_agent_config,
)
from job_copilot.db.base import Base
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.device import DeviceRegistrationModel, DeviceStatus
from job_copilot.models.job import Job
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.repositories.device_repository import DeviceRepository
from job_copilot.services.dashboard_service import DashboardService


from sqlalchemy.pool import StaticPool
from job_copilot.api.routes.dashboard import get_dashboard_service


@pytest.fixture
def in_memory_db():
    """Create in-memory SQLite database for test isolation."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(in_memory_db):
    """FastAPI TestClient with overridden database session and dashboard service."""
    def override_get_db():
        try:
            yield in_memory_db
        finally:
            pass

    def override_get_dashboard_service():
        return DashboardService(db=in_memory_db)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_dashboard_service] = override_get_dashboard_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()



def test_device_pairing_lifecycle(in_memory_db):
    """Test full pairing lifecycle: generate code, verify, issue token, authenticate."""
    repo = DeviceRepository(in_memory_db)

    # 1. Generate pairing code
    device, code = repo.generate_pairing_code(device_name="MacBook Pro", validity_minutes=10)
    assert device.device_id.startswith("dev_")
    assert len(code) == 6
    assert device.status == DeviceStatus.PENDING_PAIRING

    # 2. Verify and pair with correct code
    paired_device, raw_token = repo.verify_and_pair(pairing_code=code, device_name="MacBook Pro")
    assert paired_device.device_id == device.device_id
    assert paired_device.status == DeviceStatus.CONNECTED
    assert paired_device.pairing_code is None  # Code consumed
    assert raw_token.startswith("jca_tok_")

    # 3. Authenticate with valid token
    auth_device = repo.authenticate_device_token(raw_token)
    assert auth_device is not None
    assert auth_device.device_id == device.device_id

    # 4. Attempt reuse of consumed code -> fails
    with pytest.raises(ValueError, match="Invalid or expired pairing code"):
        repo.verify_and_pair(pairing_code=code)


def test_expired_pairing_code_rejection(in_memory_db):
    """Test that expired pairing codes are rejected."""
    repo = DeviceRepository(in_memory_db)
    device, code = repo.generate_pairing_code(device_name="Test Device", validity_minutes=-5)

    with pytest.raises(ValueError, match="Invalid or expired pairing code"):
        repo.verify_and_pair(pairing_code=code)


def test_revoked_device_rejection(in_memory_db):
    """Test that revoking a device immediately invalidates its token."""
    repo = DeviceRepository(in_memory_db)
    device, code = repo.generate_pairing_code(device_name="Test Device")
    paired_device, raw_token = repo.verify_and_pair(code)

    # Verify authenticated
    assert repo.authenticate_device_token(raw_token) is not None

    # Revoke device
    revoked = repo.revoke_device(paired_device.device_id)
    assert revoked is True

    # Token must now be rejected
    assert repo.authenticate_device_token(raw_token) is None


def test_agent_protocol_api_endpoints(client, in_memory_db):
    """Test REST API protocol routes between local agent and backend."""
    # 1. Dashboard generates pairing code
    gen_resp = client.post("/api/dashboard/devices/pair-code?device_name=TestMachine")
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    pairing_code = gen_data["pairing_code"]
    device_id = gen_data["device_id"]
    assert len(pairing_code) == 6

    # 2. Local agent pairs via POST /api/agent/pair
    pair_resp = client.post(
        "/api/agent/pair",
        json={
            "pairing_code": pairing_code,
            "device_name": "TestMachine",
            "agent_version": "1.0.0",
            "capabilities": ["playwright_chromium", "visible_browser"],
        },
    )
    assert pair_resp.status_code == 200
    pair_data = pair_resp.json()
    assert pair_data["success"] is True
    device_token = pair_data["device_token"]
    assert device_token.startswith("jca_tok_")

    # 3. Local agent checks device status via GET /api/agent/device
    status_resp = client.get("/api/agent/device", headers={"X-Device-Token": device_token})
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "CONNECTED"

    # 4. Unauthorized request without valid token -> 401
    unauth_resp = client.get("/api/agent/device", headers={"X-Device-Token": "invalid_token"})
    assert unauth_resp.status_code == 401

    # 5. Create a browser task in database
    task_repo = BrowserTaskRepository(in_memory_db)
    task = BrowserTaskModel(
        task_id="task-test-local-01",
        application_id="app-test-01",
        job_id="job-test-01",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/example/jobs/123",
        status=BrowserTaskStatus.QUEUED,
        execution_mode="LOCAL_INTERACTIVE",
    )
    task_repo.create(task)

    # 6. Local agent polls for task via GET /api/agent/tasks/poll
    poll_resp = client.get("/api/agent/tasks/poll", headers={"X-Device-Token": device_token})
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert poll_data["has_task"] is True
    assert poll_data["task"]["task_id"] == "task-test-local-01"

    # 7. Local agent reports CAPTCHA blocker via POST /api/agent/tasks/{id}/heartbeat
    blocker_resp = client.post(
        "/api/agent/tasks/task-test-local-01/heartbeat",
        headers={"X-Device-Token": device_token},
        json={
            "task_id": "task-test-local-01",
            "status": "CAPTCHA_REQUIRED",
            "pause_reason": "CAPTCHA detected in visible browser",
        },
    )
    assert blocker_resp.status_code == 200
    assert blocker_resp.json()["status"] == "CAPTCHA_REQUIRED"

    # 8. Local agent uploads review package via POST /api/agent/tasks/{id}/package
    pkg_resp = client.post(
        "/api/agent/tasks/task-test-local-01/package",
        headers={"X-Device-Token": device_token},
        json={
            "task_id": "task-test-local-01",
            "fields_detected_count": 5,
            "fields_filled_count": 4,
            "fields_requiring_input_count": 1,
            "review_package_json": {"detected_fields": ["Name", "Email", "Phone", "Resume", "Notice"]},
        },
    )
    assert pkg_resp.status_code == 200
    assert pkg_resp.json()["status"] == "READY_FOR_REVIEW"

    # 9. Local agent reports verified completion via POST /api/agent/tasks/{id}/complete
    complete_resp = client.post(
        "/api/agent/tasks/task-test-local-01/complete",
        headers={"X-Device-Token": device_token},
        json={
            "task_id": "task-test-local-01",
            "employer_confirmation_signal": "Thank you for applying! Confirmation #GH-98765",
            "submission_reference": "GH-98765",
            "evidence_notes": "Verified on confirmation page",
        },
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "COMPLETED"


def test_agent_config_security_permissions():
    """Test that local agent config is stored securely with 0600 permissions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "agent_config.json"
        config = AgentConfig(
            server_url="https://job-copilot.example.com",
            device_id="dev_123456",
            device_token="jca_tok_secrettokenvalue",
            device_name="Secure Laptop",
        )
        saved = save_agent_config(config, config_path=config_path)
        assert saved.exists()

        # Check permissions (0600 on POSIX)
        mode = oct(saved.stat().st_mode)[-3:]
        assert mode == "600"

        # Load back
        loaded = load_agent_config(config_path=config_path)
        assert loaded.device_id == "dev_123456"
        assert loaded.device_token == "jca_tok_secrettokenvalue"

        # Clear config
        clear_agent_config(config_path=config_path)
        assert not config_path.exists()


def test_cross_domain_task_rejection(client, in_memory_db):
    """Test that tasks with spoofed or untrusted domains are rejected by security validators."""
    from job_copilot.browser_worker.safety import validate_target_domain
    from job_copilot.browser_worker.exceptions import DomainSecurityError

    from job_copilot.browser_worker.adapters import SourceAdapterRegistry

    # 1. Allowed domain validation
    validated_url = validate_target_domain("https://boards.greenhouse.io/company/jobs/123", ["boards.greenhouse.io", "greenhouse.io"])
    assert validated_url == "https://boards.greenhouse.io/company/jobs/123"

    # 2. Source adapter validation
    registry = SourceAdapterRegistry()
    adapter = registry.get_adapter(source="greenhouse", target_url="https://boards.greenhouse.io/company/jobs/123")
    assert adapter is not None

    # 3. Cross-domain / spoofed domain rejected
    with pytest.raises(DomainSecurityError, match="No registered source adapter supports URL"):
        registry.get_adapter(source="greenhouse", target_url="https://attacker-phishing.com/greenhouse/apply")

    with pytest.raises(DomainSecurityError, match="No registered source adapter supports URL"):
        registry.get_adapter(source="lever", target_url="https://malicious-site.org/lever/job")


def test_unauthorized_task_update_rejection(client, in_memory_db):
    """Test that unauthorized agents cannot mutate browser tasks."""
    task_repo = BrowserTaskRepository(in_memory_db)
    task = BrowserTaskModel(
        task_id="task-secure-99",
        application_id="app-sec-99",
        job_id="job-sec-99",
        source="lever",
        target_url="https://jobs.lever.co/example/123",
        status=BrowserTaskStatus.QUEUED,
        execution_mode="LOCAL_INTERACTIVE",
    )
    task_repo.create(task)

    # Attempt heartbeat without valid token -> 401
    resp = client.post(
        "/api/agent/tasks/task-secure-99/heartbeat",
        headers={"X-Device-Token": "bad_token_123"},
        json={"task_id": "task-secure-99", "status": "RUNNING"},
    )
    assert resp.status_code == 401

    # Attempt complete without valid token -> 401
    resp2 = client.post(
        "/api/agent/tasks/task-secure-99/complete",
        headers={"X-Device-Token": "bad_token_123"},
        json={"task_id": "task-secure-99", "employer_confirmation_signal": "Fake Confirmed"},
    )
    assert resp2.status_code == 401

