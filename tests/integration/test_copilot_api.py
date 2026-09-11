"""Integration tests for Continuous Job Copilot REST API."""

from httpx import ASGITransport, AsyncClient
import pytest

from job_copilot.api.app import app
from job_copilot.services.discovery_service import DiscoveryService


@pytest.mark.asyncio
async def test_copilot_api_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest a job into Discovery
        disc = DiscoveryService()
        raw_jd = (
            "Job Title: Senior Java Architect\n"
            "Company: ApiCloud Corp\n"
            "Requirements: 6+ years Java, Spring, Microservices, Kubernetes"
        )
        canonical = disc.ingest_text(
            text=raw_jd,
            company="ApiCloud Corp",
            title="Senior Java Architect",
        )
        job_id = canonical.job_id

        # 2. Process Job via Copilot API
        resp = await client.post("/api/copilot/process", json={"job_id": job_id})
        assert resp.status_code == 200
        job_data = resp.json()[0]
        assert job_data["job_id"] == job_id
        assert job_data["match_score"] >= 60.0
        assert "priority_band" in job_data

        # 3. Get Dashboard
        resp = await client.get("/api/copilot/dashboard")
        assert resp.status_code == 200
        dash_data = resp.json()
        assert "queue_summary" in dash_data
        assert "recent_outcomes" in dash_data

        # 4. Get Queue
        resp = await client.get("/api/copilot/queue")
        assert resp.status_code == 200
        queue_data = resp.json()
        assert len(queue_data) >= 1
        assert any(j["job_id"] == job_id for j in queue_data)

        # 5. Get Recommendations
        resp = await client.get("/api/copilot/recommendations")
        assert resp.status_code == 200
        recs = resp.json()
        assert len(recs) >= 1

        # 6. Get Insights
        resp = await client.get("/api/copilot/insights")
        assert resp.status_code == 200
        insights = resp.json()
        assert isinstance(insights, list)

        # 7. Approve Job
        resp = await client.post(f"/api/copilot/{job_id}/approve")
        assert resp.status_code == 200
        assert resp.json()["queue_status"] == "APPROVED"

        # 8. Prepare Job (One-Click)
        resp = await client.post(f"/api/copilot/{job_id}/prepare")
        assert resp.status_code == 200
        pkg_data = resp.json()
        assert pkg_data["job_id"] == job_id

        # 9. Apply Job without confirmation token -> returns SUBMISSION_BLOCKED
        resp = await client.post(f"/api/copilot/{job_id}/apply", json={"confirmation_token": None})
        assert resp.status_code == 200
        apply_data = resp.json()
        assert apply_data["status"] == "SUBMISSION_BLOCKED"

        # 10. Skip Job
        resp = await client.post(f"/api/copilot/{job_id}/skip", json={"reason": "Location mismatch"})
        assert resp.status_code == 200
        assert resp.json()["queue_status"] == "SKIPPED"
