"""Integration tests for TrackingService and Phase 7 integration."""

from pathlib import Path
import pytest

from job_copilot.browser.models import SubmissionResult
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.models import ApplicationLifecycleStatus


from job_copilot.tracking.store import TrackingStore


def test_tracking_registration_and_lifecycle(tmp_path):
    prep = ApplicationPrepService(
        applications_data_dir=tmp_path / "apps",
        jobs_data_dir=tmp_path / "jobs",
    )
    pkg = prep.prepare_application("Job Title: Lead Java Engineer\nCompany: TargetCo\nRequirements: Java, GCP, Payments")
    job_id = pkg.job_id

    tracking = TrackingService(
        prep_service=prep,
        tracking_dir=tmp_path / "tracking",
    )

    # 1. Register application submission
    sub_res = SubmissionResult(
        success=True,
        confirmation_reference="REF-XYZ-123",
        evidence="Form submission confirmed",
    )
    record = tracking.register_submission(job_id=job_id, package=pkg, submission_result=sub_res)
    assert record is not None
    assert record.current_status == ApplicationLifecycleStatus.SUBMITTED
    assert record.snapshot is not None
    assert record.snapshot.resume_strategy == pkg.selected_resume_strategy
    assert record.snapshot.match_score == pkg.assessment.score_breakdown.overall_score

    app_id = record.application_id

    # 2. Verify snapshot immutability
    frozen_score = record.snapshot.match_score
    frozen_strategy = record.snapshot.resume_strategy

    # Simulate re-generating package with different strategy
    re_pkg = prep.prepare_application("Job Title: Lead Java Engineer\nCompany: TargetCo\nRequirements: Java, GCP, Payments", strategy_override="cloud_devops")
    fetched_app = tracking.get_application(app_id)
    assert fetched_app.snapshot.resume_strategy == frozen_strategy
    assert fetched_app.snapshot.match_score == frozen_score

    # 3. Record progression: RECRUITER_RESPONSE -> INTERVIEW -> OFFER
    ev1 = tracking.record_event(app_id, ApplicationLifecycleStatus.RECRUITER_RESPONSE, notes="Recruiter emailed")
    assert ev1.event_type == ApplicationLifecycleStatus.RECRUITER_RESPONSE

    ev2 = tracking.record_event(app_id, ApplicationLifecycleStatus.INTERVIEW, notes="Technical round scheduled")
    assert ev2.event_type == ApplicationLifecycleStatus.INTERVIEW

    ev3 = tracking.record_event(app_id, ApplicationLifecycleStatus.OFFER, notes="Received offer letter")
    assert ev3.event_type == ApplicationLifecycleStatus.OFFER

    # 4. Check timeline
    timeline = tracking.get_timeline(app_id)
    assert len(timeline) >= 4  # PREPARED, SUBMITTED, RECRUITER_RESPONSE, INTERVIEW, OFFER
    assert timeline[-1].event_type == ApplicationLifecycleStatus.OFFER

    # 5. Check dashboard metrics
    dashboard = tracking.get_analytics_dashboard()
    assert dashboard.funnel.submitted >= 1
    assert dashboard.funnel.offers >= 1
