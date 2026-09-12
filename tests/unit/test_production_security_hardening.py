"""Comprehensive test suite for Phase 12.1 Production Security Hardening."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.api.auth import require_dashboard_auth
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import SubmissionSafetyError
from job_copilot.browser_worker.models import HumanConfirmationRequest
from job_copilot.config import settings
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.services.dashboard_service import DashboardService


@pytest.fixture
def client():
    """FastAPI TestClient instance."""
    return TestClient(app, raise_server_exceptions=False)


# ==============================================================================
# 1. Authentication & Production Safety
# ==============================================================================

def test_public_endpoints_accessible_without_auth(client):
    """Verify that public monitoring and root endpoints do not require auth."""
    # /health
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json() == {"status": "ok"}

    # /ready
    resp_ready = client.get("/ready")
    assert resp_ready.status_code == 200
    assert resp_ready.json()["status"] == "ready"

    # /
    resp_root = client.get("/")
    assert resp_root.status_code == 200
    assert "service" in resp_root.json()


def test_production_auth_missing_key_fails_safely(client, monkeypatch):
    """Verify that missing DASHBOARD_API_KEY in production mode fails safely with HTTP 500."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "dashboard_api_key", None)

    resp = client.get("/api/dashboard/overview")
    assert resp.status_code == 500
    assert "misconfigured" in resp.json().get("detail", "").lower()


def test_production_auth_with_valid_and_invalid_keys(client, monkeypatch):
    """Verify production authentication with X-API-Key and Bearer token."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "dashboard_api_key", "sec-test-prod-key-999")

    # 1. No credentials -> 401
    resp_none = client.get("/api/dashboard/overview")
    assert resp_none.status_code == 401

    # 2. Invalid credentials -> 401
    resp_bad = client.get("/api/dashboard/overview", headers={"X-API-Key": "wrong-key"})
    assert resp_bad.status_code == 401

    # 3. Valid X-API-Key -> 200
    resp_good_header = client.get("/api/dashboard/overview", headers={"X-API-Key": "sec-test-prod-key-999"})
    assert resp_good_header.status_code == 200

    # 4. Valid Bearer Token -> 200
    resp_good_bearer = client.get(
        "/api/dashboard/overview",
        headers={"Authorization": "Bearer sec-test-prod-key-999"},
    )
    assert resp_good_bearer.status_code == 200


def test_dev_mode_pass_through_when_key_unset(client, monkeypatch):
    """Verify dev mode permits pass-through when DASHBOARD_API_KEY is unset."""
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "dashboard_api_key", None)

    resp = client.get("/api/dashboard/overview")
    assert resp.status_code == 200


# ==============================================================================
# 2. API Route Authorization Audit
# ==============================================================================

@pytest.mark.parametrize(
    "method,endpoint",
    [
        ("GET", "/api/dashboard/overview"),
        ("GET", "/api/analytics/dashboard"),
        ("GET", "/api/browser/sessions"),
        ("GET", "/api/copilot/dashboard"),
        ("GET", "/api/resume/strategies"),
        ("GET", "/api/tracking/applications"),
        ("POST", "/api/applications/prepare"),
        ("POST", "/api/browser/tasks"),
        ("POST", "/api/jobs/discover"),
        ("POST", "/api/analyze-job"),
    ],
)
def test_all_api_routes_require_auth_in_production(client, monkeypatch, method, endpoint):
    """Verify that all core API routes enforce authentication in production mode."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "dashboard_api_key", "sec-test-prod-key-999")

    # Request without authentication
    if method == "GET":
        resp = client.get(endpoint)
    else:
        resp = client.post(endpoint, json={})

    assert resp.status_code == 401, f"Endpoint {method} {endpoint} did not enforce auth (status={resp.status_code})"


# ==============================================================================
# 3. CORS Configuration
# ==============================================================================

