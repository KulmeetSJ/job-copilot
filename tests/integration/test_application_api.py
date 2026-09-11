"""Integration tests for Phase 6 Application Preparation FastAPI endpoints."""

from fastapi.testclient import TestClient
import pytest

from job_copilot.api.app import app
import job_copilot.api.routes.application_prep as prep_module
from job_copilot.services.application_prep_service import ApplicationPrepService


@pytest.fixture
def client(tmp_path):
    # Isolate test directories
    prep_module.service = ApplicationPrepService(
        applications_data_dir=tmp_path / "applications",
        jobs_data_dir=tmp_path / "jobs",
    )
    return TestClient(app)


def test_api_prepare_application(client):
    payload = {
        "job_id_or_text": "Company: Stripe\nRole: Java Backend Engineer\nReqs: Java, Spring Boot, GCP.",
    }
    res = client.post("/api/applications/prepare", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["company"] == "Stripe"
    assert data["selected_resume_strategy"] == "backend_java"
    assert "cover_letter" in data
    assert len(data["answers"]) > 0


def test_api_get_application_and_cover_letter(client):
    # 1. Prepare
    prepare_payload = {
        "job_id_or_text": "Company: Adyen\nRole: Full Stack Software Engineer\nReqs: React, Java, PostgreSQL.",
    }
    create_res = client.post("/api/applications/prepare", json=prepare_payload)
    assert create_res.status_code == 200
    job_id = create_res.json()["job_id"]

    # 2. Get Application
    get_res = client.get(f"/api/applications/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["job_id"] == job_id

    # 3. Get Cover Letter
    cl_res = client.post(f"/api/applications/{job_id}/cover-letter")
    assert cl_res.status_code == 200
    assert cl_res.json()["company"] == "Adyen"

    # 4. Get User Inputs
    inp_res = client.get(f"/api/applications/{job_id}/inputs")
    assert inp_res.status_code == 200
    assert isinstance(inp_res.json(), list)

    # 5. Validate Package
    val_res = client.post(f"/api/applications/{job_id}/validate")
    assert val_res.status_code == 200
    assert "is_valid" in val_res.json()
