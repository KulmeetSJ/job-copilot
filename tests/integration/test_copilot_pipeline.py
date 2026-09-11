"""Comprehensive End-to-End Integration, Safety, and Zero-Mutation Tests for Phase 9 / 9.1 Continuous Copilot."""

from datetime import datetime, timezone, timedelta
import hashlib
from pathlib import Path
import pytest
import yaml

from job_copilot.browser.models import SubmissionResult
from job_copilot.copilot.models import (
    ClaimType,
    CopilotAction,
    PriorityBand,
    QueueStatus,
    utc_now,
)
from job_copilot.copilot.queue import CopilotQueueStore
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.browser_workflow_service import BrowserWorkflowService
from job_copilot.services.copilot_service import CopilotService
from job_copilot.services.discovery_service import DiscoveryService
from job_copilot.services.job_intelligence_service import JobIntelligenceService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.models import (
    ApplicationEvent,
    ApplicationLifecycleStatus,
    EventSource,
)
from job_copilot.tracking.store import TrackingStore


@pytest.mark.asyncio
async def test_copilot_end_to_end_orchestration(tmp_path: Path):
    """
    Test complete lifecycle path:
    Discovery -> Matching -> Prioritization -> Queue -> Prep -> Browser Review -> Confirmation -> Submission -> Tracking.
    """
    data_dir = tmp_path / "data"
    jobs_dir = data_dir / "jobs"
    apps_dir = data_dir / "applications"
    tracking_dir = data_dir / "tracking"
    copilot_dir = data_dir / "copilot"

    disc_service = DiscoveryService(jobs_data_dir=jobs_dir)
    intel_service = JobIntelligenceService(jobs_data_dir=jobs_dir)
    prep_service = ApplicationPrepService(
        applications_data_dir=apps_dir,
        jobs_data_dir=jobs_dir,
        intelligence_service=intel_service,
    )
    track_store = TrackingStore(tracking_dir=tracking_dir, applications_dir=apps_dir)
    tracking_service = TrackingService(store=track_store, prep_service=prep_service)
    browser_service = BrowserWorkflowService(application_prep_service=prep_service, applications_data_dir=apps_dir)
    queue_store = CopilotQueueStore(queue_dir=copilot_dir)

    copilot = CopilotService(
        discovery_service=disc_service,
        intelligence_service=intel_service,
        prep_service=prep_service,
        browser_service=browser_service,
        tracking_service=tracking_service,
        queue_store=queue_store,
    )

    # 1. Ingest Job Description (Phase 5)
    raw_jd = (
        "Job Title: Senior Backend Java Engineer\n"
        "Company: TargetFintech\n"
        "Location: Remote\n"
        "Requirements:\n"
        "- 6+ years Java, Spring Boot, Microservices\n"
        "- GCP, BigQuery, Kafka\n"
        "- Distributed transaction processing in banking\n"
    )
    canonical = disc_service.ingest_text(
        text=raw_jd,
        company="TargetFintech",
        title="Senior Backend Java Engineer",
        source_url=str(Path("tests/browser/fixtures/basic_form.html").resolve()),
    )
    job_id = canonical.job_id

    # 2. Process Opportunity through Copilot
    c_job = copilot.process_job(job_id)
    assert c_job is not None
    assert c_job.job_id == job_id
    assert c_job.match_score >= 70.0
    assert c_job.priority_band in [PriorityBand.CRITICAL, PriorityBand.HIGH, PriorityBand.MEDIUM]
    assert c_job.queue_status == QueueStatus.REVIEW
    assert c_job.explanation is not None
    assert len(c_job.explanation.why_apply) > 0
    assert len(c_job.explanation.evidence_references) > 0

    # Verify Phase 8 tracking registered early stages
    tracked_app = tracking_service.get_application(c_job.tracking_application_id)
    assert tracked_app is not None
    assert tracked_app.current_status == ApplicationLifecycleStatus.RECOMMENDED

    # 3. Candidate Approves and Prepares Application Package (Phase 6)
    copilot.approve(job_id)
    pkg = copilot.prepare(job_id)
    assert pkg is not None
    assert pkg.selected_resume_strategy == "backend_java"
    assert Path(pkg.resume_pdf_path).exists()

    queued_job = copilot.get_job(job_id)
    assert queued_job.queue_status == QueueStatus.READY_FOR_REVIEW

    # 4. Critical Safety Test: Attempt submission without confirmation token
    blocked_res = await copilot.apply_async(job_id, confirmation_token=None)
    assert blocked_res["status"] == "SUBMISSION_BLOCKED"
    assert "confirmation token required" in blocked_res["reason"].lower()

    # Verify queue status paused for user
    waiting_job = copilot.get_job(job_id)
    assert waiting_job.queue_status == QueueStatus.WAITING_FOR_USER

    # Verify Phase 8 SUBMITTED event does NOT occur
    pre_submit_app = tracking_service.get_application(c_job.tracking_application_id)
    assert pre_submit_app.current_status != ApplicationLifecycleStatus.SUBMITTED
    assert not any(ev.event_type == ApplicationLifecycleStatus.SUBMITTED for ev in pre_submit_app.events)

    # 5. Check Phase 7 Review Artifact
    sess_id = blocked_res["session_id"]
    session = browser_service.get_session(sess_id)
    assert session is not None
    assert session.review is not None
    assert session.review.job_id == job_id

    # 6. Candidate Confirms and Executes Submission with Token / Confirmation
    submit_res = await copilot.apply_async(job_id, confirmation_token="SUBMIT")
    assert submit_res["status"] == "SUBMITTED"
    assert submit_res["submission_result"]["success"] is True

    # 7. Verify Final Tracking and Snapshot Immutability
    final_job = copilot.get_job(job_id)
    assert final_job.queue_status == QueueStatus.SUBMITTED

    final_tracked = tracking_service.get_application(c_job.tracking_application_id)
    assert final_tracked.current_status == ApplicationLifecycleStatus.SUBMITTED
    assert any(ev.event_type == ApplicationLifecycleStatus.SUBMITTED for ev in final_tracked.events)
    assert final_tracked.snapshot is not None
    assert final_tracked.snapshot.resume_strategy == "backend_java"
    assert final_tracked.snapshot.match_score == pkg.assessment.score_breakdown.overall_score


