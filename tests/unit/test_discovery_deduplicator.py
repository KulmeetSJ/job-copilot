"""Unit tests for Phase 5 JobDeduplicator."""

import pytest
from job_copilot.ingestion.deduplicator import JobDeduplicator
from job_copilot.ingestion.models import CanonicalJob


@pytest.fixture
def deduplicator():
    return JobDeduplicator()


def test_deduplication_exact_source_id(deduplicator):
    existing = [
        CanonicalJob(
            job_id="feed-100",
            source="feed",
            source_job_id="100",
            company="Google",
            title="Software Engineer",
            clean_description="Google SWE role",
            content_hash="hash100",
        )
    ]
    candidate = CanonicalJob(
        job_id="feed-100-dup",
        source="feed",
        source_job_id="100",
        company="Google Inc",
        title="Software Engineer",
        clean_description="Google SWE role updated",
        content_hash="hash100b",
    )
    is_dup, canonical_id, reason = deduplicator.check_duplicate(candidate, existing)
    assert is_dup is True
    assert canonical_id == "feed-100"
    assert "source_job_id" in reason


def test_deduplication_canonical_url(deduplicator):
    existing = [
        CanonicalJob(
            job_id="google-swe-1",
            source="manual",
            canonical_url="https://careers.google.com/jobs/results/12345",
            company="Google",
            title="Software Engineer",
            clean_description="Work on GCP",
            content_hash="hash1",
        )
    ]
    candidate = CanonicalJob(
        job_id="linkedin-swe-2",
        source="linkedin",
        canonical_url="https://careers.google.com/jobs/results/12345",
        company="Google",
        title="Software Engineer - Cloud",
        clean_description="Work on GCP infrastructure",
        content_hash="hash2",
    )
    is_dup, canonical_id, reason = deduplicator.check_duplicate(candidate, existing)
    assert is_dup is True
    assert canonical_id == "google-swe-1"
    assert "canonical URL" in reason


def test_deduplication_content_hash(deduplicator):
    existing = [
        CanonicalJob(
            job_id="stripe-backend-1",
            source="site_a",
            company="Stripe",
            title="Backend Engineer",
            clean_description="Identical description text for stripe",
            content_hash="same_content_hash_123",
        )
    ]
    candidate = CanonicalJob(
        job_id="stripe-backend-2",
        source="site_b",
        company="Stripe",
        title="Software Engineer - Backend",
        clean_description="Identical description text for stripe",
        content_hash="same_content_hash_123",
    )
    is_dup, canonical_id, reason = deduplicator.check_duplicate(candidate, existing)
    assert is_dup is True
    assert canonical_id == "stripe-backend-1"
    assert "content hash" in reason


def test_distinct_jobs_not_merged_when_locations_differ(deduplicator):
    existing = [
        CanonicalJob(
            job_id="uber-swe-pune",
            source="uber_careers",
            company="Uber",
            title="Software Engineer",
            location="Pune, India",
            clean_description="Uber platform engineering in Pune office.",
            content_hash="hash_pune",
        )
    ]
    candidate = CanonicalJob(
        job_id="uber-swe-bangalore",
        source="uber_careers",
        company="Uber",
        title="Software Engineer",
        location="Bangalore, India",
        clean_description="Uber platform engineering in Bangalore office.",
        content_hash="hash_bangalore",
    )
    is_dup, canonical_id, reason = deduplicator.check_duplicate(candidate, existing)
    assert is_dup is False
    assert canonical_id is None