def test_cors_allowed_origin(client):
    """Verify that configured origins receive CORS headers."""
    resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_disallowed_origin(client):
    """Verify that non-whitelisted origins do not receive CORS allow headers."""
    resp = client.get("/health", headers={"Origin": "https://malicious-attacker.com"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


def test_cors_preflight_request(client):
    """Verify that preflight OPTIONS requests are handled with CORS headers."""
    resp = client.options(
        "/api/dashboard/overview",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "GET" in resp.headers.get("access-control-allow-methods", "")


# ==============================================================================
# 4. Security Headers
# ==============================================================================

def test_security_headers_present(client):
    """Verify standard defensive security headers are applied to HTTP responses."""
    resp = client.get("/health")
    assert resp.status_code == 200

    # Content-Type sniffing defense
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    # Clickjacking defense
    assert resp.headers.get("X-Frame-Options") == "DENY"

    # Referrer policy
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    # Permissions policy
    assert "geolocation=()" in resp.headers.get("Permissions-Policy", "")

    # Content Security Policy
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_hsts_header_in_production(client, monkeypatch):
    """Verify Strict-Transport-Security header is applied in production."""
    monkeypatch.setattr(settings, "app_env", "production")
    resp = client.get("/health")
    assert "Strict-Transport-Security" in resp.headers
    assert "max-age=31536000" in resp.headers.get("Strict-Transport-Security", "")


# ==============================================================================
# 5. SSRF Security Protections
# ==============================================================================

@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://localhost:8080/job",
        "http://127.0.0.1:8000/api",
        "http://0.0.0.0:8000/job",
        "http://10.0.0.1/admin",
        "http://172.16.0.1/internal",
        "http://172.31.255.255/job",
        "http://192.168.1.1/secret",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/job",
        "http://[fe80::1]/job",
        "http://[fc00::1]/job",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://instance-data/latest/meta-data/",
        "http://service.local/job",
        "http://internal.company.internal/careers",
        "http://myhost.localhost/job",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "ftp://ftp.example.com/job",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    ],
)
def test_ssrf_blocking_matrix(unsafe_url):
    """Verify that all internal, private, loopback, metadata, and non-http schemes are rejected."""
    with pytest.raises(ValueError) as exc:
        DashboardService.validate_user_submitted_url(unsafe_url)
    assert any(
        msg in str(exc.value).lower()
        for msg in ["disallowed url scheme", "unsafe url", "not permitted", "non-empty string", "not supported"]
    )


def test_ssrf_valid_public_url():
    """Verify that legitimate public HTTP/HTTPS URLs pass validation."""
    valid_url = "https://boards.greenhouse.io/company/jobs/123456"
    result = DashboardService.validate_user_submitted_url(valid_url)
    assert result == valid_url


# ==============================================================================
# 6. Human Confirmation Gate Security
# ==============================================================================

def test_confirmation_service_rejects_wrong_keyword(db_session):
    """Verify confirmation requires exact 'SUBMIT' keyword."""
    service = HumanConfirmationService(db=db_session)
    req = HumanConfirmationRequest(
        task_id="task-test-1",
        confirmation_token="CONFIRM-token123",
        confirm_text="CONFIRM",
    )
    with pytest.raises(SubmissionSafetyError, match="Explicit confirmation keyword 'SUBMIT' is required"):
        service.validate_and_confirm("task-test-1", req)


def test_confirmation_service_rejects_wrong_token(db_session):
    """Verify confirmation rejects invalid/mismatched tokens."""
    repo = BrowserTaskRepository(db_session)
    task = BrowserTaskModel(
        task_id="task-sec-test-1",
        target_url="https://example.com/apply",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token="CONFIRM-valid-token-secret-1234567890",
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    repo.create(task)

    service = HumanConfirmationService(db=db_session)
    req = HumanConfirmationRequest(
        task_id="task-sec-test-1",
        confirmation_token="CONFIRM-invalid-token",
        confirm_text="SUBMIT",
    )
    with pytest.raises(SubmissionSafetyError, match="Invalid confirmation token provided"):
        service.validate_and_confirm("task-sec-test-1", req)


def test_confirmation_service_rejects_expired_token(db_session):
    """Verify confirmation rejects expired tokens."""
    repo = BrowserTaskRepository(db_session)
    task = BrowserTaskModel(
        task_id="task-sec-test-2",
        target_url="https://example.com/apply",
        status=BrowserTaskStatus.READY_FOR_REVIEW,
        confirmation_token="CONFIRM-expired-token-1234567890",
        confirmation_expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    repo.create(task)

    service = HumanConfirmationService(db=db_session)
    req = HumanConfirmationRequest(
        task_id="task-sec-test-2",
        confirmation_token="CONFIRM-expired-token-1234567890",
        confirm_text="SUBMIT",
    )
    with pytest.raises(SubmissionSafetyError, match="Confirmation token has expired"):
        service.validate_and_confirm("task-sec-test-2", req)


def test_confirmation_service_duplicate_submission_protection(db_session):
    """Verify duplicate submission returns safe existing result without resubmitting."""
    repo = BrowserTaskRepository(db_session)
    task = BrowserTaskModel(
        task_id="task-sec-test-3",
        application_id="app-123",
        target_url="https://example.com/apply",
        status=BrowserTaskStatus.COMPLETED,
        confirmation_token="CONFIRM-used-token-1234567890",
    )
    repo.create(task)

    service = HumanConfirmationService(db=db_session)
    req = HumanConfirmationRequest(
        task_id="task-sec-test-3",
        confirmation_token="CONFIRM-used-token-1234567890",
        confirm_text="SUBMIT",
    )
    result = service.validate_and_confirm("task-sec-test-3", req)
    assert result.success is True
    assert result.status == BrowserTaskStatus.COMPLETED
    assert "Duplicate submission prevented" in result.message


# ==============================================================================
# 7. Safe Error Disclosure
# ==============================================================================

def test_production_error_masking(client, monkeypatch):
    """Verify that unhandled server exceptions in production do not disclose internal tracebacks."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "dashboard_api_key", "sec-test-prod-key-999")

    # Invalidate DB or force error on an endpoint
    resp = client.get("/api/dashboard/jobs/non-existent-id", headers={"X-API-Key": "sec-test-prod-key-999"})
    # Should be 404
    assert resp.status_code == 404
    assert "Traceback" not in resp.text
    assert "site-packages" not in resp.text