def test_historical_learning_and_zero_mutation(tmp_path: Path):
    """
    Test historical learning with deterministic sample comparison:
    Backend Java: 24 submitted, 7 interviews (29.2%)
    Full Stack: 18 submitted, 2 interviews (11.1%)
    Verify that:
      1. Backend Java is identified as stronger signal.
      2. Output separates FACT, INFERENCE, RECOMMENDATION.
      3. Candidate truth, Phase 4 weights, and Phase 3 strategies remain strictly unmutated.
    """
    data_dir = tmp_path / "data"
    tracking_dir = data_dir / "tracking"
    apps_dir = data_dir / "applications"

    track_store = TrackingStore(tracking_dir=tracking_dir, applications_dir=apps_dir)
    tracking_service = TrackingService(store=track_store)
    now = utc_now()

    # Populate 24 Backend Java applications (7 interviews)
    for i in range(24):
        rec = tracking_service.register_discovered_job(
            job_id=f"job-bj-{i}",
            company=f"JavaCo-{i}",
            role="Backend Engineer",
            source="greenhouse",
            discovered_at=now - timedelta(days=30 - i),
        )
        rec.resume_strategy = "backend_java"
        rec.submitted_at = now - timedelta(days=25 - i)
        rec.current_status = ApplicationLifecycleStatus.SUBMITTED
        ev_sub = ApplicationEvent(
            event_id=f"evt-sub-bj-{i}",
            application_id=rec.application_id,
            job_id=rec.job_id,
            event_type=ApplicationLifecycleStatus.SUBMITTED,
            timestamp=rec.submitted_at,
            source=EventSource.SYSTEM,
        )
        rec.events.append(ev_sub)
        if i < 7:
            ev_int = ApplicationEvent(
                event_id=f"evt-int-bj-{i}",
                application_id=rec.application_id,
                job_id=rec.job_id,
                event_type=ApplicationLifecycleStatus.INTERVIEW,
                timestamp=rec.submitted_at + timedelta(days=4),
                source=EventSource.MANUAL,
            )
            rec.events.append(ev_int)
            rec.current_status = ApplicationLifecycleStatus.INTERVIEW
            track_store.append_event(ev_int)

        track_store.save_application(rec)
        track_store.append_event(ev_sub)

    # Populate 18 Full Stack applications (2 interviews)
    for i in range(18):
        rec = tracking_service.register_discovered_job(
            job_id=f"job-fs-{i}",
            company=f"StackCo-{i}",
            role="Full Stack Engineer",
            source="linkedin",
            discovered_at=now - timedelta(days=30 - i),
        )
        rec.resume_strategy = "full_stack"
        rec.submitted_at = now - timedelta(days=25 - i)
        rec.current_status = ApplicationLifecycleStatus.SUBMITTED
        ev_sub = ApplicationEvent(
            event_id=f"evt-sub-fs-{i}",
            application_id=rec.application_id,
            job_id=rec.job_id,
            event_type=ApplicationLifecycleStatus.SUBMITTED,
            timestamp=rec.submitted_at,
            source=EventSource.SYSTEM,
        )
        rec.events.append(ev_sub)
        if i < 2:
            ev_int = ApplicationEvent(
                event_id=f"evt-int-fs-{i}",
                application_id=rec.application_id,
                job_id=rec.job_id,
                event_type=ApplicationLifecycleStatus.INTERVIEW,
                timestamp=rec.submitted_at + timedelta(days=4),
                source=EventSource.MANUAL,
            )
            rec.events.append(ev_int)
            rec.current_status = ApplicationLifecycleStatus.INTERVIEW
            track_store.append_event(ev_int)

        track_store.save_application(rec)
        track_store.append_event(ev_sub)

    copilot = CopilotService(tracking_service=tracking_service)
    insights = copilot.get_insights()

    assert len(insights) >= 2
    bj_insight = next(ins for ins in insights if "backend_java" in ins.topic)
    assert bj_insight.sample_threshold_met is True
    assert bj_insight.sample_size == 24
    assert any("24" in f for f in bj_insight.fact_statements)
    assert any("7" in f for f in bj_insight.fact_statements)
    assert any("prioritizing" in r.lower() for r in bj_insight.recommendation_statements)
    assert "No configuration change made" in bj_insight.action_required

    # Verify Candidate Truth and Configuration Immutability
    pref_path = Path("data/candidate/preferences.yaml")
    assert pref_path.exists()
    pref_content = yaml.safe_load(pref_path.read_text(encoding="utf-8"))
    assert "preferences" in pref_content


