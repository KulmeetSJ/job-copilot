"""Regression tests for Browser Review Flow, Mapped Fields Hydration, and Submission Authorization."""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from job_copilot.models.base import Base
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus, FieldAction
from job_copilot.domain.enums import ApplicationStatus, ResumeStrategy
from job_copilot.models.application import Application
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.schemas.dashboard import (
    HumanInputAnswerItem,
    HumanInputSubmitRequest,
    SubmissionConfirmPayload,
)
from job_copilot.services.dashboard_service import DashboardService
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import SubmissionSafetyError


@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def dashboard_service(in_memory_db, tmp_path):
    prep = ApplicationPrepService(applications_data_dir=tmp_path / "apps")
    tracking = TrackingService(tracking_dir=tmp_path / "tracking")
    return DashboardService(db=in_memory_db, prep_service=prep, tracking_service=tracking)


def _seed_barclays_fixtures(in_memory_db, prep_service):
    """Seed a realistic Barclays application fixture with 4 detected fields (2 evidence-backed, 2 needs input)."""
    job_repo = JobRepository(in_memory_db)
    app_repo = ApplicationRepository(in_memory_db)
    task_repo = BrowserTaskRepository(in_memory_db)

    job_id = "barclays-software-engineer-infrastructure-13015"
    app_id = "app_barclays_infra_12860"
    url = "https://search.jobs.barclays/job/-/-/13015/98832951728?src=JB-12860"

    db_job = Job(
        job_id=job_id,
        title="Software Engineer – Infrastructure",
        company="Barclays",
        source="user_submitted_url",
        url=url,
        canonical_url=url,
        description="Barclays Infrastructure Engineering role.",
    )
    in_memory_db.add(db_job)
    in_memory_db.flush()

    db_app = Application(
        application_id=app_id,
        job_id=db_job.id,
        job_id_str=job_id,
        canonical_job_url=url,
        source="user_submitted_url",
        strategy_used=ResumeStrategy.CLOUD_DEVOPS,
        status=ApplicationStatus.READY_TO_APPLY,
        applied_at=None,
    )
    in_memory_db.add(db_app)
    in_memory_db.flush()

    # Initial browser task in QUEUED state
    browser_task = BrowserTaskModel(
        task_id=f"task-bw-{app_id}",
        application_id=app_id,
        job_id=job_id,
        source="user_submitted_url",
        target_url=url,
        status=BrowserTaskStatus.QUEUED,
        confirmation_token=None,
        confirmation_expires_at=None,
        review_package_json={
            "detected_fields": [
                "Full Name",
                "Email Address",
                "Will you now or in the future require visa sponsorship?",
                "What are your salary expectations?",
            ],
            "filled_fields": [
                "Full Name",
                "Email Address",
            ],
            "unresolved_fields": [
                "Will you now or in the future require visa sponsorship?",
                "What are your salary expectations?",
            ],
            "fields_summary": [
                {
                    "field_id": "full_name",
                    "name": "full_name",
                    "label": "Full Name",
                    "element_type": "text",
                    "action": "AUTO_FILL",
                    "filled_value_masked": "Jane Doe",
                    "evidence_source": "master_profile.yaml",
                    "reason": "Direct evidence match",
                },
                {
                    "field_id": "email",
                    "name": "email",
                    "label": "Email Address",
                    "element_type": "text",
                    "action": "AUTO_FILL",
                    "filled_value_masked": "jane@example.com",
                    "evidence_source": "master_profile.yaml",
                    "reason": "Direct evidence match",
                },
                {
                    "field_id": "visa_sponsorship",
                    "name": "visa_sponsorship",
                    "label": "Will you now or in the future require visa sponsorship?",
                    "element_type": "select",
                    "action": "REQUIRES_USER_INPUT",
                    "filled_value_masked": None,
                    "evidence_source": None,
                    "reason": "Sensitive question requiring user confirmation",
                },
                {
                    "field_id": "salary_expectations",
                    "name": "salary_expectations",
                    "label": "What are your salary expectations?",
                    "element_type": "text",
                    "action": "REQUIRES_USER_INPUT",
                    "filled_value_masked": None,
                    "evidence_source": None,
                    "reason": "Sensitive compensation question",
                },
            ],
        },
    )
    in_memory_db.add(browser_task)
    in_memory_db.commit()

    return app_id, job_id, browser_task.task_id


def test_queued_task_rendering_and_invariants(dashboard_service, in_memory_db):
    """Test 1: If BrowserTask is QUEUED, task status is QUEUED, no token generated, not ready for review."""
    app_id, job_id, task_id = _seed_barclays_fixtures(in_memory_db, dashboard_service.prep_service)

    detail = dashboard_service.get_application_detail(app_id)
    assert detail.browser_review is not None
    assert detail.browser_review.status == "QUEUED"
    assert detail.browser_review.is_ready_for_review is False
    assert detail.browser_review.has_confirmation_token is False
    assert detail.browser_review.confirmation_token is None


