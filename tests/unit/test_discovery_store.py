"""Unit tests for Phase 5 JobStore and Index persistence."""

import json
from pathlib import Path
import pytest
from job_copilot.ingestion.models import CanonicalJob, JobLifecycleStatus, RawJob
from job_copilot.ingestion.store import JobStore


@pytest.fixture
def store(tmp_path):
    return JobStore(base_dir=tmp_path / "jobs")


def test_save_and_retrieve_job(store):
    raw = RawJob(
        source="manual",
        source_job_id="test-1",
        raw_description="Test JD Description",
    )
    store.save_raw_job("test-1", raw)

    canonical = CanonicalJob(
        job_id="test-1",
        source="manual",
        company="Stripe",
        title="Backend Engineer",
        clean_description="Test JD Description",
        content_hash="hash123",
    )
    store.save_canonical_job(canonical)

    loaded = store.get_canonical_job("test-1")
    assert loaded is not None
    assert loaded.company == "Stripe"
    assert loaded.title == "Backend Engineer"
    assert loaded.lifecycle_status == JobLifecycleStatus.NORMALIZED

    raw_text = store.get_raw_job_text("test-1")
    assert raw_text == "Test JD Description"

    index = store.load_index()
    assert "test-1" in index
    assert index["test-1"].company == "Stripe"


def test_path_traversal_sanitization(store):
    # Testing that relative path traversal IDs raise ValueError
    with pytest.raises(ValueError):
        store._sanitize_job_id("../../../etc/passwd")

    with pytest.raises(ValueError):
        store._sanitize_job_id("sub/dir/job1")

    with pytest.raises(ValueError):
        store._sanitize_job_id("..//..//")

    # Valid ID with safe characters succeeds
    valid = store._sanitize_job_id("stripe-backend-101.v2")
    assert valid == "stripe-backend-101.v2"


def test_update_phase_4_evaluation_status(store):
    canonical = CanonicalJob(
        job_id="stripe-eval-1",
        source="manual",
        company="Stripe",
        title="Software Engineer",
        clean_description="Stripe Java role",
        content_hash="hash_stripe",
    )
    store.save_canonical_job(canonical)

    store.update_phase_4_status(
        job_id="stripe-eval-1",
        overall_score=88.5,
        recommendation="STRONG_APPLY",
        recommended_strategy="backend_java",
    )

    index = store.load_index(reload=True)
    entry = index["stripe-eval-1"]
    assert entry.overall_fit_score == 88.5
    assert entry.recommendation == "STRONG_APPLY"
    assert entry.recommended_strategy == "backend_java"
    assert entry.lifecycle_status == JobLifecycleStatus.RECOMMENDED.value