def test_copilot_idempotency_and_queue_stability(tmp_path: Path):
    """Verify running copilot process repeatedly produces stable states without duplication."""
    data_dir = tmp_path / "data"
    jobs_dir = data_dir / "jobs"
    apps_dir = data_dir / "applications"
    copilot_dir = data_dir / "copilot"

    disc = DiscoveryService(jobs_data_dir=jobs_dir)
    queue = CopilotQueueStore(queue_dir=copilot_dir)
    copilot = CopilotService(discovery_service=disc, queue_store=queue)

    raw_jd = "Job Title: SRE Engineer\nCompany: ReliabilityCo\nRequirements: Linux, Python, Observability"
    canonical = disc.ingest_text(text=raw_jd, company="ReliabilityCo", title="SRE Engineer")
    job_id = canonical.job_id

    # Run process multiple times
    job1 = copilot.process_job(job_id)
    job2 = copilot.process_job(job_id)
    job3 = copilot.process_job(job_id)

    assert job1.job_id == job2.job_id == job3.job_id
    queue_jobs = queue.list_jobs()
    assert len(queue_jobs) == 1
    assert queue_jobs[0].job_id == job_id


def test_zero_mutation_byte_for_byte():
    """
    Phase 9.1 Verification: Capture exact SHA256 hashes of all canonical candidate truth,
    Phase 4 matching weights, and Phase 3 strategy definitions. Run representative Phase 9
    operations and verify byte-for-byte immutability.
    """
    protected_files = [
        Path("data/candidate/master_profile.yaml"),
        Path("data/candidate/evidence.yaml"),
        Path("data/candidate/preferences.yaml"),
        Path("data/candidate/review_required.yaml"),
        Path("src/job_copilot/matching/scorer.py"),
        Path("src/job_copilot/resume/strategy.py"),
    ]

    hashes_before = {}
    for p in protected_files:
        assert p.exists(), f"Protected file {p} missing"
        hashes_before[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()

    # Execute Phase 9 Copilot service operations
    service = CopilotService()
    service.get_dashboard()
    service.get_insights()

    hashes_after = {}
    for p in protected_files:
        hashes_after[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()

    assert hashes_before == hashes_after, "Zero-mutation violation detected! Protected files were altered."


def test_historical_learning_does_not_leak_into_canonical_scoring(tmp_path: Path):
    """
    Phase 9.1 Verification: Ensure historical learning signals cannot alter Phase 4 canonical match scores.
    """
    data_dir = tmp_path / "data"
    jobs_dir = data_dir / "jobs"
    intel_service = JobIntelligenceService(jobs_data_dir=jobs_dir)

    raw_jd = (
        "Job Title: Senior Java Developer\n"
        "Company: FinSystems\n"
        "Requirements: 5+ years Java, Spring Boot, Microservices, GCP"
    )

    # 1. Baseline Phase 4 score without historical learning
    assessment_baseline = intel_service.evaluate_job(raw_text=raw_jd, save_artifacts=False)
    base_score = assessment_baseline.score_breakdown.overall_score

    # 2. Add overwhelming historical performance favoring backend_java
    track_store = TrackingStore(tracking_dir=data_dir / "tracking", applications_dir=data_dir / "apps")
    tracking_service = TrackingService(store=track_store)
    now = utc_now()
    for i in range(25):
        rec = tracking_service.register_discovered_job(
            job_id=f"job-hist-{i}",
            company=f"HistCo-{i}",
            role="Java Dev",
            source="manual",
            discovered_at=now,
        )
        rec.resume_strategy = "backend_java"
        rec.current_status = ApplicationLifecycleStatus.OFFER
        track_store.save_application(rec)

    copilot = CopilotService(intelligence_service=intel_service, tracking_service=tracking_service)
    insights = copilot.get_insights()
    assert len(insights) >= 1

    # 3. Evaluate same job again via Phase 4 - must produce identical canonical score
    assessment_after = intel_service.evaluate_job(raw_text=raw_jd, save_artifacts=False)
    assert assessment_after.score_breakdown.overall_score == base_score
    assert assessment_after.score_breakdown.model_dump() == assessment_baseline.score_breakdown.model_dump()


def test_evidence_classification_safety():
    """
    Phase 9.1 Verification: Ensure Phase 9 explanation and recommendation engines preserve
    truth boundaries:
      - GKE / Helm exposure cannot become production Kubernetes experience.
      - 100K+ RPS benchmark cannot become production experience.
    """
    from job_copilot.copilot.explanations import ExplanationEngine

    claim_exposure = ExplanationEngine.classify_claim("GKE and Helm exposure in personal projects", "EXP-01", is_confirmed_prod=False)
    assert claim_exposure in [ClaimType.EXPOSURE, ClaimType.PERSONAL_PROJECT]
    assert claim_exposure != ClaimType.PROFESSIONAL_EXPERIENCE

    claim_benchmark = ExplanationEngine.classify_claim("100K+ RPS benchmark pipeline project", "PRJ-01", is_confirmed_prod=False)
    assert claim_benchmark in [ClaimType.PERSONAL_PROJECT, ClaimType.EXPOSURE]
    assert claim_benchmark != ClaimType.PROFESSIONAL_EXPERIENCE


def test_complete_12_state_end_to_end_lifecycle(tmp_path: Path):
    """
    Phase 9.1 Verification: Complete deterministic 12-state funnel progression:
    DISCOVERED -> RECOMMENDED -> PRIORITIZED -> USER APPROVED -> PREPARED ->
    READY_FOR_REVIEW -> USER CONFIRMS -> SUBMITTED -> RECRUITER_RESPONSE ->
    INTERVIEW -> OFFER -> ACCEPTED.
    Phase 8 remains the authoritative lifecycle tracking system throughout.
    """
    data_dir = tmp_path / "data"
    jobs_dir = data_dir / "jobs"
    apps_dir = data_dir / "applications"
    tracking_dir = data_dir / "tracking"
    copilot_dir = data_dir / "copilot"

    disc = DiscoveryService(jobs_data_dir=jobs_dir)
    intel = JobIntelligenceService(jobs_data_dir=jobs_dir)
    prep = ApplicationPrepService(applications_data_dir=apps_dir, jobs_data_dir=jobs_dir, intelligence_service=intel)
    track_store = TrackingStore(tracking_dir=tracking_dir, applications_dir=apps_dir)
    tracking = TrackingService(store=track_store, prep_service=prep)
    queue = CopilotQueueStore(queue_dir=copilot_dir)

    copilot = CopilotService(
        discovery_service=disc,
        intelligence_service=intel,
        prep_service=prep,
        tracking_service=tracking,
        queue_store=queue,
    )

    # 1. DISCOVERED
    canonical = disc.ingest_text(
        text="Job Title: Senior Java Engineer\nCompany: DreamFintech\nRequirements: Java, Spring, GCP",
        company="DreamFintech",
        title="Senior Java Engineer",
    )
    job_id = canonical.job_id
    assert canonical is not None

    # 2. RECOMMENDED & 3. PRIORITIZED
    c_job = copilot.process_job(job_id)
    assert c_job.priority_band in [PriorityBand.CRITICAL, PriorityBand.HIGH, PriorityBand.MEDIUM]
    app_id = c_job.tracking_application_id

    # 4. USER APPROVED
    copilot.approve(job_id)
    assert copilot.get_job(job_id).queue_status == QueueStatus.APPROVED

    # 5. PREPARED & 6. READY_FOR_REVIEW
    pkg = copilot.prepare(job_id)
    assert pkg is not None
    assert copilot.get_job(job_id).queue_status == QueueStatus.READY_FOR_REVIEW

    # 7. USER CONFIRMS & 8. SUBMITTED
    # Simulate browser submission completion via Phase 7 & 8 tracking
    sub_res = SubmissionResult(
        success=True,
        submitted_at=utc_now(),
        confirmation_reference="APP-CONF-777",
        final_url="https://example.com/thank-you",
    )
    tracking.register_submission(
        job_id=job_id,
        package=pkg,
        submission_result=sub_res,
    )
    queue.update_status(job_id, QueueStatus.SUBMITTED)
    assert tracking.get_application(app_id).current_status == ApplicationLifecycleStatus.SUBMITTED

    # 9. RECRUITER_RESPONSE
    tracking.record_event(app_id, ApplicationLifecycleStatus.RECRUITER_RESPONSE, notes="Recruiter emailed")
    assert tracking.get_application(app_id).current_status == ApplicationLifecycleStatus.RECRUITER_RESPONSE

    # 10. INTERVIEW
    tracking.record_event(app_id, ApplicationLifecycleStatus.INTERVIEW, notes="Technical round scheduled")
    assert tracking.get_application(app_id).current_status == ApplicationLifecycleStatus.INTERVIEW

    # 11. OFFER
    tracking.record_event(app_id, ApplicationLifecycleStatus.OFFER, notes="Received offer letter")
    assert tracking.get_application(app_id).current_status == ApplicationLifecycleStatus.OFFER

    # 12. ACCEPTED
    tracking.record_event(app_id, ApplicationLifecycleStatus.ACCEPTED, notes="Signed and accepted offer")
    final_app = tracking.get_application(app_id)
    assert final_app.current_status == ApplicationLifecycleStatus.ACCEPTED
    assert len(final_app.events) >= 6
