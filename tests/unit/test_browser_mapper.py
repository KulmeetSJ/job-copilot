"""Unit tests for Phase 7 browser field mapper."""

from pathlib import Path
from job_copilot.browser.detector import FormDetector
from job_copilot.browser.mapper import FieldMapper
from job_copilot.browser.models import (
    BrowserElementType,
    BrowserField,
    FieldClassification,
    MappingConfidence,
)
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.services.application_prep_service import ApplicationPrepService


def test_map_candidate_profile_fields():
    prep = ApplicationPrepService()
    profile = prep.load_master_profile()

    fields = [
        BrowserField(field_id="first_name", label="First Name", element_type=BrowserElementType.INPUT_TEXT),
        BrowserField(field_id="email", label="Email Address", element_type=BrowserElementType.INPUT_EMAIL),
        BrowserField(field_id="phone", label="Phone Number", element_type=BrowserElementType.INPUT_TEL),
        BrowserField(field_id="linkedin", label="LinkedIn Profile", element_type=BrowserElementType.INPUT_TEXT),
    ]

    mappings = FieldMapper.map_fields(fields, profile, package=None)
    assert len(mappings) == 4

    m_fname = next(m for m in mappings if m.field_id == "first_name")
    assert m_fname.is_safe_to_autofill is True
    assert m_fname.confidence == MappingConfidence.HIGH
    assert m_fname.proposed_value == profile.personal_info.full_name.split()[0]

    m_email = next(m for m in mappings if m.field_id == "email")
    assert m_email.is_safe_to_autofill is True
    assert m_email.proposed_value == profile.personal_info.email


def test_map_sensitive_fields_require_user_input():
    prep = ApplicationPrepService()
    profile = prep.load_master_profile()

    fields = [
        BrowserField(field_id="salary", label="Expected Salary", element_type=BrowserElementType.INPUT_TEXT),
        BrowserField(field_id="sponsorship", label="Will you require visa sponsorship?", element_type=BrowserElementType.SELECT),
    ]

    mappings = FieldMapper.map_fields(fields, profile, package=None)
    for m in mappings:
        assert m.requires_user_input is True
        assert m.is_safe_to_autofill is False
        assert m.classification == FieldClassification.USER_INPUT_REQUIRED


def test_html_form_detection_and_mapping():
    prep = ApplicationPrepService()
    profile = prep.load_master_profile()

    html = Path("tests/browser/fixtures/basic_form.html").read_text(encoding="utf-8")
    fields = FormDetector.detect_fields_from_html(html)
    assert len(fields) >= 8

    mappings = FieldMapper.map_fields(fields, profile, package=None)
    filled_candidates = [m for m in mappings if m.is_safe_to_autofill]
    assert len(filled_candidates) >= 4
