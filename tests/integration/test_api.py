"""Integration tests for FastAPI application."""

from fastapi.testclient import TestClient


def test_health_check_endpoint(api_client: TestClient):
    """Test that GET /health returns 200 and {'status': 'ok'}."""
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint(api_client: TestClient):
    """Test that GET / returns 200 with service information."""
    response = api_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Job Copilot API"
    assert data["status"] == "online"
