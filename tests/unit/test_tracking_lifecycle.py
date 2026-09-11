"""Unit tests for tracking lifecycle transitions and status derivation."""

from datetime import datetime, timezone, timedelta
from job_copilot.tracking.lifecycle import LifecycleValidator
from job_copilot.tracking.models import (
    ApplicationEvent,
    ApplicationLifecycleStatus,
    EventSource,
    utc_now,
)


def test_valid_lifecycle_transitions():
    # DISCOVERED -> PREPARED -> SUBMITTED -> INTERVIEW -> OFFER -> ACCEPTED
    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.DISCOVERED, ApplicationLifecycleStatus.PREPARED)
    assert ok is True

    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.PREPARED, ApplicationLifecycleStatus.SUBMITTED)
    assert ok is True

    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.SUBMITTED, ApplicationLifecycleStatus.INTERVIEW)
    assert ok is True

    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.INTERVIEW, ApplicationLifecycleStatus.OFFER)
    assert ok is True

    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.OFFER, ApplicationLifecycleStatus.ACCEPTED)
    assert ok is True


def test_transition_to_outcome_and_archive_states():
    # Can transition to REJECTED, WITHDRAWN, EXPIRED, OFFER, ACCEPTED from any active state
    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.SUBMITTED, ApplicationLifecycleStatus.REJECTED)
    assert ok is True

    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.INTERVIEW, ApplicationLifecycleStatus.WITHDRAWN)
    assert ok is True

    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.DISCOVERED, ApplicationLifecycleStatus.EXPIRED)
    assert ok is True

    # Outcome states can transition to CLOSED (archived)
    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.ACCEPTED, ApplicationLifecycleStatus.CLOSED)
    assert ok is True

    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.REJECTED, ApplicationLifecycleStatus.CLOSED)
    assert ok is True

    ok, _ = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.WITHDRAWN, ApplicationLifecycleStatus.CLOSED)
    assert ok is True

    # Archived state (CLOSED) cannot transition to any other state
    ok, err = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.CLOSED, ApplicationLifecycleStatus.INTERVIEW)
    assert ok is False
    assert "archived" in err.lower() or "cannot transition" in err.lower()


def test_invalid_regression_transition():
    # Regression from OFFER back to PREPARED is disallowed
    ok, err = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.OFFER, ApplicationLifecycleStatus.PREPARED)
    assert ok is False
    assert "disallowed" in err.lower() or "regression" in err.lower() or "outcome" in err.lower()

    # Regression from INTERVIEW back to PREPARED is disallowed
    ok, err = LifecycleValidator.validate_transition(ApplicationLifecycleStatus.INTERVIEW, ApplicationLifecycleStatus.PREPARED)
    assert ok is False
    assert "regression" in err.lower() or "disallowed" in err.lower()


def test_derive_current_status():
    t0 = utc_now()
    t1 = t0 + timedelta(hours=2)
    t2 = t0 + timedelta(days=3)

    events = [
        ApplicationEvent(event_id="e1", application_id="a1", job_id="j1", event_type=ApplicationLifecycleStatus.SUBMITTED, timestamp=t0),
        ApplicationEvent(event_id="e2", application_id="a1", job_id="j1", event_type=ApplicationLifecycleStatus.RECRUITER_RESPONSE, timestamp=t1),
        ApplicationEvent(event_id="e3", application_id="a1", job_id="j1", event_type=ApplicationLifecycleStatus.INTERVIEW, timestamp=t2),
    ]

    status, ts = LifecycleValidator.derive_current_status(events)
    assert status == ApplicationLifecycleStatus.INTERVIEW
    assert ts == t2
