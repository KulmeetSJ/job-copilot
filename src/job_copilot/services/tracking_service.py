"""Service layer for Phase 8 Application Tracking and Outcome Analytics."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from job_copilot.application.models import ApplicationPackage
from job_copilot.browser.models import BrowserSession, SubmissionResult
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.tracking.analytics import AnalyticsEngine
from job_copilot.tracking.lifecycle import LifecycleValidator
from job_copilot.tracking.models import (
    AnalyticsDashboard,
    ApplicationEvent,
    ApplicationLifecycleStatus,
    ApplicationRecord,
    ApplicationSnapshot,
    CohortMetric,
    ConversionRates,
    EventSource,
    FunnelMetrics,
    ResponseTimeMetrics,
    utc_now,
)
from job_copilot.tracking.store import TrackingStore
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class TrackingService:
    """
    Central orchestrator for immutable application lifecycle event logging,
    frozen submission snapshots, manual status updates, and outcome analytics.
    """

    def __init__(
        self,
        store: Optional[TrackingStore] = None,
        prep_service: Optional[ApplicationPrepService] = None,
        tracking_dir: Optional[Path] = None,
        applications_dir: Optional[Path] = None,
    ):
        self.store = store or TrackingStore(
            tracking_dir=tracking_dir,
            applications_dir=applications_dir,
        )
        self.prep_service = prep_service or ApplicationPrepService()

    def register_discovered_job(
        self,
        job_id: str,
        company: str,
        role: str,
        source: str = "unknown",
        canonical_url: Optional[str] = None,
        discovered_at: Optional[datetime] = None,
    ) -> ApplicationRecord:
        """
        Register a newly discovered job (Phase 5) into tracking with DISCOVERED status.
        """
        existing_app = self.store.get_application_by_job_id(job_id)
        if existing_app:
            return existing_app

        now = discovered_at or utc_now()
        app_id = f"app-{uuid.uuid4().hex[:8]}"

        event = ApplicationEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            application_id=app_id,
            job_id=job_id,
            event_type=ApplicationLifecycleStatus.DISCOVERED,
            timestamp=now,
            source=EventSource.SYSTEM,
            notes=f"Job discovered via {source}",
            metadata={"source": source, "canonical_url": canonical_url},
        )

        record = ApplicationRecord(
            application_id=app_id,
            job_id=job_id,
            company=company,
            role=role,
            canonical_job_url=canonical_url,
            source=source,
            discovered_at=now,
            current_status=ApplicationLifecycleStatus.DISCOVERED,
            current_status_at=now,
            events=[event],
            created_at=now,
            updated_at=now,
        )

        self.store.save_application(record)
        self.store.append_event(event)
        return record

    def register_recommendation(
        self,
        job_id: str,
        assessment: Any,
    ) -> ApplicationRecord:
        """
        Record recommendation outcome (Phase 4) into tracking.
        Reuses Phase 4 assessment without re-scoring.
        """
        app = self.store.get_application_by_job_id(job_id)
        now = getattr(assessment, "assessment_date", None) or utc_now()

        # Extract scores safely
        match_score = 0.0
        recommendation = "UNKNOWN"
        strategy = getattr(assessment, "recommended_strategy", "backend_java")
        breakdown_dict = {}

        if hasattr(assessment, "recommendation"):
            rec_val = assessment.recommendation
            recommendation = rec_val.value if hasattr(rec_val, "value") else str(rec_val)

        if hasattr(assessment, "score_breakdown") and assessment.score_breakdown:
            sb = assessment.score_breakdown
            match_score = sb.overall_score
            breakdown_dict = {
                "overall_score": sb.overall_score,
                "technical_score": sb.technical_score,
                "responsibility_score": sb.responsibility_score,
                "role_score": sb.role_score,
                "experience_score": sb.experience_score,
                "domain_score": sb.domain_score,
                "preference_score": sb.preference_score,
                "credential_score": sb.credential_score,
            }

        company = assessment.job.company if (hasattr(assessment, "job") and assessment.job and assessment.job.company) else "Company unavailable"
        role = assessment.job.title if (hasattr(assessment, "job") and assessment.job and assessment.job.title) else "Role unavailable"
        source = assessment.job.source if (hasattr(assessment, "job") and assessment.job and assessment.job.source) else "Source unavailable"
        url = assessment.job.source_url if (hasattr(assessment, "job") and assessment.job) else None

        if not app:
            app_id = f"app-{uuid.uuid4().hex[:8]}"
            disc_event = ApplicationEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                application_id=app_id,
                job_id=job_id,
                event_type=ApplicationLifecycleStatus.DISCOVERED,
                timestamp=now,
                source=EventSource.SYSTEM,
                notes="Job ingested during evaluation",
            )
            rec_event = ApplicationEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                application_id=app_id,
                job_id=job_id,
                event_type=ApplicationLifecycleStatus.RECOMMENDED,
                timestamp=now,
                source=EventSource.SYSTEM,
                notes=f"Recommended tier: {recommendation} (Match score: {match_score:.1f}, Strategy: {strategy})",
                metadata={"match_score": match_score, "recommendation": recommendation, "strategy": strategy, "score_breakdown": breakdown_dict},
            )
            app = ApplicationRecord(
                application_id=app_id,
                job_id=job_id,
                company=company,
                role=role,
                canonical_job_url=url,
                source=source,
                discovered_at=now,
                recommended_at=now,
                current_status=ApplicationLifecycleStatus.RECOMMENDED,
                current_status_at=now,
                resume_strategy=strategy,
                match_score=match_score,
                recommendation=recommendation,
                events=[disc_event, rec_event],
                created_at=now,
                updated_at=now,
            )
            self.store.save_application(app)
            self.store.append_event(disc_event)
            self.store.append_event(rec_event)
            return app

        # If app exists, record recommendation event
        rec_event = ApplicationEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            application_id=app.application_id,
            job_id=job_id,
            event_type=ApplicationLifecycleStatus.RECOMMENDED,
            timestamp=now,
            source=EventSource.SYSTEM,
            notes=f"Recommended tier: {recommendation} (Match score: {match_score:.1f}, Strategy: {strategy})",
            metadata={"match_score": match_score, "recommendation": recommendation, "strategy": strategy, "score_breakdown": breakdown_dict},
        )
        app.recommended_at = now
        app.match_score = match_score
        app.recommendation = recommendation
        app.resume_strategy = strategy
        app.events.append(rec_event)
        # Advance status if currently DISCOVERED
        if app.current_status == ApplicationLifecycleStatus.DISCOVERED:
            app.current_status = ApplicationLifecycleStatus.RECOMMENDED
            app.current_status_at = now
        app.updated_at = utc_now()

        self.store.save_application(app)
        self.store.append_event(rec_event)
        return app

    def register_prepared_application(
        self,
        package: ApplicationPackage,
    ) -> ApplicationRecord:
        """
        Record application preparation (Phase 6) into tracking.
        Reuses Phase 6 application package references without duplicating storage.
        """
        job_id = package.job_id
        app = self.store.get_application_by_job_id(job_id)
        now = getattr(package, "created_at", None) or utc_now()
        package_path = str(Path(self.prep_service.applications_data_dir) / job_id)

        prep_event = ApplicationEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            application_id=app.application_id if app else f"app-{uuid.uuid4().hex[:8]}",
            job_id=job_id,
            event_type=ApplicationLifecycleStatus.PREPARED,
            timestamp=now,
            source=EventSource.SYSTEM,
            notes=f"Application prepared with strategy '{package.selected_resume_strategy}' (Status: {package.status.value}).",
            metadata={
                "strategy": package.selected_resume_strategy,
                "package_path": package_path,
                "resume_pdf_path": package.resume_pdf_path,
                "user_inputs_required": len(package.user_inputs_required),
            },
        )

        if not app:
            app_id = prep_event.application_id
            disc_event = ApplicationEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                application_id=app_id,
                job_id=job_id,
                event_type=ApplicationLifecycleStatus.DISCOVERED,
                timestamp=now,
                source=EventSource.SYSTEM,
                notes="Job discovered during preparation",
            )
            match_score = package.assessment.score_breakdown.overall_score if (package.assessment and package.assessment.score_breakdown) else 0.0
            rec_val = package.assessment.recommendation.value if (package.assessment and package.assessment.recommendation) else "UNKNOWN"

            app = ApplicationRecord(
                application_id=app_id,
                job_id=job_id,
                company=package.company,
                role=package.job_title,
                source=package.assessment.job.source if (package.assessment and package.assessment.job) else "unknown",
                discovered_at=now,
                recommended_at=now,
                prepared_at=now,
                current_status=ApplicationLifecycleStatus.PREPARED,
                current_status_at=now,
                resume_strategy=package.selected_resume_strategy,
                match_score=match_score,
                recommendation=rec_val,
                package_path=package_path,
                events=[disc_event, prep_event],
                created_at=now,
                updated_at=now,
            )
            self.store.save_application(app)
            self.store.append_event(disc_event)
            self.store.append_event(prep_event)
            return app

        # Update existing app
        prep_event.application_id = app.application_id
        app.prepared_at = now
        app.package_path = package_path
        app.resume_strategy = package.selected_resume_strategy
        app.events.append(prep_event)
        if app.current_status in [ApplicationLifecycleStatus.DISCOVERED, ApplicationLifecycleStatus.RECOMMENDED]:
            app.current_status = ApplicationLifecycleStatus.PREPARED
            app.current_status_at = now
        app.updated_at = utc_now()

        self.store.save_application(app)
        self.store.append_event(prep_event)
        return app

    def register_ready_for_review(
        self,
        job_id: str,
        browser_session_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ApplicationRecord:
        """
        Record application readiness for human review (Phase 6/7) into tracking.
        """
        app = self.store.get_application_by_job_id(job_id)
        if not app:
            raise ValueError(f"Application for job '{job_id}' not found.")

        now = utc_now()
        event = ApplicationEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            application_id=app.application_id,
            job_id=job_id,
            event_type=ApplicationLifecycleStatus.READY_FOR_REVIEW,
            timestamp=now,
            source=EventSource.SYSTEM,
            notes=notes or f"Application form filled and ready for human review (Session: {browser_session_id or 'N/A'}).",
            metadata={"browser_session_id": browser_session_id},
        )

        if browser_session_id:
            app.browser_session_id = browser_session_id
        app.events.append(event)
        if app.current_status in [ApplicationLifecycleStatus.DISCOVERED, ApplicationLifecycleStatus.RECOMMENDED, ApplicationLifecycleStatus.PREPARED]:
            app.current_status = ApplicationLifecycleStatus.READY_FOR_REVIEW
            app.current_status_at = now
        app.updated_at = now

        self.store.save_application(app)
        self.store.append_event(event)
        return app

    def register_submission(
        self,
        job_id: str,
        package: Optional[ApplicationPackage] = None,
        browser_session: Optional[BrowserSession] = None,
        submission_result: Optional[SubmissionResult] = None,
    ) -> ApplicationRecord:
        """
        Create or update tracked ApplicationRecord, freeze immutable historical snapshot,
        and append the SUBMITTED event upon successful browser submission.
        """
        # Load package if omitted (read-only from disk, never synchronously regenerate)
        if not package:
            package = self.prep_service.get_application_package(job_id)

        # Check existing record
        app = self.store.get_application_by_job_id(job_id)
        if app and app.submitted_at and app.current_status == ApplicationLifecycleStatus.SUBMITTED:
            logger.warning(f"Application for job '{job_id}' is already registered as submitted.")
            return app

        now = utc_now()
        app_id = app.application_id if app else f"app-{uuid.uuid4().hex[:8]}"

        # Extract scores and assessment breakdown safely
        match_score = 0.0
        recommendation = "UNKNOWN"
        strategy = package.selected_resume_strategy if package else (app.resume_strategy if app else "backend_java")
        tech_m = resp_m = sen_m = prof_m = dom_m = pref_m = cred_m = 0.0

        if package and package.assessment:
            recommendation = package.assessment.recommendation.value
            if package.assessment.score_breakdown:
                sb = package.assessment.score_breakdown
                match_score = sb.overall_score
                tech_m = sb.technical_score
                resp_m = sb.responsibility_score
                sen_m = sb.role_score
                prof_m = sb.experience_score
                dom_m = sb.domain_score
                pref_m = sb.preference_score
                cred_m = sb.credential_score
        elif app:
            match_score = app.match_score or 0.0
            recommendation = app.recommendation or "UNKNOWN"

        # 1. Freeze Historical Snapshot (Immutable)
        # If snapshot already exists, preserve it without mutation
        snapshot = app.snapshot if (app and app.snapshot) else ApplicationSnapshot(
            application_id=app_id,
            job_id=job_id,
            timestamp=now,
            resume_strategy=strategy,
            match_score=match_score,
            recommendation=recommendation,
            technical_match=tech_m,
            responsibility_match=resp_m,
            seniority_match=sen_m,
            professional_evidence_match=prof_m,
            domain_match=dom_m,
            preference_match=pref_m,
            credential_match=cred_m,
            job_source=(
                package.assessment.job.source
                if (package and package.assessment and package.assessment.job)
                else (app.source if app else "unknown")
            ),
            resume_pdf_path=package.resume_pdf_path if package else None,
            cover_letter_path=str(Path(self.prep_service.applications_data_dir) / job_id / "cover_letter.md"),
            applied_via="Playwright Browser" if browser_session else "Direct",
        )

        # 2. Events to append
        events_to_add: List[ApplicationEvent] = []

        if not app or not any(e.event_type == ApplicationLifecycleStatus.PREPARED for e in app.events):
            prep_event = ApplicationEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                application_id=app_id,
                job_id=job_id,
                event_type=ApplicationLifecycleStatus.PREPARED,
                timestamp=now,
                source=EventSource.SYSTEM,
                notes=f"Application prepared with strategy '{strategy}'.",
            )
            events_to_add.append(prep_event)

        is_submitted = submission_result.success if submission_result else True
        if is_submitted:
            sub_event = ApplicationEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                application_id=app_id,
                job_id=job_id,
                event_type=ApplicationLifecycleStatus.SUBMITTED,
                timestamp=now,
                source=EventSource.BROWSER if browser_session else EventSource.SYSTEM,
                notes=f"Application successfully submitted. Ref: {submission_result.confirmation_reference if submission_result else 'Direct'}",
                metadata={
                    "confirmation_reference": submission_result.confirmation_reference if submission_result else None,
                    "final_url": submission_result.final_url if submission_result else None,
                },
            )
            events_to_add.append(sub_event)

        if not app:
            app = ApplicationRecord(
                application_id=app_id,
                job_id=job_id,
                company=package.company if (package and package.company) else "Company unavailable",
                role=package.job_title if (package and package.job_title) else "Role unavailable",
                canonical_job_url=browser_session.application_url if browser_session else None,
                source=snapshot.job_source or "Source unavailable",
                discovered_at=now,
                recommended_at=now,
                prepared_at=now,
                submitted_at=now if is_submitted else None,
                current_status=ApplicationLifecycleStatus.SUBMITTED if is_submitted else ApplicationLifecycleStatus.PREPARED,
                current_status_at=now,
                resume_strategy=strategy,
                match_score=match_score,
                recommendation=recommendation,
                package_path=str(Path(self.prep_service.applications_data_dir) / job_id),
                browser_session_id=browser_session.session_id if browser_session else None,
                snapshot=snapshot,
                events=events_to_add,
                created_at=now,
                updated_at=now,
            )
        else:
            app.snapshot = snapshot
            app.package_path = str(Path(self.prep_service.applications_data_dir) / job_id)
            if browser_session:
                app.browser_session_id = browser_session.session_id
                if not app.canonical_job_url:
                    app.canonical_job_url = browser_session.application_url
            if is_submitted:
                app.submitted_at = now
                app.current_status = ApplicationLifecycleStatus.SUBMITTED
                app.current_status_at = now
            app.events.extend(events_to_add)
            app.updated_at = now

        self.store.save_application(app)
        for ev in events_to_add:
            self.store.append_event(ev)

        return app

    def record_event(
        self,
        application_id: str,
        event_type: ApplicationLifecycleStatus,
        source: EventSource = EventSource.MANUAL,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApplicationEvent:
        """
        Append an outcome or lifecycle event to an application's immutable ledger.
        """
        app = self.store.get_application(application_id)
        if not app:
            raise ValueError(f"Application '{application_id}' not found.")

        # Validate lifecycle transition
        is_valid, warning = LifecycleValidator.validate_transition(app.current_status, event_type)
        if not is_valid:
            raise ValueError(f"Invalid lifecycle transition: {warning}")

        if warning:
            logger.warning(f"Lifecycle transition warning for {application_id}: {warning}")

        event = ApplicationEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            application_id=application_id,
            job_id=app.job_id,
            event_type=event_type,
            timestamp=utc_now(),
            source=source,
            notes=notes,
            metadata=metadata or {},
        )

        self.store.append_event(event)

        # Update application current status
        app.events.append(event)
        app.current_status, app.current_status_at = LifecycleValidator.derive_current_status(app.events)
        app.updated_at = utc_now()
        self.store.save_application(app)

        return event

    def add_user_note(self, application_id: str, note: str) -> ApplicationRecord:
        """Add a candidate/user note to an application record."""
        app = self.store.get_application(application_id)
        if not app:
            raise ValueError(f"Application '{application_id}' not found.")

        timestamp_str = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
        app.user_notes.append(f"[{timestamp_str}] {note}")
        app.updated_at = utc_now()
        self.store.save_application(app)
        return app

    def get_application(self, application_id: str) -> Optional[ApplicationRecord]:
        """Fetch application record by ID."""
        return self.store.get_application(application_id)

    def list_applications(
        self,
        status: Optional[ApplicationLifecycleStatus] = None,
        strategy: Optional[str] = None,
        recommendation: Optional[str] = None,
    ) -> List[ApplicationRecord]:
        """List tracked applications with optional filtering."""
        apps = self.store.list_applications()
        if status:
            apps = [a for a in apps if a.current_status == status]
        if strategy:
            apps = [a for a in apps if a.resume_strategy == strategy]
        if recommendation:
            apps = [a for a in apps if a.recommendation == recommendation]
        return apps

    def get_timeline(self, application_id: str) -> List[ApplicationEvent]:
        """Fetch sorted timeline of all events for an application."""
        app = self.store.get_application(application_id)
        if not app:
            raise ValueError(f"Application '{application_id}' not found.")
        return sorted(app.events, key=lambda e: e.timestamp)

    def get_analytics_dashboard(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> AnalyticsDashboard:
        """Assemble complete analytics dashboard metrics."""
        apps = self.store.list_applications()
        events = self.store.get_events()

        if from_date or to_date:
            apps = AnalyticsEngine.filter_by_date(apps, from_date, to_date)
            app_ids = {a.application_id for a in apps}
            events = [e for e in events if e.application_id in app_ids]

        return AnalyticsEngine.build_dashboard(apps, events)

    def get_funnel(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> FunnelMetrics:
        """Calculate funnel metrics."""
        apps = self.store.list_applications()
        events = self.store.get_events()
        if from_date or to_date:
            apps = AnalyticsEngine.filter_by_date(apps, from_date, to_date)
            app_ids = {a.application_id for a in apps}
            events = [e for e in events if e.application_id in app_ids]
        return AnalyticsEngine.compute_funnel(apps, events)

    def get_conversion(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> ConversionRates:
        """Calculate conversion metrics."""
        funnel = self.get_funnel(from_date, to_date)
        return AnalyticsEngine.compute_conversion(funnel)

    def get_strategy_metrics(self) -> List[CohortMetric]:
        """Compute strategy performance breakdown."""
        apps = self.store.list_applications()
        return AnalyticsEngine.compute_cohort_performance(apps, "strategy")

    def get_recommendation_metrics(self) -> List[CohortMetric]:
        """Compute recommendation performance breakdown."""
        apps = self.store.list_applications()
        return AnalyticsEngine.compute_cohort_performance(apps, "recommendation")

    def get_source_metrics(self) -> List[CohortMetric]:
        """Compute discovery source performance breakdown."""
        apps = self.store.list_applications()
        return AnalyticsEngine.compute_cohort_performance(apps, "source")

    def get_response_time_metrics(self) -> List[ResponseTimeMetrics]:
        """Compute milestone response-time metrics."""
        apps = self.store.list_applications()
        return AnalyticsEngine.compute_response_times(apps)
