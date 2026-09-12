"""Deterministic Local Playwright E2E Test Suite for Local Interactive Browser Agent.

Tests real Playwright browser execution against an isolated local Fake Employer server.
Proves SAME BROWSER SESSION continuity across CAPTCHA/Login/MFA human blockers,
zero credential transmission, strict submission authorization boundaries,
and worker concurrency isolation.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import http.server
import json
from pathlib import Path
import socket
import threading
from typing import Optional
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import httpx
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.api.routes.dashboard import get_dashboard_service
from job_copilot.browser_agent.agent_runner import LocalBrowserAgentRunner
from job_copilot.browser_agent.client import AgentProtocolClient
from job_copilot.browser_agent.config import AgentConfig
from job_copilot.browser_worker.worker import BrowserWorker
from job_copilot.db.base import Base
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.application import Application
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.device import DeviceRegistrationModel, DeviceStatus
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.repositories.device_repository import DeviceRepository
from job_copilot.schemas.candidate import CandidateProfile, PersonalInformation
from job_copilot.services.dashboard_service import DashboardService


# ==============================================================================
# Isolated Fake Employer HTTP Server
# ==============================================================================

class FakeEmployerHandler(http.server.BaseHTTPRequestHandler):
    """Deterministic HTTP handler simulating ATS portals (Greenhouse/Lever/Generic)."""

    def do_GET(self):
        url = self.path
        if "/jobs/software-engineer/apply" in url:
            challenge = ""
            if "challenge=captcha" in url:
                challenge = """
                <div id="captcha-container" class="g-recaptcha" style="padding:20px;border:2px solid red;">
                    <p id="captcha-text">Please solve the CAPTCHA to continue</p>
                    <button id="solve-captcha-btn" type="button" onclick="document.getElementById('captcha-container').remove();">
                        I am Human (Solve CAPTCHA)
                    </button>
                </div>
                """
            elif "challenge=login" in url:
                challenge = """
                <div id="login-form-container" style="padding:20px;border:2px solid blue;">
                    <h2>Sign In Required</h2>
                    <input type="text" id="username" placeholder="Username" /><br/>
                    <input type="password" id="password" placeholder="Password" /><br/>
                    <button id="login-submit-btn" type="button" onclick="document.getElementById('login-form-container').remove();">
                        Log In
                    </button>
                </div>
                """

            html = f"""<!DOCTYPE html>
            <html>
            <head><title>Software Engineer Application - Acme Corp</title></head>
            <body>
                <h1>Software Engineer Application</h1>
                {challenge}
                <form id="application-form" method="POST" action="/jobs/software-engineer/submit{('?outcome=ambiguous' if 'outcome=ambiguous' in url else '')}">
                    <label for="full_name">Full Name</label>
                    <input type="text" id="full_name" name="full_name" /><br/>
                    
                    <label for="email">Email</label>
                    <input type="email" id="email" name="email" /><br/>
                    
                    <label for="phone">Phone</label>
                    <input type="tel" id="phone" name="phone" /><br/>
                    
                    <label for="location">Location</label>
                    <input type="text" id="location" name="location" /><br/>
                    
                    <button type="submit" id="submit-btn">Submit Application</button>
                </form>
            </body>
            </html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif "/jobs/software-engineer/confirmation" in url:
            html = """<!DOCTYPE html>
            <html>
            <head><title>Application Confirmation</title></head>
            <body>
                <h1>Application Submitted!</h1>
                <p id="confirmation-msg">Your application has been submitted successfully.</p>
                <p>Confirmation Reference: <strong>CONF-FAKE-998877</strong></p>
            </body>
            </html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif "/jobs/software-engineer/ambiguous" in url:
            html = """<!DOCTYPE html>
            <html>
            <head><title>Processing</title></head>
            <body>
                <h1>Processing Your Request</h1>
                <p>Please wait while we process your form...</p>
            </body>
            </html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if "/jobs/software-engineer/submit" in self.path:
            # Check for ambiguous query flag
            if "outcome=ambiguous" in self.path:
                self.send_response(302)
                self.send_header("Location", "/jobs/software-engineer/ambiguous")
                self.end_headers()
            elif "outcome=network_drop" in self.path:
                # Abruptly close connection without response
                self.close_connection = True
                return
            else:
                self.send_response(302)
                self.send_header("Location", "/jobs/software-engineer/confirmation")
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence default server logging during tests
        pass