def test_inspected_ready_for_review_task_rendering(dashboard_service, in_memory_db):
    """Test 2: When worker completes inspection, task transitions to READY_FOR_REVIEW with confirmation token."""
    app_id, job_id, task_id = _seed_barclays_fixtures(in_memory_db, dashboard_service.prep_service)

    task_repo = BrowserTaskRepository(in_memory_db)
    token = HumanConfirmationService.generate_confirmation_token()
    task_repo.update_status(task_id, BrowserTaskStatus.READY_FOR_REVIEW)
    task_repo.set_review_package(
        task_id=task_id,
        review_package={
            "fields_summary": [
                {"field_id": "full_name", "label": "Full Name", "action": "AUTO_FILL", "filled_value_masked": "Jane Doe", "evidence_source": "master_profile.yaml"},
                {"field_id": "email", "label": "Email", "action": "AUTO_FILL", "filled_value_masked": "jane@example.com", "evidence_source": "master_profile.yaml"},
            ]
        },
        confirmation_token=token,
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    in_memory_db.commit()

    detail = dashboard_service.get_application_detail(app_id)
    assert detail.browser_review is not None
    assert detail.browser_review.status == "READY_FOR_REVIEW"
    assert detail.browser_review.is_ready_for_review is True
    assert detail.browser_review.has_confirmation_token is True
    assert detail.browser_review.confirmation_token == token


def test_all_mapped_fields_returned_and_count_matches(dashboard_service, in_memory_db):
    """Test 3: Exactly 4 detected fields correspond to 4 returned mapped fields with 2/4 filled initially."""
    app_id, job_id, task_id = _seed_barclays_fixtures(in_memory_db, dashboard_service.prep_service)

    detail = dashboard_service.get_application_detail(app_id)
    assert detail.browser_review is not None
    assert detail.browser_review.fields_detected_count == 4
    assert detail.browser_review.fields_filled_count == 2
    assert detail.browser_review.fields_requiring_input_count == 2

    # Exactly 4 displayed fields
    mapped_fields = detail.browser_review.mapped_fields
    assert len(mapped_fields) == 4

    field_ids = {f.field_id for f in mapped_fields}
    assert "full_name" in field_ids
    assert "email" in field_ids
    assert "visa_sponsorship" in field_ids
    assert "salary_expectations" in field_ids


def test_persisted_human_answers_appear_in_mapped_fields(dashboard_service, in_memory_db):
    """Test 4: Saved sensitive answers appear in the correct mapped fields with source='Human Input' and 4/4 filled."""
    app_id, job_id, task_id = _seed_barclays_fixtures(in_memory_db, dashboard_service.prep_service)

    # Submit 2 user answers
    payload = HumanInputSubmitRequest(
        answers=[
            HumanInputAnswerItem(
                question_id="visa_sponsorship",
                question_text="Will you now or in the future require visa sponsorship?",
                answer_value="Authorized to work in UK without visa sponsorship",
            ),
            HumanInputAnswerItem(
                question_id="salary_expectations",
                question_text="What are your salary expectations?",
                answer_value="£95,000 gross per annum",
            ),
        ]
    )
    detail_after_save = dashboard_service.submit_user_inputs(app_id, payload)

    assert detail_after_save.browser_review is not None
    assert detail_after_save.browser_review.fields_detected_count == 4
    assert detail_after_save.browser_review.fields_filled_count == 4
    assert detail_after_save.browser_review.fields_requiring_input_count == 0

    mapped_fields = {f.field_id: f for f in detail_after_save.browser_review.mapped_fields}
    assert mapped_fields["visa_sponsorship"].value == "Authorized to work in UK without visa sponsorship"
    assert mapped_fields["visa_sponsorship"].source == "Human Input"
    assert mapped_fields["visa_sponsorship"].action == "USER_PROVIDED"
    assert mapped_fields["visa_sponsorship"].status == "FILLED"

    assert mapped_fields["salary_expectations"].value == "£95,000 gross per annum"
    assert mapped_fields["salary_expectations"].source == "Human Input"
    assert mapped_fields["salary_expectations"].action == "USER_PROVIDED"
    assert mapped_fields["salary_expectations"].status == "FILLED"


def test_no_submission_authorization_before_task_is_ready(dashboard_service, in_memory_db):
    """Test 5: Submitting confirmation on a QUEUED task without valid token raises safety error."""
    app_id, job_id, task_id = _seed_barclays_fixtures(in_memory_db, dashboard_service.prep_service)

    # Task is QUEUED with no token
    confirm_payload = SubmissionConfirmPayload(
        task_id=task_id,
        confirmation_token="invalid_token",
        confirm_text="SUBMIT",
    )

    with pytest.raises(SubmissionSafetyError):
        dashboard_service.confirm_submission(confirm_payload, application_id=app_id)


def test_submission_authorization_transitions_strictly_to_authorized_not_submitted(dashboard_service, in_memory_db):
    """Test 6: Valid confirmation transitions strictly to SUBMISSION_AUTHORIZED without faking SUBMITTED."""
    app_id, job_id, task_id = _seed_barclays_fixtures(in_memory_db, dashboard_service.prep_service)

    task_repo = BrowserTaskRepository(in_memory_db)
    token = HumanConfirmationService.generate_confirmation_token()
    task_repo.update_status(task_id, BrowserTaskStatus.READY_FOR_REVIEW)
    task_repo.set_review_package(
        task_id=task_id,
        review_package={"fields": []},
        confirmation_token=token,
        confirmation_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    in_memory_db.commit()

    confirm_payload = SubmissionConfirmPayload(
        task_id=task_id,
        confirmation_token=token,
        confirm_text="SUBMIT",
    )

    res = dashboard_service.confirm_submission(confirm_payload, application_id=app_id)
    assert res.success is True
    assert res.status == "SUBMISSION_AUTHORIZED"

    # Invariant: Must NOT be marked SUBMITTED / APPLIED
    task_after = task_repo.get_by_task_id(task_id)
    assert task_after.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED

    detail = dashboard_service.get_application_detail(app_id)
    assert detail.status != "APPLIED"
    assert detail.status != "SUBMITTED"
