"""Unit tests for Phase 7 browser models."""

from job_copilot.browser.models import (
    BrowserAuditEvent,
    BrowserAuditEventType,
    BrowserElementType,
    BrowserField,
    BrowserSession,
    BrowserSessionStatus,
    FieldClassification,
    FieldMapping,
    MappingConfidence,
    ReviewArtifact,
    SubmissionResult,
)


def test_browser_models_instantiation():
    field = BrowserField(
        field_id="first_name",
        element_type=BrowserElementType.INPUT_TEXT,
        name="first_name",
        label="First Name",
        required=True,
    )
    assert field.field_id == "first_name"
    assert field.required is True

    mapping = FieldMapping(
        field_id="first_name",
        target_field="first_name",
        classification=FieldClassification.KNOWN_CANDIDATE_FIELD,
        confidence=MappingConfidence.HIGH,
        proposed_value="John",
        is_safe_to_autofill=True,
    )
    assert mapping.is_safe_to_autofill is True

    event = BrowserAuditEvent(
        session_id="sess-123",
        event_type=BrowserAuditEventType.SESSION_STARTED,
        action="Session started",
    )
    assert event.event_type == BrowserAuditEventType.SESSION_STARTED

    review = ReviewArtifact(
        job_id="job-123",
        company="TechCorp",
        role="Backend Engineer",
        resume_strategy="backend_java",
        resume_path="data/generated/backend_java/latest.pdf",
        ready_to_submit=True,
    )
    assert review.ready_to_submit is True

    sub = SubmissionResult(
        success=True,
        confirmation_reference="REF-999",
    )
    assert sub.success is True
