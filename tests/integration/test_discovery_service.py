"""Integration tests for Phase 5 DiscoveryService orchestration."""

import hashlib
from pathlib import Path
import pytest
import yaml

from job_copilot.domain.enums import RemoteStatus
from job_copilot.ingestion.models import DiscoveryQuery, JobLifecycleStatus
from job_copilot.ingestion.sources.feed import FeedJobSource
from job_copilot.services.discovery_service import DiscoveryService


@pytest.fixture
def service(tmp_path):
    jobs_dir = tmp_path / "jobs"
    pref_path = Path("data/candidate/preferences.yaml")
    return DiscoveryService(jobs_data_dir=jobs_dir, preferences_path=pref_path)


def test_manual_file_ingestion(service, tmp_path):
    sample_file = tmp_path / "sample_stripe.txt"
    sample_file.write_text(
        "Company: Stripe\nJob Title: Backend Java Engineer\nLocation: Remote\nRequirements: Java, Spring Boot, GCP.",
        encoding="utf-8",
    )

    job = service.ingest_file(str(sample_file))
    assert job is not None
    assert job.company == "Stripe"
    assert job.title == "Backend Java Engineer"
    assert job.remote_policy == RemoteStatus.REMOTE
    assert job.lifecycle_status == JobLifecycleStatus.NORMALIZED

    # Verify disk persistence
    loaded = service.store.get_canonical_job(job.job_id)
    assert loaded is not None
    assert loaded.job_id == job.job_id

    # Verify index
    index = service.store.load_index()
    assert job.job_id in index


def test_discovery_across_sources_and_preferences(service):
    # Register mock feed source
    feed = FeedJobSource(name="tech_feed")
    feed.set_static_jobs([
        {
            "id": "feed-stripe-001",
            "company": "Stripe",
            "title": "Software Engineer - Java",
            "location": "Pune, India",
            "description": "Java and Spring Boot microservices.",
        },
        {
            "id": "feed-qualcomm-002",
            "company": "Qualcomm",
            "title": "Firmware Engineer",
            "location": "San Diego, CA",
            "description": "Embedded C and RTOS development.",
        },
    ])
    service.register_source(feed)

    # Use query deriving from preferences (Software Engineer / Pune / Remote)
    query = DiscoveryQuery(
        keywords=["Software Engineer"],
        locations=["Pune", "Remote"],
    )
    result = service.discover_jobs(query)
    assert result.jobs_discovered == 1
    assert result.jobs_new == 1
    assert result.jobs[0].company == "Stripe"


def test_source_failure_resilience(service):
    # Good feed
    good_feed = FeedJobSource(name="good_feed")
    good_feed.set_static_jobs([
        {
            "id": "job-1",
            "company": "Adyen",
            "title": "Full Stack Engineer",
            "location": "Remote",
            "description": "React and Java payments platform.",
        }
    ])
    service.register_source(good_feed)

    # Broken feed that raises exception
    def failing_provider(q):
        raise ConnectionError("Upstream career site timeout (504 Gateway Timeout)")

    broken_feed = FeedJobSource(name="broken_feed", feed_provider=failing_provider)
    service.register_source(broken_feed)

    result = service.discover_jobs(DiscoveryQuery(keywords=["Engineer"]))
    assert "broken_feed" in result.failed_sources
    assert "timeout" in result.failed_sources["broken_feed"].lower()
    assert result.jobs_discovered == 1
    assert len(result.jobs) == 1
    assert result.jobs[0].company == "Adyen"


def test_phase_4_bridge_process_job(service):
    job = service.ingest_text(
        text="""
        Job Title: Software Engineer - Java Backend
        Company: Stripe
        Location: Remote
        Requirements:
        - 2+ years of Java, Spring Boot, REST APIs.
        - GCP cloud services and PostgreSQL.
        """,
        company="Stripe",
        title="Software Engineer - Java Backend",
    )

    assessment = service.process_job(job.job_id)
    assert assessment is not None
    assert assessment.score_breakdown.overall_score >= 75.0
    assert assessment.recommendation in ("STRONG_APPLY", "APPLY")
    assert assessment.recommended_strategy == "backend_java"

    # Verify index was updated with Phase 4 metrics
    index = service.store.load_index(reload=True)
    entry = index[job.job_id]
    assert entry.overall_fit_score == assessment.score_breakdown.overall_score
    assert entry.recommendation == assessment.recommendation.value
    assert entry.recommended_strategy == "backend_java"
    assert entry.lifecycle_status == JobLifecycleStatus.RECOMMENDED.value


def test_candidate_truth_isolation(service):
    master_path = Path("data/candidate/master_profile.yaml")
    original_bytes = master_path.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()

    # Ingest a JD with conflicting technologies & impossible requirements
    job = service.ingest_text(
        text="""
        Job Title: Principal Kubernetes Architect
        Company: MegaCorp
        Requirements:
        - 15+ years of AWS and production Kubernetes cluster administration.
        - Must be US Citizen.
        """
    )
    service.process_job(job.job_id)

    # Verify candidate master profile was not mutated
    after_bytes = master_path.read_bytes()
    after_hash = hashlib.sha256(after_bytes).hexdigest()
    assert original_hash == after_hash


def test_job_ranking(service):
    # Job 1: Strong match
    j1 = service.ingest_text(
        text="Company: Stripe\nRole: Java Backend Engineer\nLocation: Remote\nReqs: Java, Spring Boot, GCP, REST APIs.",
        company="Stripe",
        title="Java Backend Engineer",
    )
    # Job 2: Poor match
    j2 = service.ingest_text(
        text="Company: HardwareCo\nRole: Embedded Firmware Engineer\nLocation: Austin\nReqs: C/C++, ARM, RTOS.",
        company="HardwareCo",
        title="Embedded Firmware Engineer",
    )

    service.process_job(j1.job_id)
    service.process_job(j2.job_id)

    ranked = service.rank_jobs()
    assert len(ranked) == 2
    assert ranked[0].job_id == j1.job_id
    assert ranked[1].job_id == j2.job_id
    assert ranked[0].overall_fit_score > ranked[1].overall_fit_score
