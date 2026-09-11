"""Integration tests for Tracking and Analytics REST API."""

from httpx import ASGITransport, AsyncClient
import pytest

from job_copilot.api.app import app
from job_copilot.services.application_prep_service import ApplicationPrepService


@pytest.mark.asyncio
async def test_tracking_and_analytics_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Prepare job via Phase 6
        prep = ApplicationPrepService()
        pkg = prep.prepare_application("Job Title: Backend Architect\nCompany: ScaleTech\nRequirements: Java, Distributed Systems")
        job_id = pkg.job_id

        # 2. Register application
        resp = await client.post("/api/tracking/applications", json={"job_id": job_id})
        assert resp.status_code == 201
        data = resp.json()
        app_id = data["application_id"]
        assert data["job_id"] == job_id

        # 3. List applications
        resp = await client.get("/api/tracking/applications")
        assert resp.status_code == 200
        apps_list = resp.json()
        assert len(apps_list) >= 1

        # 4. Get single application
        resp = await client.get(f"/api/tracking/applications/{app_id}")
        assert resp.status_code == 200
        assert resp.json()["application_id"] == app_id

        # 5. Record event
        resp = await client.post(f"/api/tracking/applications/{app_id}/events", json={
            "event_type": "INTERVIEW",
            "notes": "Passed screen, tech interview scheduled",
        })
        assert resp.status_code == 200
        assert resp.json()["event_type"] == "INTERVIEW"

        # 6. Get timeline
        resp = await client.get(f"/api/tracking/applications/{app_id}/timeline")
        assert resp.status_code == 200
        timeline = resp.json()
        assert len(timeline) >= 2

        # 7. Add user note
        resp = await client.post(f"/api/tracking/applications/{app_id}/notes", json={
            "note": "Spoke with engineering manager",
        })
        assert resp.status_code == 200

        # 8. Analytics endpoints
        resp = await client.get("/api/analytics/dashboard")
        assert resp.status_code == 200
        dash = resp.json()
        assert "funnel" in dash
        assert "conversion" in dash

        resp = await client.get("/api/analytics/funnel")
        assert resp.status_code == 200

        resp = await client.get("/api/analytics/conversion")
        assert resp.status_code == 200

        resp = await client.get("/api/analytics/strategies")
        assert resp.status_code == 200

        resp = await client.get("/api/analytics/recommendations")
        assert resp.status_code == 200

        resp = await client.get("/api/analytics/sources")
        assert resp.status_code == 200

        resp = await client.get("/api/analytics/response-times")
        assert resp.status_code == 200