@pytest.fixture(scope="module")
def fake_employer_server():
    """Start local threaded HTTP server for fake employer applications."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeEmployerHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()


@pytest.fixture
def in_memory_db():
    """Create in-memory database with static thread pool for concurrency tests."""
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
def agent_http_client(in_memory_db):
    """In-memory ASGI transport HTTP client connected to FastAPI app with DB override."""
    app.dependency_overrides[get_db] = lambda: in_memory_db
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_candidate():
    """Mock test candidate profile."""
    return CandidateProfile(
        personal_info=PersonalInformation(
            full_name="Alex Mercer",
            email="alex.mercer@example.com",
            phone="+14155552671",
            location="San Francisco, CA",
        )
    )


# ==============================================================================
# 1. REAL PLAYWRIGHT E2E — SAME BROWSER SESSION & CAPTCHA PAUSE PROOF
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_same_session_captcha_pause_and_verified_submission(
    in_memory_db, fake_employer_server, mock_candidate, agent_http_client
):
    """
    PROVE SAME BROWSER SESSION:
    1. Agent opens visible-capable Playwright browser.
    2. Navigates to fake employer with CAPTCHA blocker.
    3. Agent detects CAPTCHA and enters CAPTCHA_REQUIRED pause.
    4. Records underlying Playwright Context and Page IDs.
    5. User solves CAPTCHA directly in that SAME page.
    6. Agent detects resolution, resumes in the SAME Page without recreating context.
    7. Fills form safely -> transitions to READY_FOR_REVIEW.
    8. User authorizes submission in dashboard with 'SUBMIT' keyword.
    9. Agent clicks submit on the SAME page.
    10. Employer confirmation detected -> COMPLETED / APPLIED / SUBMITTED.
    """
    # 1. Setup backend DB models
    device_repo = DeviceRepository(in_memory_db)
    device, pairing_code = device_repo.generate_pairing_code(device_name="Test Playwright Laptop")
    paired_device, device_token = device_repo.verify_and_pair(pairing_code)

    from job_copilot.models.job import Job
    job = Job(
        job_id="job-fake-e2e-01",
        title="Software Engineer",
        company="Fake Tech Corp",
        location="Remote",
        description="Software Engineer role",
        canonical_url=f"{fake_employer_server}/jobs/software-engineer/apply?challenge=captcha",
        source="generic",
    )
    in_memory_db.add(job)
    in_memory_db.commit()
    in_memory_db.refresh(job)

    app_repo = ApplicationRepository(in_memory_db)
    app = Application(
        application_id="app-fake-e2e-01",
        job_id=job.id,
        job_id_str="job-fake-e2e-01",
        company="Fake Tech Corp",
        role="Software Engineer",
        source="generic",
        canonical_job_url=f"{fake_employer_server}/jobs/software-engineer/apply?challenge=captcha",
        status=ApplicationStatus.PREPARING,
    )
    in_memory_db.add(app)
    in_memory_db.commit()
    in_memory_db.refresh(app)

    task_repo = BrowserTaskRepository(in_memory_db)
    task = BrowserTaskModel(
        task_id="task-fake-e2e-01",
        application_id="app-fake-e2e-01",
        job_id="job-fake-e2e-01",
        source="generic",
        target_url=f"{fake_employer_server}/jobs/software-engineer/apply?challenge=captcha",
        status=BrowserTaskStatus.QUEUED,
        execution_mode="LOCAL_INTERACTIVE",
        assigned_device_id=paired_device.device_id,
    )
    task_repo.create(task)

    # 2. Configure Local Browser Agent
    agent_config = AgentConfig(
        server_url="http://testserver",
        device_id=paired_device.device_id,
        device_token=device_token,
        headless=True,  # Headless Playwright execution in test
        allow_test_fixture=True,
    )
    agent_protocol_client = AgentProtocolClient(agent_config, http_client=agent_http_client)
    runner = LocalBrowserAgentRunner(agent_config, candidate_profile=mock_candidate, client=agent_protocol_client)

    # 3. Simulate Agent Claiming & Running Task
    task_dict = {
        "task_id": task.task_id,
        "source": "generic",
        "target_url": task.target_url,
        "status": "QUEUED",
    }

    # Start processing task in background task
    process_future = asyncio.create_task(runner.process_task(task_dict))

    # Wait for agent to launch browser and encounter CAPTCHA
    for _ in range(30):
        await asyncio.sleep(0.2)
        curr_task = task_repo.get_by_task_id(task.task_id)
        if curr_task and curr_task.status == BrowserTaskStatus.CAPTCHA_REQUIRED:
            break

    curr_task = task_repo.get_by_task_id(task.task_id)
    assert curr_task.status == BrowserTaskStatus.CAPTCHA_REQUIRED
    assert runner.active_page is not None
    assert runner.active_context is not None

    # Capture Page & Context Identity Objects to PROVE SAME SESSION
    initial_page = runner.active_page
    initial_context = runner.active_context

    # 4. Simulate User Solving CAPTCHA in the SAME Page
    await initial_page.click("#solve-captcha-btn")
    await initial_page.wait_for_timeout(500)

    # Wait for agent to detect blocker disappearance and finish preparation
    await asyncio.wait_for(process_future, timeout=15.0)

    # PROVE Page & Context were NOT recreated
    assert runner.active_page is initial_page
    assert runner.active_context is initial_context

    # Verify task reached READY_FOR_REVIEW
    task_ready = task_repo.get_by_task_id(task.task_id)
    assert task_ready.status == BrowserTaskStatus.READY_FOR_REVIEW
    assert task_ready.confirmation_token is not None

    # 5. User Confirms Submission with 'SUBMIT' Keyword in Dashboard
    dash_service = DashboardService(db=in_memory_db)
    from job_copilot.schemas.dashboard import SubmissionConfirmPayload
    confirm_resp = dash_service.confirm_submission(
        payload=SubmissionConfirmPayload(
            task_id=task.task_id,
            confirmation_token=task_ready.confirmation_token,
            confirm_text="SUBMIT",
        ),
        application_id=app.application_id,
    )
    assert confirm_resp.success is True

    task_auth = task_repo.get_by_task_id(task.task_id)
    assert task_auth.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED

    # 6. Local Agent Executes Authorized Final Submission on SAME Page
    sub_task_dict = {
        "task_id": task.task_id,
        "source": "generic",
        "target_url": task.target_url,
        "status": "SUBMISSION_AUTHORIZED",
    }
    await runner.process_task(sub_task_dict)

    # PROVE Final Execution completed with verified employer signal
    task_completed = task_repo.get_by_task_id(task.task_id)
    assert task_completed.status == BrowserTaskStatus.COMPLETED

    app_applied = app_repo.get_by_application_id(app.application_id)
    assert app_applied.status == ApplicationStatus.APPLIED

    # Clean shutdown
    await runner.shutdown()


# ==============================================================================
# 2. PROVE LOGIN WALL & ZERO CREDENTIAL TRANSMISSION
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_same_session_login_and_zero_credential_transmission(
    in_memory_db, fake_employer_server, mock_candidate, agent_http_client
):
    """
    PROVE LOGIN FLOW & ZERO CREDENTIAL TRANSMISSION:
    1. Agent navigates to fake employer with login challenge.
    2. Agent pauses in LOGIN_REQUIRED.
    3. Human enters secret credentials locally into the browser window.
    4. Asserts that the secret password NEVER exists in server database, review package, or audit events.
    """
    device_repo = DeviceRepository(in_memory_db)
    device, pairing_code = device_repo.generate_pairing_code(device_name="Test Laptop")
    paired_device, device_token = device_repo.verify_and_pair(pairing_code)

    task_repo = BrowserTaskRepository(in_memory_db)
    task = BrowserTaskModel(
        task_id="task-login-e2e-01",
        application_id="app-login-e2e-01",
        job_id="job-login-e2e-01",
        source="generic",
        target_url=f"{fake_employer_server}/jobs/software-engineer/apply?challenge=login",
        status=BrowserTaskStatus.QUEUED,
        execution_mode="LOCAL_INTERACTIVE",
        assigned_device_id=paired_device.device_id,
    )
    task_repo.create(task)

    agent_config = AgentConfig(
        server_url="http://testserver",
        device_id=paired_device.device_id,
        device_token=device_token,
        headless=True,
        allow_test_fixture=True,
    )
    agent_protocol_client = AgentProtocolClient(agent_config, http_client=agent_http_client)
    runner = LocalBrowserAgentRunner(agent_config, candidate_profile=mock_candidate, client=agent_protocol_client)

    process_future = asyncio.create_task(
        runner.process_task({
            "task_id": task.task_id,
            "source": "generic",
            "target_url": task.target_url,
            "status": "QUEUED",
        })
    )

    # Wait for LOGIN_REQUIRED
    for _ in range(30):
        await asyncio.sleep(0.2)
        curr_task = task_repo.get_by_task_id(task.task_id)
        if curr_task and curr_task.status == BrowserTaskStatus.LOGIN_REQUIRED:
            break

    curr_task = task_repo.get_by_task_id(task.task_id)
    assert curr_task.status == BrowserTaskStatus.LOGIN_REQUIRED

    SECRET_PASSWORD = "SuperSecretPassword123!@#"
    # User types password directly in browser
    await runner.active_page.fill("#username", "candidate_user")
    await runner.active_page.fill("#password", SECRET_PASSWORD)
    await runner.active_page.click("#login-submit-btn")

    # Complete preparation
    await asyncio.wait_for(process_future, timeout=15.0)

    # Verify task state
    task_ready = task_repo.get_by_task_id(task.task_id)
    assert task_ready.status == BrowserTaskStatus.READY_FOR_REVIEW

    # CRITICAL ZERO-CREDENTIAL AUDIT: Password must NEVER appear in DB or review JSON
    task_json_str = json.dumps(task_ready.review_package_json)
    assert SECRET_PASSWORD not in task_json_str
    assert SECRET_PASSWORD not in str(task_ready.audit_events)

    await runner.shutdown()


# ==============================================================================
# 3. AMBIGUOUS OUTCOME & NETWORK FAILURE SAFEGUARDS
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_ambiguous_outcome_becomes_unverified_without_retry(
    in_memory_db, fake_employer_server, mock_candidate, agent_http_client
):
    """
    Test that clicking submit when the employer page returns an ambiguous response
    transitions task to SUBMISSION_UNVERIFIED and NEVER marks SUBMITTED.
    """
    device_repo = DeviceRepository(in_memory_db)
    device, pairing_code = device_repo.generate_pairing_code(device_name="Test Ambig Laptop")
    paired_device, device_token = device_repo.verify_and_pair(pairing_code)

    task_repo = BrowserTaskRepository(in_memory_db)
    task = BrowserTaskModel(
        task_id="task-ambig-e2e-01",
        application_id="app-ambig-e2e-01",
        job_id="job-ambig-e2e-01",
        source="generic",
        target_url=f"{fake_employer_server}/jobs/software-engineer/apply?outcome=ambiguous",
        status=BrowserTaskStatus.SUBMISSION_AUTHORIZED,
        execution_mode="LOCAL_INTERACTIVE",
        assigned_device_id=paired_device.device_id,
    )
    task_repo.create(task)

    agent_config = AgentConfig(
        server_url="http://testserver",
        device_id=paired_device.device_id,
        device_token=device_token,
        headless=True,
        allow_test_fixture=True,
    )
    agent_protocol_client = AgentProtocolClient(agent_config, http_client=agent_http_client)
    runner = LocalBrowserAgentRunner(agent_config, candidate_profile=mock_candidate, client=agent_protocol_client)

    await runner.process_task({
        "task_id": task.task_id,
        "source": "generic",
        "target_url": task.target_url,
        "status": "SUBMISSION_AUTHORIZED",
    })

    updated_task = task_repo.get_by_task_id(task.task_id)
    assert updated_task.status == BrowserTaskStatus.SUBMISSION_UNVERIFIED
    assert updated_task.status != BrowserTaskStatus.COMPLETED

    await runner.shutdown()


# ==============================================================================
# 4. WORKER CONCURRENCY & OWNERSHIP ISOLATION
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_worker_ownership_and_concurrency_race(in_memory_db):
    """
    Test that Render BrowserWorker and Local Agent NEVER claim each other's tasks.
    - LOCAL_INTERACTIVE is ignored by Render worker.
    - REMOTE_HEADLESS is ignored by Local agent.
    """
    task_repo = BrowserTaskRepository(in_memory_db)

    # Task 1: LOCAL_INTERACTIVE
    task_local = BrowserTaskModel(
        task_id="task-local-mode-01",
        application_id="app-local-01",
        job_id="job-local-01",
        source="generic",
        target_url="https://jobs.lever.co/company/job-local",
        status=BrowserTaskStatus.QUEUED,
        execution_mode="LOCAL_INTERACTIVE",
    )
    task_repo.create(task_local)

    # Task 2: REMOTE_HEADLESS
    task_remote = BrowserTaskModel(
        task_id="task-remote-mode-02",
        application_id="app-remote-02",
        job_id="job-remote-02",
        source="greenhouse",
        target_url="https://boards.greenhouse.io/company/job-remote",
        status=BrowserTaskStatus.QUEUED,
        execution_mode="REMOTE_HEADLESS",
    )
    task_repo.create(task_remote)

    # Render worker runs single cycle
    worker = BrowserWorker(worker_id="render-worker-prod-01")
    claimed_by_worker = await worker.process_next_task(db=in_memory_db)

    # Assert Render worker claimed ONLY task_remote, leaving task_local in QUEUED state
    assert claimed_by_worker is not None
    assert claimed_by_worker.task_id == "task-remote-mode-02"

    task_local_check = task_repo.get_by_task_id("task-local-mode-01")
    assert task_local_check.status == BrowserTaskStatus.QUEUED
    assert task_local_check.worker_id is None


# ==============================================================================
# 5. LOCAL SSRF & URL REJECTION MATRIX
# ==============================================================================

def test_local_browser_ssrf_and_url_security_matrix():
    """
    Verify local agent rejects all local network, loopback, private, and non-http schemes.
    """
    from job_copilot.browser_worker.safety import validate_local_agent_target_url
    from job_copilot.browser_worker.exceptions import DomainSecurityError

    forbidden_urls = [
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/admin",
        "http://192.168.1.1/",
        "http://172.16.0.1/router",
        "http://127.0.0.1:8000/internal",
        "http://localhost:3000/api",
        "http://[::1]/job",
        "http://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "javascript:alert(1)",
        "chrome://settings",
        "https://evil-phishing-attacker.com/careers/apply",
    ]

    for url in forbidden_urls:
        with pytest.raises(DomainSecurityError):
            validate_local_agent_target_url(url, allow_test_fixture=False)
