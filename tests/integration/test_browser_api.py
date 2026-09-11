"""Integration tests for Browser Workflow REST API."""

from pathlib import Path
from httpx import ASGITransport, AsyncClient
import pytest

from job_copilot.api.app import app
from job_copilot.services.application_prep_service import ApplicationPrepService


@pytest.mark.asyncio
async def test_browser_api_workflow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Prepare job via Phase 6
        prep = ApplicationPrepService()
        pkg = prep.prepare_application("Job Title: Software Engineer\nCompany: TestAPI\nRequirements: Java")
        job_id = pkg.job_id

        fixture_path = str(Path("tests/browser/fixtures/basic_form.html").resolve())

        # 2. Start session
        resp = await client.post("/api/browser/start", json={
            "job_id": job_id,
            "application_url": fixture_path,
            "headless": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        session_id = data["session_id"]
        assert data["job_id"] == job_id

        # 3. Get session
        resp = await client.get(f"/api/browser/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == session_id

        # 4. Fill session
        resp = await client.post(f"/api/browser/{session_id}/fill")
        assert resp.status_code == 200
        fill_data = resp.json()
        assert len(fill_data["filled_fields"]) > 0

        # 5. Inputs
        resp = await client.get(f"/api/browser/{session_id}/inputs")
        assert resp.status_code == 200

        # 6. Review
        resp = await client.post(f"/api/browser/{session_id}/review")
        assert resp.status_code == 200
        review_data = resp.json()
        assert "company" in review_data

        # 7. Submit without confirmation -> 403 Forbidden
        resp = await client.post(f"/api/browser/{session_id}/submit", json={"confirmed": False})
        assert resp.status_code == 403

        # 8. Cancel
        resp = await client.post(f"/api/browser/{session_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "CANCELLED"
