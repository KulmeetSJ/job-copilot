"""Integration tests for FastAPI resume tailoring endpoints."""

from fastapi.testclient import TestClient
import pytest
from job_copilot.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_strategies_api(client):
    response = client.get("/api/resume/strategies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert "backend_java" in data
    assert "cloud_devops" in data


def test_get_strategy_detail_api(client):
    response = client.get("/api/resume/strategies/backend_java")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "backend_java"
    assert "Backend & Distributed Systems" in data["display_title"]


def test_analyze_job_api(client):
    payload = {
        "job_description": "We are seeking a Backend Engineer with Java and Spring Boot experience."
    }
    response = client.post("/api/resume/analyze-job", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["required_skills"]) > 0
    assert any(s["normalized_name"] == "Java" for s in data["required_skills"])


def test_tailor_resume_api(client):
    payload = {
        "strategy": "backend_java",
        "job_description": "Java Spring Boot engineer needed"
    }
    response = client.post("/api/resume/tailor", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["strategy_name"] == "backend_java"
    assert len(data["experience"]) > 0
    assert data["experience"][0]["company"] == "HSBC"
