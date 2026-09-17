"""Integration tests for Phase 9.2 Job Targeting, Sources, API, and Deduplication."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.copilot.models import PriorityBand, QueueStatus
from job_copilot.copilot.queue import CopilotQueueStore
from job_copilot.ingestion.deduplicator import JobDeduplicator
from job_copilot.ingestion.models import RawJob
from job_copilot.ingestion.normalizer import JobNormalizer
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.browser_workflow_service import BrowserWorkflowService
from job_copilot.services.copilot_service import CopilotService
from job_copilot.services.discovery_service import DiscoveryService
from job_copilot.services.job_intelligence_service import JobIntelligenceService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.store import TrackingStore


@pytest.fixture
def api_client():
    """FastAPI TestClient for API endpoint integration tests."""
    return TestClient(app)


def test_copilot_targeting_api_endpoints(api_client):
    """Verify GET /api/copilot/targets, /sources, and /sources/health."""
    # 1. /targets
    resp_targets = api_client.get("/api/copilot/targets")
    assert resp_targets.status_code == 200
    targets_data = resp_targets.json()
    assert "tier_1" in targets_data
    assert "tier_2" in targets_data
    assert "job_families" in targets_data
    assert "locations" in targets_data
    assert any(c["name"] == "Mastercard" for c in targets_data["tier_1"]["companies"])
    assert any(c["name"] == "Google" for c in targets_data["tier_2"]["companies"])

    # 2. /sources
    resp_sources = api_client.get("/api/copilot/sources")
    assert resp_sources.status_code == 200
    sources_data = resp_sources.json()
    assert len(sources_data) >= 6
    assert any(s["id"] == "linkedin_pune" for s in sources_data)
    assert any(s["id"] == "wellfound" for s in sources_data)

    # 3. /sources?enabled_only=true
    resp_enabled = api_client.get("/api/copilot/sources?enabled_only=true")
    assert resp_enabled.status_code == 200
    enabled_data = resp_enabled.json()
    assert all(s["enabled"] for s in enabled_data)

    # 4. /sources/health
    resp_health = api_client.get("/api/copilot/sources/health")
    assert resp_health.status_code == 200
    health_data = resp_health.json()
    assert len(health_data) >= 6
    wf_health = next(h for h in health_data if h["source_id"] == "wellfound")
    assert wf_health["state"] == "UNSUPPORTED"


def test_target_company_explanation_and_preference_isolation(tmp_path: Path):
    """
    Verify that target company preference:
    1. Adjusts priority score.
    2. Surfaces transparent targeting note in explanation.
    3. Does NOT present targeting as candidate qualification evidence.
    """
    data_dir = tmp_path / "data"
    jobs_dir = data_dir / "jobs"
    apps_dir = data_dir / "applications"
    tracking_dir = data_dir / "tracking"
    copilot_dir = data_dir / "copilot"

    disc_service = DiscoveryService(jobs_data_dir=jobs_dir)
    intel_service = JobIntelligenceService(jobs_data_dir=jobs_dir)
    prep_service = ApplicationPrepService(
        applications_data_dir=apps_dir,
        jobs_data_dir=jobs_dir,
        intelligence_service=intel_service,
    )
    track_store = TrackingStore(tracking_dir=tracking_dir, applications_dir=apps_dir)
    tracking_service = TrackingService(store=track_store, prep_service=prep_service)
    browser_service = BrowserWorkflowService(application_prep_service=prep_service, applications_data_dir=apps_dir)
    queue_store = CopilotQueueStore(queue_dir=copilot_dir)

    copilot = CopilotService(
        discovery_service=disc_service,
        intelligence_service=intel_service,
        prep_service=prep_service,
        browser_service=browser_service,
        tracking_service=tracking_service,
        queue_store=queue_store,
    )

    # Ingest a Tier 1 target company job
    mc_jd = """
    Lead Backend Engineer - Payments AI
    Mastercard is seeking an experienced Backend Engineer to scale our transaction infrastructure.
    Requirements: 8+ years Java, Spring Boot, GCP, BigQuery, Pub/Sub, Dataflow, Payments.
    """
    canon_job = disc_service.ingest_text(
        text=mc_jd,
        company="Mastercard",
        title="Lead Backend Engineer - Payments AI",
        location="Pune",
        source_url="https://www.linkedin.com/jobs/view/123456",
    )

    # Process through pipeline
    processed = copilot.process_job(canon_job.job_id)
    assert processed is not None
    assert processed.priority_score > 0
    assert processed.explanation is not None

    # Verify targeting note is present in explanation
    assert any("Tier 1 — Financial Services" in r for r in processed.explanation.why_apply)
    assert any("HSBC Payments/Data Platform" in r for r in processed.explanation.why_apply)

    # Verify evidence citations only reference canonical candidate evidence
    for ev in processed.explanation.evidence_references:
        assert ev.claim_id is not None
        assert "EXP-" in ev.claim_id or "PRJ-" in ev.claim_id or "EDU-" in ev.claim_id


def test_multi_source_deduplication_provenance():
    """
    Verify that the same job posted across multiple sources (LinkedIn, Wellfound, Career site)
    resolves to a single canonical job via Phase 5 deduplicator while preserving provenance.
    """
    normalizer = JobNormalizer()
    deduplicator = JobDeduplicator()

    jd_text = """
    Staff Backend Engineer - Payments Infrastructure
    Mastercard is seeking an experienced Backend Engineer to build real-time transaction processing systems.
    Requirements: 8+ years Java, Spring Boot, GCP, Distributed Systems, High Availability.
    """

    # 1. Job from LinkedIn
    raw_li = RawJob(
        source="linkedin_pune",
        company="Mastercard",
        title="Staff Backend Engineer - Payments",
        raw_description=jd_text,
        source_url="https://www.linkedin.com/jobs/view/123456",
    )
    canon_li = normalizer.normalize(raw_li)

    # 2. Duplicate from Wellfound
    raw_wf = RawJob(
        source="wellfound",
        company="Mastercard",
        title="Staff Backend Engineer - Payments Infrastructure",
        raw_description=jd_text,
        source_url="https://wellfound.com/jobs/789012",
    )
    canon_wf = normalizer.normalize(raw_wf)

    # Verify deduplication match
    is_dup, matched_id, reason = deduplicator.check_duplicate(candidate=canon_wf, existing_jobs=[canon_li])
    assert is_dup is True
    assert matched_id == canon_li.job_id
