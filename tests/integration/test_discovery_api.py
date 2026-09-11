"""Integration tests for Phase 5 Job Discovery & Ingestion FastAPI endpoints."""

from fastapi.testclient import TestClient
import pytest
from job_copilot.api.app import app
import job_copilot.api.routes.discovery as discovery_module
from job_copilot.services.discovery_service import DiscoveryService


@pytest.fixture
def client(tmp_path):
    # Isolate test store to tmp_path
    discovery_module.service = DiscoveryService(jobs_data_dir=tmp_path / "jobs")
    return TestClient(app)


def test_api_ingest_text(client):
    payload = {
        "job_description": "We are hiring a Senior Java Developer at Target Company with Spring Boot and AWS.",
        "company": "Target Company",
        "title": "Senior Java Developer",
    }
    response = client.post("/api/jobs/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["company"] == "Target Company"
    assert data["title"] == "Senior Java Developer"
    assert "job_id" in data
    assert data["lifecycle_status"] == "NORMALIZED"


def test_api_list_and_get_jobs(client):
    # Ingest a test job
    payload = {
        "job_description": "Cloud & DevOps Engineer with GCP and Terraform at FastCorp.",
        "company": "FastCorp",
        "title": "Cloud & DevOps Engineer",
    }
    create_res = client.post("/api/jobs/ingest", json=payload)
    assert create_res.status_code == 200
    job_id = create_res.json()["job_id"]

    # List jobs
    list_res = client.get("/api/jobs")
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(j["job_id"] == job_id for j in items)

    # Get single job
    get_res = client.get(f"/api/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["job_id"] == job_id


def test_api_process_stored_job(client):
    payload = {
        "job_description": "Data Engineer needed with Apache Beam, BigQuery, and Python at DataFlow Corp.",
        "company": "DataFlow Corp",
        "title": "Data Engineer",
    }
    create_res = client.post("/api/jobs/ingest", json=payload)
    assert create_res.status_code == 200
    job_id = create_res.json()["job_id"]

    # Process with Phase 4
    proc_res = client.post(f"/api/jobs/{job_id}/process")
    assert proc_res.status_code == 200
    data = proc_res.json()
    assert "score_breakdown" in data
    assert "overall_score" in data["score_breakdown"]
    assert data["recommended_strategy"] == "data_engineering"
