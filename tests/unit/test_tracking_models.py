"""Unit tests for Phase 8 tracking models."""

from datetime import datetime, timezone
from job_copilot.tracking.models import (
    ApplicationEvent,
    ApplicationLifecycleStatus,
    ApplicationRecord,
    ApplicationSnapshot,
    EventSource,
    utc_now,
)


def test_tracking_models_instantiation():
    now = utc_now()
    event = ApplicationEvent(
        event_id="evt-1",
        application_id="app-1",
        job_id="job-1",
        event_type=ApplicationLifecycleStatus.SUBMITTED,
        timestamp=now,
        source=EventSource.BROWSER,
        notes="Applied via browser",
    )
    assert event.event_id == "evt-1"
    assert event.event_type == ApplicationLifecycleStatus.SUBMITTED

    snapshot = ApplicationSnapshot(
        application_id="app-1",
        job_id="job-1",
        timestamp=now,
        resume_strategy="backend_java",
        match_score=85.0,
        recommendation="STRONG_APPLY",
        technical_match=88.0,
        responsibility_match=82.0,
        job_source="url",
    )
    assert snapshot.resume_strategy == "backend_java"
    assert snapshot.match_score == 85.0

    record = ApplicationRecord(
        application_id="app-1",
        job_id="job-1",
        company="Stripe",
        role="Backend Engineer",
        source="url",
        current_status=ApplicationLifecycleStatus.SUBMITTED,
        current_status_at=now,
        resume_strategy="backend_java",
        match_score=85.0,
        recommendation="STRONG_APPLY",
        snapshot=snapshot,
        events=[event],
    )
    assert record.application_id == "app-1"
    assert record.current_status == ApplicationLifecycleStatus.SUBMITTED
    assert len(record.events) == 1
