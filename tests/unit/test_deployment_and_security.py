"""Unit tests for Phase 9.3 Deployment Foundation, Security Hardening, and Secrets."""

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.utils.logging import sanitize_message
from job_copilot.utils.security import scan_repository_for_secrets


@pytest.fixture
def client():
    """FastAPI TestClient for API endpoints."""
    return TestClient(app)


def test_health_endpoint_response(client):
    """Verify that GET /health returns 200 OK and minimal deterministic response."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    # Ensure internal paths or secrets are not leaked
    assert "password" not in data
    assert "token" not in data
    assert "path" not in data


def test_root_endpoint_response(client):
    """Verify that GET / returns service identity without leaking private state."""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "Job Copilot API"
    assert "version" in data
    assert data["status"] == "online"


def test_env_example_and_gitignore_rules():
    """Verify .env.example exists and .gitignore properly ignores sensitive runtime data."""
    root = Path.cwd()

    env_example = root / ".env.example"
    assert env_example.exists(), ".env.example must exist"
    env_content = env_example.read_text(encoding="utf-8")
    assert "APP_ENV=" in env_content
    assert "DATABASE_URL=" in env_content
    assert "LOG_LEVEL=" in env_content

    gitignore = root / ".gitignore"
    assert gitignore.exists(), ".gitignore must exist"
    gi_content = gitignore.read_text(encoding="utf-8")
    assert ".env" in gi_content
    assert "data/candidate/" in gi_content
    assert "data/jobs/" in gi_content
    assert "data/applications/" in gi_content
    assert "data/tracking/" in gi_content
    assert "data/copilot/" in gi_content
    assert "*.db" in gi_content or "*.sqlite" in gi_content


def test_repository_secret_scan_clean():
    """Verify that secret scanner finds no exposed credentials or tokens in tracked codebase."""
    root = Path.cwd()
    findings = scan_repository_for_secrets(base_dir=root)
    assert not findings, f"Repository contains potential exposed secrets: {findings}"


def test_logging_credential_sanitization():
    """Verify that sensitive patterns are redacted in log messages."""
    raw_log = "User logged in with password='SuperSecretPassword123' and api_key='ak_live_abcdef123456789'"
    sanitized = sanitize_message(raw_log)
    assert "SuperSecretPassword123" not in sanitized
    assert "ak_live_abcdef123456789" not in sanitized
    assert "[REDACTED]" in sanitized


def test_deployment_configuration_files_exist():
    """Verify presence and validity of Dockerfile, docker-compose.yml, render.yaml, and CI."""
    root = Path.cwd()

    dockerfile = root / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile must exist"
    df_content = dockerfile.read_text(encoding="utf-8")
    assert "FROM python:3.13" in df_content
    assert "USER appuser" in df_content
    assert "EXPOSE 8000" in df_content

    compose = root / "docker-compose.yml"
    assert compose.exists(), "docker-compose.yml must exist"
    compose_content = compose.read_text(encoding="utf-8")
    assert "services:" in compose_content
    assert "job-copilot-api" in compose_content

    render = root / "render.yaml"
    assert render.exists(), "render.yaml must exist"
    render_content = render.read_text(encoding="utf-8")
    assert "job-copilot-api" in render_content
    assert "healthCheckPath: /health" in render_content

    ci = root / ".github" / "workflows" / "ci.yml"
    assert ci.exists(), "CI workflow must exist"
    ci_content = ci.read_text(encoding="utf-8")
    assert "pytest -v" in ci_content
