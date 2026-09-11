"""Comprehensive End-to-End Funnel and Analytics Integration Tests for Phase 8.1."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from job_copilot.browser.models import SubmissionResult
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.adapter import TrackingAdapter
from job_copilot.tracking.models import (
    ApplicationEvent,
    ApplicationLifecycleStatus,
    ApplicationRecord,
    EventSource,
    utc_now,
)
from job_copilot.tracking.store import TrackingStore


def test_phase_5_discovery_to_tracking(tmp_path: Path):
    """Test Phase 5 discovered job properly registers in Tracking."""
    store = TrackingStore(tracking_dir=tmp_path / "tracking", applications_dir=tmp_path / "apps")
    tracking = TrackingService(store=store)
    adapter = TrackingAdapter(tracking_service=tracking)

    t0 = utc_now()
    record = adapter.on_job_discovered(
        job_id="job-gh-101",
        company="Fintech Payments Inc",
        role="Senior Backend Engineer",
        source="greenhouse",
        canonical_url="https://boards.greenhouse.io/fintech/jobs/101",
        discovered_at=t0,
    )

    assert record.job_id == "job-gh-101"
    assert record.company == "Fintech Payments Inc"
    assert record.role == "Senior Backend Engineer"
    assert record.source == "greenhouse"
    assert record.canonical_job_url == "https://boards.greenhouse.io/fintech/jobs/101"
    assert record.current_status == ApplicationLifecycleStatus.DISCOVERED
    assert record.discovered_at == t0
    assert len(record.events) == 1
    assert record.events[0].event_type == ApplicationLifecycleStatus.DISCOVERED


def test_phase_4_recommendation_to_tracking(tmp_path: Path):
    """Test Phase 4 recommendation and scoring properly registers in Tracking."""
    prep = ApplicationPrepService()
    pkg = prep.prepare_application("Job Title: Cloud Architect\nCompany: CloudCo\nRequirements: GCP, Terraform, Kubernetes")
    assessment = pkg.assessment

    store = TrackingStore(tracking_dir=tmp_path / "tracking", applications_dir=tmp_path / "apps")
    tracking = TrackingService(store=store, prep_service=prep)
    adapter = TrackingAdapter(tracking_service=tracking)

    # 1. Discover
    adapter.on_job_discovered(
        job_id=assessment.job.job_id,
        company=assessment.job.company,
        role=assessment.job.title,
        source="manual",
    )

    # 2. Recommend
    record = adapter.on_recommendation(job_id=assessment.job.job_id, assessment=assessment)
    assert record.current_status == ApplicationLifecycleStatus.RECOMMENDED
    assert record.recommendation == assessment.recommendation.value
    assert record.match_score == assessment.score_breakdown.overall_score
    assert record.resume_strategy == assessment.recommended_strategy
    assert any(e.event_type == ApplicationLifecycleStatus.RECOMMENDED for e in record.events)


def test_phase_6_prep_and_ready_for_review_to_tracking(tmp_path: Path):
    """Test Phase 6 preparation and Phase 7 ready for review register in Tracking."""
    prep = ApplicationPrepService()
    pkg = prep.prepare_application("Job Title: Full Stack Developer\nCompany: WebTech\nRequirements: TypeScript, React, Node.js")

    store = TrackingStore(tracking_dir=tmp_path / "tracking", applications_dir=tmp_path / "apps")
    tracking = TrackingService(store=store, prep_service=prep)
    adapter = TrackingAdapter(tracking_service=tracking)

    # 1. Prepared
    rec1 = adapter.on_application_prepared(package=pkg)
    assert rec1.current_status == ApplicationLifecycleStatus.PREPARED
    assert rec1.package_path is not None
    assert any(e.event_type == ApplicationLifecycleStatus.PREPARED for e in rec1.events)

    # 2. Ready for review
    rec2 = adapter.on_ready_for_review(job_id=pkg.job_id, browser_session_id="sess-xyz-999")
    assert rec2.current_status == ApplicationLifecycleStatus.READY_FOR_REVIEW
    assert rec2.browser_session_id == "sess-xyz-999"
    assert any(e.event_type == ApplicationLifecycleStatus.READY_FOR_REVIEW for e in rec2.events)


def test_submission_preserves_snapshot_immutability(tmp_path: Path):
    """Verify historical submission snapshot remains immutable."""
    prep = ApplicationPrepService()
    pkg = prep.prepare_application("Job Title: Staff SRE\nCompany: InfraScale\nRequirements: Kubernetes, Prometheus, Python")

    store = TrackingStore(tracking_dir=tmp_path / "tracking", applications_dir=tmp_path / "apps")
    tracking = TrackingService(store=store, prep_service=prep)

    sub_res = SubmissionResult(success=True, confirmation_reference="CONF-SRE-777", evidence="DOM confirmed")
    record = tracking.register_submission(job_id=pkg.job_id, package=pkg, submission_result=sub_res)

    snapshot_original = record.snapshot.model_dump()

    # Log subsequent events: RECRUITER_RESPONSE -> INTERVIEW -> REJECTED -> CLOSED
    tracking.record_event(record.application_id, ApplicationLifecycleStatus.RECRUITER_RESPONSE)
    tracking.record_event(record.application_id, ApplicationLifecycleStatus.INTERVIEW)
    tracking.record_event(record.application_id, ApplicationLifecycleStatus.REJECTED)
    tracking.record_event(record.application_id, ApplicationLifecycleStatus.CLOSED)

    fetched = tracking.get_application(record.application_id)
    assert fetched.current_status == ApplicationLifecycleStatus.CLOSED
    assert fetched.snapshot.model_dump() == snapshot_original


def test_complete_and_partial_funnel_analytics_fixture(tmp_path: Path):
    """
    Test exact fixture requirement (Phase 8.1 Section 8 & 9):
    10 discovered jobs
    ↓
    7 recommended
    ↓
    5 prepared
    ↓
    4 submitted
    ↓
    2 recruiter responses
    ↓
    2 interviews (one with multiple rounds to test deduplication)
    ↓
    1 offer
    ↓
    1 accepted

    Also tests partial funnel representation:
    - 1 discovered-but-not-recommended job (included in the 3 unrecommended)
    - 1 recommended-but-not-prepared job (included in the 2 unprepared)
    - 1 prepared-but-not-submitted job (included in the 1 unsubmitted)
    - 1 submitted-but-rejected job (tracked under submitted + rejected)
    """
    store = TrackingStore(tracking_dir=tmp_path / "tracking", applications_dir=tmp_path / "apps")
    tracking = TrackingService(store=store)
    now = utc_now()

    # 1. Create 10 Discovered Applications
    apps: list[ApplicationRecord] = []
    for i in range(10):
        rec = tracking.register_discovered_job(
            job_id=f"job-{i}",
            company=f"Company-{i}",
            role=f"Role-{i}",
            source="linkedin" if i % 2 == 0 else "greenhouse",
            discovered_at=now - timedelta(days=20 - i),
        )
        apps.append(rec)

    # 2. 7 Recommended (apps 0..6)
    for i in range(7):
        app = apps[i]
        app.recommended_at = now - timedelta(days=18 - i)
        app.recommendation = "APPLY"
        app.match_score = 80.0 + i
        app.resume_strategy = "backend_java"
        ev = ApplicationEvent(
            event_id=f"evt-rec-{i}",
            application_id=app.application_id,
            job_id=app.job_id,
            event_type=ApplicationLifecycleStatus.RECOMMENDED,
            timestamp=app.recommended_at,
            source=EventSource.SYSTEM,
        )
        app.events.append(ev)
        app.current_status = ApplicationLifecycleStatus.RECOMMENDED
        store.save_application(app)
        store.append_event(ev)

    # 3. 5 Prepared (apps 0..4)
    for i in range(5):
        app = apps[i]
        app.prepared_at = now - timedelta(days=15 - i)
        ev = ApplicationEvent(
            event_id=f"evt-prep-{i}",
            application_id=app.application_id,
            job_id=app.job_id,
            event_type=ApplicationLifecycleStatus.PREPARED,
            timestamp=app.prepared_at,
            source=EventSource.SYSTEM,
        )
        app.events.append(ev)
        app.current_status = ApplicationLifecycleStatus.PREPARED
        store.save_application(app)
        store.append_event(ev)

    # 4. 4 Submitted (apps 0..3)
    for i in range(4):
        app = apps[i]
        app.submitted_at = now - timedelta(days=12 - i)
        ev = ApplicationEvent(
            event_id=f"evt-sub-{i}",
            application_id=app.application_id,
            job_id=app.job_id,
            event_type=ApplicationLifecycleStatus.SUBMITTED,
            timestamp=app.submitted_at,
            source=EventSource.SYSTEM,
        )
        app.events.append(ev)
        app.current_status = ApplicationLifecycleStatus.SUBMITTED
        store.save_application(app)
        store.append_event(ev)

    # App 3: Submitted-but-rejected
    app3 = apps[3]
    ev_rej = ApplicationEvent(
        event_id="evt-rej-3",
        application_id=app3.application_id,
        job_id=app3.job_id,
        event_type=ApplicationLifecycleStatus.REJECTED,
        timestamp=now - timedelta(days=8),
        source=EventSource.EMAIL,
    )
    app3.events.append(ev_rej)
    app3.current_status = ApplicationLifecycleStatus.REJECTED
    store.save_application(app3)
    store.append_event(ev_rej)

    # 5. 2 Recruiter Responses (apps 0, 1)
    for i in range(2):
        app = apps[i]
        ev = ApplicationEvent(
            event_id=f"evt-resp-{i}",
            application_id=app.application_id,
            job_id=app.job_id,
            event_type=ApplicationLifecycleStatus.RECRUITER_RESPONSE,
            timestamp=now - timedelta(days=8 - i),
            source=EventSource.EMAIL,
        )
        app.events.append(ev)
        app.current_status = ApplicationLifecycleStatus.RECRUITER_RESPONSE
        store.save_application(app)
        store.append_event(ev)

    # 6. 2 Interviews (apps 0, 1)
    # App 0 has 3 interview rounds to test deduplication protection
    for round_idx in [1, 2, 3]:
        ev_int = ApplicationEvent(
            event_id=f"evt-intv-0-r{round_idx}",
            application_id=apps[0].application_id,
            job_id=apps[0].job_id,
            event_type=ApplicationLifecycleStatus.INTERVIEW,
            timestamp=now - timedelta(days=5 - round_idx),
            source=EventSource.MANUAL,
            metadata={"round": round_idx},
        )
        apps[0].events.append(ev_int)
        store.append_event(ev_int)
    apps[0].current_status = ApplicationLifecycleStatus.INTERVIEW
    store.save_application(apps[0])

    ev_int1 = ApplicationEvent(
        event_id="evt-intv-1",
        application_id=apps[1].application_id,
        job_id=apps[1].job_id,
        event_type=ApplicationLifecycleStatus.INTERVIEW,
        timestamp=now - timedelta(days=4),
        source=EventSource.MANUAL,
    )
    apps[1].events.append(ev_int1)
    apps[1].current_status = ApplicationLifecycleStatus.INTERVIEW
    store.save_application(apps[1])
    store.append_event(ev_int1)

    # 7. 1 Offer (app 0)
    ev_off = ApplicationEvent(
        event_id="evt-off-0",
        application_id=apps[0].application_id,
        job_id=apps[0].job_id,
        event_type=ApplicationLifecycleStatus.OFFER,
        timestamp=now - timedelta(days=2),
        source=EventSource.EMAIL,
    )
    apps[0].events.append(ev_off)
    apps[0].current_status = ApplicationLifecycleStatus.OFFER
    store.save_application(apps[0])
    store.append_event(ev_off)

    # 8. 1 Accepted (app 0)
    ev_acc = ApplicationEvent(
        event_id="evt-acc-0",
        application_id=apps[0].application_id,
        job_id=apps[0].job_id,
        event_type=ApplicationLifecycleStatus.ACCEPTED,
        timestamp=now - timedelta(days=1),
        source=EventSource.MANUAL,
    )
    apps[0].events.append(ev_acc)
    apps[0].current_status = ApplicationLifecycleStatus.ACCEPTED
    store.save_application(apps[0])
    store.append_event(ev_acc)

    # --- VERIFY FUNNEL COUNTS ---
    funnel = tracking.get_funnel()
    assert funnel.discovered == 10, f"Expected 10 discovered, got {funnel.discovered}"
    assert funnel.recommended == 7, f"Expected 7 recommended, got {funnel.recommended}"
    assert funnel.prepared == 5, f"Expected 5 prepared, got {funnel.prepared}"
    assert funnel.submitted == 4, f"Expected 4 submitted, got {funnel.submitted}"
    assert funnel.recruiter_responses == 2, f"Expected 2 recruiter responses, got {funnel.recruiter_responses}"
    assert funnel.interviews == 2, f"Expected 2 unique interviews (no dupes), got {funnel.interviews}"
    assert funnel.offers == 1, f"Expected 1 offer, got {funnel.offers}"
    assert funnel.accepted == 1, f"Expected 1 accepted, got {funnel.accepted}"
    assert funnel.rejected == 1, f"Expected 1 rejected, got {funnel.rejected}"

    # --- VERIFY CONVERSION FORMULAS AND DENOMINATORS ---
    conv = tracking.get_conversion()
    # application_rate = submitted (4) / discovered (10) = 40.0%
    assert conv.application_rate == 40.0, f"Expected 40.0%, got {conv.application_rate}"
    # response_rate = recruiter_responses (2) / submitted (4) = 50.0%
    assert conv.response_rate == 50.0, f"Expected 50.0%, got {conv.response_rate}"
    # interview_rate = interviews (2) / submitted (4) = 50.0%
    assert conv.interview_rate == 50.0, f"Expected 50.0%, got {conv.interview_rate}"
    # offer_rate = offers (1) / submitted (4) = 25.0%
    assert conv.offer_rate == 25.0, f"Expected 25.0%, got {conv.offer_rate}"
    # acceptance_rate = accepted (1) / offers (1) = 100.0%
    assert conv.acceptance_rate == 100.0, f"Expected 100.0%, got {conv.acceptance_rate}"

    # --- VERIFY PARTIAL FUNNEL STATES REMAIN ACCURATE ---
    # App 9: Discovered-but-not-recommended
    app9 = tracking.get_application(apps[9].application_id)
    assert app9.current_status == ApplicationLifecycleStatus.DISCOVERED
    assert app9.recommended_at is None

    # App 5: Recommended-but-not-prepared
    app5 = tracking.get_application(apps[5].application_id)
    assert app5.current_status == ApplicationLifecycleStatus.RECOMMENDED
    assert app5.prepared_at is None

    # App 4: Prepared-but-not-submitted
    app4 = tracking.get_application(apps[4].application_id)
    assert app4.current_status == ApplicationLifecycleStatus.PREPARED
    assert app4.submitted_at is None

    # App 3: Submitted-but-rejected
    app3_fetched = tracking.get_application(apps[3].application_id)
    assert app3_fetched.current_status == ApplicationLifecycleStatus.REJECTED
    assert app3_fetched.submitted_at is not None
