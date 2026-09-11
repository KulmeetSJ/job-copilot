"""Integration tests for Phase 4 Job Intelligence FastAPI endpoints."""

from fastapi.testclient import TestClient
import pytest
from job_copilot.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_analyze_job(client):
    payload = {
        "job_description": "We need a Senior Backend Java Engineer at Stripe with Spring Boot and PostgreSQL.",
        "company_override": "Stripe",
    }
    response = client.post("/api/analyze-job", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["company"] == "Stripe"
    assert len(data["technical_requirements"]) > 0
    assert any(r["normalized_name"] == "Java" for r in data["technical_requirements"])


def test_api_match_job(client):
    payload = {
        "job_description": "We are seeking a Cloud Engineer with GCP, Terraform, and Jenkins.",
    }
    response = client.post("/api/match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "score_breakdown" in data
    assert "overall_score" in data["score_breakdown"]
    assert "recommendation" in data
    assert len(data["strengths"]) > 0


def test_api_recommend_job(client):
    payload = {
        "job_description": "Data Engineer with Apache Beam and BigQuery experience.",
    }
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["recommended_strategy"] == "data_engineering"
    assert data["recommendation"] in ("STRONG_APPLY", "APPLY")


def test_api_tailor_chain(client):
    payload = {
        "job_description": "Java and Spring Boot engineer needed for payments platform.",
    }
    response = client.post("/api/tailor", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["strategy_name"] == "backend_java"
    assert data["validation"]["is_valid"] is True
