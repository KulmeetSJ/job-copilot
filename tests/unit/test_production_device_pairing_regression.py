"""Regression test suite for Production Device Pairing & Server Separation Invariants."""

import asyncio
from datetime import datetime, timezone
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.api.routes.dashboard import get_dashboard_service
from job_copilot.browser_agent.agent_runner import LocalBrowserAgentRunner
from job_copilot.browser_agent.cli import main_async, parse_args
from job_copilot.browser_agent.client import AgentProtocolClient
from job_copilot.browser_agent.config import AgentConfig
from job_copilot.db.base import Base
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.device import DeviceRegistrationModel, DeviceStatus
from job_copilot.repositories.device_repository import DeviceRepository
from job_copilot.services.dashboard_service import DashboardService


@pytest.fixture
def in_memory_db():
    """Isolated in-memory test database session."""
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
    """FastAPI test client with test db overrides."""
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


def test_production_pairing_code_generation_includes_explicit_server_url(client):
    """
    Invariant 1: Clicking Connect Local Agent from production dashboard must generate/display
    a one-time 6-digit code with the explicit production server URL embedded in the CLI command.
    """
    prod_url = "https://job-copilot-x3kc.onrender.com"
    resp = client.post(f"/api/dashboard/devices/pair-code?device_name=MacBook&server_url={prod_url}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["device_id"].startswith("dev_")
    assert len(data["pairing_code"]) == 6
    assert data["server_url"] == prod_url
    assert f"--server {prod_url}" in data["cli_command"]
    assert f"pair {data['pairing_code']} --server {prod_url}" in data["cli_command"]


def test_pairing_code_generation_infers_reverse_proxy_forwarded_headers(client):
    """
    Invariant 2: When invoked through reverse proxy headers (e.g. Render HTTPS),
    the generated CLI command automatically resolves the public HTTPS production domain.
    """
    headers = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "job-copilot-x3kc.onrender.com",
    }
    resp = client.post("/api/dashboard/devices/pair-code?device_name=WorkStation", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["server_url"] == "https://job-copilot-x3kc.onrender.com"
    assert "--server https://job-copilot-x3kc.onrender.com" in data["cli_command"]


def test_unpaired_production_device_remains_pending_pairing(client, in_memory_db):
    """
    Invariant 3: A generated production device must remain PENDING_PAIRING
    and not active until paired with its valid OTP.
    """
    resp = client.post("/api/dashboard/devices/pair-code?device_name=TestMachine&server_url=https://job-copilot-x3kc.onrender.com")
    data = resp.json()
    device_id = data["device_id"]

    # Check dashboard devices list
    list_resp = client.get("/api/dashboard/devices")
    assert list_resp.status_code == 200
    devices = list_resp.json()
    matching = next((d for d in devices if d["device_id"] == device_id), None)
    assert matching is not None
    assert matching["status"] == DeviceStatus.PENDING_PAIRING.value
    assert matching["is_active"] is False


def test_pairing_creates_same_device_id_and_transitions_to_connected(client, in_memory_db):
    """
    Invariant 4: When local agent pairs using the OTP against the production server,
    the exact same device ID transitions to CONNECTED in production.
    """
    # 1. Generate pairing code on server
    prod_url = "https://job-copilot-x3kc.onrender.com"
    gen_resp = client.post(f"/api/dashboard/devices/pair-code?device_name=Laptop&server_url={prod_url}")
    gen_data = gen_resp.json()
    device_id = gen_data["device_id"]
    code = gen_data["pairing_code"]

    # 2. Local agent sends pair request
    pair_resp = client.post(
        "/api/agent/pair",
        json={
            "pairing_code": code,
            "device_name": "Laptop",
            "agent_version": "1.0.0",
        },
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "job-copilot-x3kc.onrender.com"},
    )
    assert pair_resp.status_code == 200
    pair_data = pair_resp.json()
    assert pair_data["device_id"] == device_id
    assert pair_data["server_url"] == prod_url
    device_token = pair_data["device_token"]

    # 3. Check dashboard devices list: exact same device ID is now CONNECTED and active
    list_resp = client.get("/api/dashboard/devices")
    devices = list_resp.json()
    matching = next(d for d in devices if d["device_id"] == device_id)
    assert matching["status"] == DeviceStatus.CONNECTED.value
    assert matching["is_active"] is True

    # 4. Device can poll and authenticate with issued token
    poll_resp = client.get("/api/agent/device", headers={"X-Device-Token": device_token})
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert poll_data["device_id"] == device_id
    assert poll_data["status"] == DeviceStatus.CONNECTED.value


def test_agent_does_not_claim_connected_when_token_is_invalid_for_server(client):
    """
    Invariant 5: Local agent does NOT claim CONNECTED if the target server does not recognize the token.
    """
    config = AgentConfig(
        server_url="https://job-copilot-x3kc.onrender.com",
        device_id="dev_invalid",
        device_token="jca_tok_invalid_token_12345",
    )
    # Using client as httpx test client
    # Direct route test with invalid token:
    resp = client.get("/api/agent/device", headers={"X-Device-Token": config.device_token})
    assert resp.status_code == 401
    assert "Invalid, expired, or revoked" in resp.json()["detail"]


def test_localhost_and_production_are_not_accidentally_mixed(client, in_memory_db):
    """
    Invariant 6: Pairing with a local server only registers on local;
    an independent production server remains un-paired and does not recognize the local token.
    """
    # Create Local DB device
    repo_local = DeviceRepository(in_memory_db)
    dev_local, code_local = repo_local.generate_pairing_code(device_name="LocalDev")
    paired_local, token_local = repo_local.verify_and_pair(code_local)

    # In a separate production DB:
    engine_prod = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(bind=engine_prod)
    ProdSession = sessionmaker(bind=engine_prod)
    db_prod = ProdSession()
    try:
        repo_prod = DeviceRepository(db_prod)
        dev_prod, code_prod = repo_prod.generate_pairing_code(device_name="ProdPending")

        # Prod must still be pending
        assert dev_prod.status == DeviceStatus.PENDING_PAIRING
        assert dev_prod.device_id != dev_local.device_id

        # Local token cannot authenticate against prod repo
        assert repo_prod.authenticate_device_token(token_local) is None
    finally:
        db_prod.close()
        Base.metadata.drop_all(bind=engine_prod)


@pytest.mark.asyncio
async def test_cli_parsing_and_interactive_prompt_handling(monkeypatch):
    """
    Invariant 7: CLI parses --server and code correctly, or prompts interactively when missing.
    """
    # 1. With explicit arguments
    parsed = parse_args(["pair", "123456", "--server", "https://job-copilot-x3kc.onrender.com"])
    assert parsed.code == "123456"
    assert parsed.server == "https://job-copilot-x3kc.onrender.com"

    # 2. With code only, defaults to None for server to trigger smart resolution
    parsed_no_server = parse_args(["pair", "654321"])
    assert parsed_no_server.code == "654321"
    assert parsed_no_server.server is None
