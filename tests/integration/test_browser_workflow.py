"""Integration tests for Phase 7 Browser Workflow Service."""

from pathlib import Path
import pytest
import yaml

from job_copilot.browser.models import BrowserSessionStatus
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.browser_workflow_service import BrowserWorkflowService


@pytest.mark.asyncio
async def test_end_to_end_browser_workflow():
    # 1. Prepare Phase 6 application package first
    prep = ApplicationPrepService()
    job_text = """
    Job Title: Senior Software Engineer — Backend
    Company: HSBC FinTech
    Requirements:
    - 5+ years backend Java experience
    - GCP, Spring Boot, Distributed Systems
    - Payment systems architecture
    """
    pkg = prep.prepare_application(job_text)
    assert pkg is not None
    job_id = pkg.job_id

    # 2. Start browser session with representative form fixture
    service = BrowserWorkflowService(application_prep_service=prep)
    fixture_path = str(Path("tests/browser/fixtures/representative_job_application.html").resolve())

    session = await service.start_session(job_id=job_id, application_url=fixture_path, headless=True)
    assert session.status == BrowserSessionStatus.READY_FOR_REVIEW
    assert len(session.detected_fields) >= 8

    # 3. Auto-fill safe fields
    session = await service.fill_session(session.session_id)
    assert session.status == BrowserSessionStatus.WAITING_FOR_USER
    assert len(session.filled_fields) >= 4

    # Verify contact fields and resume were filled
    assert "first_name" in session.filled_fields
    assert "resume" in session.filled_fields or any("resume" in k for k in session.filled_fields)

    # Verify sensitive fields are unresolved
    assert len(session.unresolved_fields) >= 2
    assert any("sponsorship" in f or "salary" in f or "k8s" in f for f in session.unresolved_fields)

    # 4. Provide user inputs for sensitive fields
    for field_id in list(session.unresolved_fields):
        if "sponsorship" in field_id:
            await service.provide_user_input(session.session_id, field_id, "No")
        elif "salary" in field_id:
            await service.provide_user_input(session.session_id, field_id, "$160,000")
        elif "k8s" in field_id:
            await service.provide_user_input(session.session_id, field_id, "3")
        else:
            await service.provide_user_input(session.session_id, field_id, "N/A")

    # 5. Review session
    review = await service.review_session(session.session_id)
    assert review.validation == "PASS"
    assert review.ready_to_submit is True
    assert review.unresolved == 0

    # 6. Attempt submission without explicit confirmation -> blocked
    with pytest.raises(PermissionError):
        await service.submit_session(session.session_id, confirmed=False)

    # 7. Submit with explicit confirmation -> succeeds
    result = await service.submit_session(session.session_id, confirmed=True, confirm_text="SUBMIT")
    assert result.success is True
    assert result.confirmation_reference is not None

    session = service.get_session(session.session_id)
    assert session.status == BrowserSessionStatus.SUBMITTED

    # 8. Duplicate submission protection -> blocked
    with pytest.raises(ValueError):
        await service.start_session(job_id=job_id, application_url=fixture_path, headless=True)

    await service.cancel_session(session.session_id)


@pytest.mark.asyncio
async def test_browser_login_and_captcha_pauses():
    prep = ApplicationPrepService()
    pkg = prep.prepare_application("Job Title: Backend Engineer\nCompany: TestCorp\nRequirements: Java")
    job_id = pkg.job_id
    service = BrowserWorkflowService(application_prep_service=prep)

    # Login fixture
    login_fixture = str(Path("tests/browser/fixtures/login_page.html").resolve())
    sess_login = await service.start_session(job_id=job_id, application_url=login_fixture, headless=True)
    assert sess_login.status == BrowserSessionStatus.WAITING_FOR_USER
    assert "login" in sess_login.pause_reason.lower() or "authentication" in sess_login.pause_reason.lower()
    await service.cancel_session(sess_login.session_id)

    # CAPTCHA fixture
    captcha_fixture = str(Path("tests/browser/fixtures/captcha_page.html").resolve())
    sess_captcha = await service.start_session(job_id=job_id, application_url=captcha_fixture, headless=True)
    assert sess_captcha.status == BrowserSessionStatus.WAITING_FOR_USER
    assert "captcha" in sess_captcha.pause_reason.lower() or "bot" in sess_captcha.pause_reason.lower()
    await service.cancel_session(sess_captcha.session_id)


def test_candidate_truth_immutability():
    """Verify master candidate files remain strictly unmodified."""
    master_path = Path("data/candidate/master_profile.yaml")
    evidence_path = Path("data/candidate/evidence.yaml")
    prefs_path = Path("data/candidate/preferences.yaml")

    before_master = master_path.read_text(encoding="utf-8")
    before_evidence = evidence_path.read_text(encoding="utf-8")
    before_prefs = prefs_path.read_text(encoding="utf-8")

    prep = ApplicationPrepService()
    pkg = prep.prepare_application("Job Title: Java Lead\nCompany: Enterprise\nRequirements: Java, GCP")
    service = BrowserWorkflowService(application_prep_service=prep)

    after_master = master_path.read_text(encoding="utf-8")
    after_evidence = evidence_path.read_text(encoding="utf-8")
    after_prefs = prefs_path.read_text(encoding="utf-8")

    assert before_master == after_master
    assert before_evidence == after_evidence
    assert before_prefs == after_prefs
