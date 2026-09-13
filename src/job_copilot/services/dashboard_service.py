"""High-level Dashboard Service coordinating human review, queue, match evidence, and control workflows."""

from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import uuid
from sqlalchemy.orm import Session

from job_copilot.application.models import ApplicationAnswer, ApplicationPackage, UserInputRequest
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import SubmissionSafetyError
from job_copilot.browser_worker.models import HumanConfirmationRequest
from job_copilot.browser_worker.session_manager import AuthenticatedSessionManager
from job_copilot.copilot.models import (
    CopilotJob,
    PriorityBand,
    QueueStatus,
)
from job_copilot.db.database import get_db
from job_copilot.domain.artifact_enums import ArtifactType
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus, RemoteStatus, ResumeStrategy
from job_copilot.domain.featured_jobs import CURATED_FEATURED_JOBS
from job_copilot.ingestion.deduplicator import JobDeduplicator
from job_copilot.ingestion.normalizer import JobNormalizer
from job_copilot.ingestion.sources.url import UrlJobSource
from job_copilot.matching.models import JobAssessment, MatchClassification
from job_copilot.models.application import Application, ApplicationEventModel
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.repositories.device_repository import DeviceRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.schemas.dashboard import (
    AnalyzeOpportunityRequest,
    AnalyzeOpportunityResponse,
    ApplicationDetailResponse,
    ApplicationTimelineEvent,
    ArtifactSummaryItem,
    BrowserMappedFieldItem,
    BrowserReviewSummary,
    DashboardOverviewResponse,
    DashboardQueueItem,
    DashboardQueueResponse,
    ExplanationSection,
    HumanInputAnswerItem,
    HumanInputSubmitRequest,
    JobDetailResponse,
    MatchDimensionScore,
    PipelineCounts,
    PreparedAnswerItem,
    QueueCounts,
    RequirementMatchDetail,
    RetrySubmissionPayload,
    SessionMetadataItem,
    SourceMonitoringItem,
    SubmissionConfirmPayload,
    SubmissionConfirmResponse,
    UserInputRequiredItem,
)
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.artifact_service import ArtifactService
from job_copilot.services.copilot_service import CopilotService
from job_copilot.services.job_intelligence_service import JobIntelligenceService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.models import ApplicationLifecycleStatus, ApplicationRecord
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def normalize_company_display(raw_company: Optional[str]) -> str:
    """
    Sanitize and normalize company name for clean presentation across dashboard views.
    Preserves raw ingestion data in provenance/debug fields while avoiding anomalies.
    """
    if not raw_company:
        return "Company unavailable"
    from job_copilot.ingestion.metadata_extractor import JobMetadataExtractor
    cleaned = JobMetadataExtractor.clean_company_name(raw_company)
    return cleaned or "Company unavailable"


def resolve_canonical_application_state(
    app: Optional[Application] = None,
    browser_task: Optional[BrowserTaskModel] = None,
) -> str:
    """
    Single canonical projection resolver for application lifecycle across all views.
    Ensures that unverified submissions (e.g. historical Mastercard record 'app-usr-2a43a63d')
    are never classified as confirmed SUBMITTED.
    """
    # 1. Historical unverified Mastercard application or explicit task ID
    if (app and app.application_id == "app-usr-2a43a63d") or (browser_task and browser_task.application_id == "app-usr-2a43a63d"):
        return "SUBMISSION_UNVERIFIED"

    # 2. Browser task state takes precedence for active execution
    if browser_task:
        if browser_task.status == BrowserTaskStatus.SUBMISSION_UNVERIFIED:
            return "SUBMISSION_UNVERIFIED"
        if browser_task.status in (
            BrowserTaskStatus.CAPTCHA_REQUIRED,
            BrowserTaskStatus.LOGIN_REQUIRED,
            BrowserTaskStatus.MFA_REQUIRED,
            BrowserTaskStatus.HUMAN_ACTION_REQUIRED,
            BrowserTaskStatus.BLOCKED,
        ):
            return "MANUAL_ACTION_REQUIRED"
        if browser_task.status == BrowserTaskStatus.USER_INPUT_REQUIRED:
            return "WAITING_FOR_USER"
        if browser_task.status == BrowserTaskStatus.READY_FOR_REVIEW:
            return "READY_FOR_REVIEW"
        if browser_task.status == BrowserTaskStatus.SUBMISSION_AUTHORIZED:
            return "SUBMISSION_AUTHORIZED"
        if browser_task.status in (BrowserTaskStatus.SUBMISSION_RUNNING, BrowserTaskStatus.RUNNING):
            return "SUBMISSION_RUNNING"
        if browser_task.status == BrowserTaskStatus.COMPLETED and app and app.status == ApplicationStatus.APPLIED:
            return "SUBMITTED"

    # 3. Application DB status mapping
    if app:
        if app.status == ApplicationStatus.APPLIED:
            if browser_task and browser_task.status == BrowserTaskStatus.COMPLETED:
                return "SUBMITTED"
            return "SUBMISSION_UNVERIFIED"
        if app.status == ApplicationStatus.READY_TO_APPLY:
            return "READY_FOR_REVIEW"
        if app.status == ApplicationStatus.PREPARING:
            return "PREPARED"
        if app.status == ApplicationStatus.SHORTLISTED:
            return "RECOMMENDED"
        if app.status == ApplicationStatus.OA:
            return "ASSESSMENT"
        if app.status == ApplicationStatus.INTERVIEW:
            return "INTERVIEW"
        if app.status == ApplicationStatus.OFFER:
            return "OFFER"
        if app.status == ApplicationStatus.REJECTED:
            return "REJECTED"
        if app.status == ApplicationStatus.WITHDRAWN:
            return "WITHDRAWN"
        return app.status.value

    return "DISCOVERED"


class DashboardService:
    """
    Core orchestrator for Phase 11 Human Review Dashboard & Control Center.
    Reuses existing authoritative services across Phases 1 through 10C without duplicating business logic.
    """

    def __init__(
        self,
        db: Optional[Session] = None,
        copilot_service: Optional[CopilotService] = None,
        tracking_service: Optional[TrackingService] = None,
        prep_service: Optional[ApplicationPrepService] = None,
        intelligence_service: Optional[JobIntelligenceService] = None,
        artifact_service: Optional[ArtifactService] = None,
    ):
        self._db = db
        disc_service = getattr(prep_service, "discovery_service", None) if prep_service else None
        self.copilot_service = copilot_service or CopilotService(
            discovery_service=disc_service,
            intelligence_service=intelligence_service,
            prep_service=prep_service,
            tracking_service=tracking_service,
        )
        orchestrator = getattr(self.copilot_service, "orchestrator", None) if isinstance(self.copilot_service, CopilotService) else None
        self.tracking_service = tracking_service or (getattr(orchestrator, "tracking_service", None) if orchestrator else None) or TrackingService()
        self.prep_service = prep_service or (getattr(orchestrator, "prep_service", None) if orchestrator else None) or ApplicationPrepService()
        self.intelligence_service = intelligence_service or (getattr(orchestrator, "intelligence_service", None) if orchestrator else None) or JobIntelligenceService()
        self.artifact_service = artifact_service or ArtifactService(db=db)

    def _get_db_session(self) -> Tuple[Session, bool]:
        """Resolve database session and ownership flag."""
        if self._db is not None:
            return self._db, False
        gen = get_db()
        return next(gen), True

    def _ensure_curated_job_exists(self, db: Session, identifier: str) -> Optional[Job]:
        """Ensure a curated featured job exists in the DB jobs table and application tracking."""
        if not identifier:
            return None

        target_job_id = identifier
        app_repo = ApplicationRepository(db)
        existing_app = app_repo.get_by_application_id(identifier)
        if existing_app and existing_app.job_id_str:
            target_job_id = existing_app.job_id_str

        curated_key = None
        if target_job_id in CURATED_FEATURED_JOBS:
            curated_key = target_job_id
        else:
            for k, v in CURATED_FEATURED_JOBS.items():
                if v.get("tracking_app_id") == target_job_id or k in target_job_id or target_job_id in k:
                    curated_key = k
                    break

        if not curated_key:
            return None

        job_repo = JobRepository(db)
        db_job = job_repo.get_by_job_id(curated_key)
        job_def = CURATED_FEATURED_JOBS[curated_key]

        if not db_job:
            db_job = Job(
                job_id=curated_key,
                company=job_def["company"],
                title=job_def["title"],
                location=job_def["location"],
                remote_status=job_def["remote_status"],
                source=job_def["source"],
                canonical_url=job_def["canonical_url"],
                url=job_def["canonical_url"],
                description=job_def["description"],
                requirements=job_def["requirements"],
                preferred_qualifications=job_def["preferred_qualifications"],
                technologies=job_def["technologies"],
                years_experience=job_def["years_experience"],
                lifecycle_status="DISCOVERED",
            )
            db.add(db_job)
            db.commit()
            db.refresh(db_job)

        # Ensure canonical job is in discovery store if available
        try:
            if hasattr(self, "copilot_service") and self.copilot_service and hasattr(self.copilot_service, "orchestrator"):
                orch = self.copilot_service.orchestrator
                if hasattr(orch, "discovery_service") and hasattr(orch.discovery_service, "store"):
                    d_store = orch.discovery_service.store
                    if not d_store.get_canonical_job(curated_key):
                        from job_copilot.ingestion.models import CanonicalJob
                        c_job = CanonicalJob(
                            job_id=curated_key,
                            title=job_def["title"],
                            company=job_def["company"],
                            location=job_def["location"],
                            remote_status=job_def["remote_status"],
                            canonical_url=job_def["canonical_url"],
                            source_url=job_def["canonical_url"],
                            source=job_def["source"],
                            raw_description=job_def["description"],
                            requirements=job_def["requirements"],
                            preferred_qualifications=job_def["preferred_qualifications"],
                            technologies=job_def["technologies"],
                            years_experience=job_def["years_experience"],
                        )
                        d_store.save(c_job)
        except Exception:
            pass

        # Ensure Application record exists
        target_app_id = job_def.get("tracking_app_id") or f"app-{curated_key[:16]}"
        app = app_repo.get_by_job_id_str(curated_key) or app_repo.get_by_application_id(target_app_id)
        if not app:
            app = Application(
                application_id=target_app_id,
                job_id=db_job.id,
                job_id_str=curated_key,
                company=job_def["company"],
                role=job_def["title"],
                canonical_job_url=job_def["canonical_url"],
                source=job_def["source"],
                status=ApplicationStatus.DISCOVERED,
                match_score=job_def["match_score"],
                resume_strategy=job_def["strategy"],
            )
            db.add(app)
            db.commit()
            db.refresh(app)

        return db_job

    # ==========================================================================
    # 1. Overview & Metrics
    # ==========================================================================

    def get_overview(self) -> DashboardOverviewResponse:
        """Aggregate high-level metrics, pipeline stages, and active queues using canonical state."""
        db, should_close = self._get_db_session()
        try:
            # 1. Queue counts from CopilotService
            all_jobs = self.copilot_service.get_queue()
            critical_cnt = sum(1 for j in all_jobs if j.priority_band == PriorityBand.CRITICAL and j.queue_status != QueueStatus.ARCHIVED)
            high_cnt = sum(1 for j in all_jobs if j.priority_band == PriorityBand.HIGH and j.queue_status != QueueStatus.ARCHIVED)
            medium_cnt = sum(1 for j in all_jobs if j.priority_band == PriorityBand.MEDIUM and j.queue_status != QueueStatus.ARCHIVED)
            low_cnt = sum(1 for j in all_jobs if j.priority_band == PriorityBand.LOW and j.queue_status != QueueStatus.ARCHIVED)
            active_cnt = sum(1 for j in all_jobs if j.queue_status not in (QueueStatus.ARCHIVED, QueueStatus.SKIPPED))

            queue_counts = QueueCounts(
                critical=critical_cnt,
                high=high_cnt,
                medium=medium_cnt,
                low=low_cnt,
                total_active=active_cnt,
            )

            # 2. Pipeline counts from authoritative DB Applications & BrowserTasks
            app_repo = ApplicationRepository(db)
            tracked_apps = app_repo.list_applications()
            task_repo = BrowserTaskRepository(db)
            
            ready_tasks = task_repo.list_by_status(BrowserTaskStatus.READY_FOR_REVIEW)
            awaiting_confirm_cnt = len(ready_tasks)

            disc_cnt = 0
            rec_cnt = 0
            prep_cnt = 0
            ready_cnt = 0
            manual_action_cnt = 0
            unverified_cnt = 0
            sub_cnt = 0
            recruiter_cnt = 0
            interview_cnt = 0
            offer_cnt = 0
            rejected_cnt = 0
            withdrawn_cnt = 0

            for a in tracked_apps:
                t = task_repo.get_by_application_or_job_id(a.application_id, a.job_id_str)
                c_state = resolve_canonical_application_state(app=a, browser_task=t)
                if c_state == "SUBMISSION_UNVERIFIED":
                    unverified_cnt += 1
                elif c_state == "MANUAL_ACTION_REQUIRED":
                    manual_action_cnt += 1
                elif c_state == "SUBMITTED":
                    sub_cnt += 1
                elif c_state in ("READY_FOR_REVIEW", "READY_TO_APPLY"):
                    ready_cnt += 1
                elif c_state in ("PREPARED", "PREPARING"):
                    prep_cnt += 1
                elif c_state in ("RECOMMENDED", "SHORTLISTED"):
                    rec_cnt += 1
                elif c_state in ("ASSESSMENT", "OA"):
                    recruiter_cnt += 1
                elif c_state == "INTERVIEW":
                    interview_cnt += 1
                elif c_state == "OFFER":
                    offer_cnt += 1
                elif c_state == "REJECTED":
                    rejected_cnt += 1
                elif c_state == "WITHDRAWN":
                    withdrawn_cnt += 1
                else:
                    disc_cnt += 1

            pipeline_counts = PipelineCounts(
                discovered=disc_cnt,
                recommended=rec_cnt,
                prepared=prep_cnt,
                ready_for_review=ready_cnt or awaiting_confirm_cnt,
                manual_action_required=manual_action_cnt,
                submission_unverified=unverified_cnt,
                needs_user_input=awaiting_confirm_cnt,
                awaiting_confirmation=awaiting_confirm_cnt,
                submitted=sub_cnt,
                recruiter_response=recruiter_cnt,
                interview=interview_cnt,
                offer=offer_cnt,
                rejected=rejected_cnt,
                withdrawn=withdrawn_cnt,
            )

            # 3. Source & Session health
            source_reports = self.copilot_service.get_sources_health()
            active_sources = sum(1 for s in source_reports if getattr(s, "enabled", True))
            healthy_sources = sum(1 for s in source_reports if getattr(getattr(s, "state", None), "value", str(getattr(s, "state", ""))) in ("HEALTHY", "ACTIVE"))

            session_mgr = AuthenticatedSessionManager(db=db)
            auth_sessions = session_mgr.list_sessions()
            authenticated_cnt = sum(1 for s in auth_sessions if s.status.value == "ACTIVE")

            # 4. Recent activity (last 10 events) with canonical labeling for unverified historical events
            events = db.query(ApplicationEventModel).order_by(ApplicationEventModel.timestamp.desc()).limit(10).all()
            recent_activity = []
            for e in events:
                evt_type = e.event_type
                notes = e.notes
                if (e.application_id == "app-usr-2a43a63d" and evt_type == "SUBMITTED") or evt_type == "SUBMISSION_UNVERIFIED":
                    evt_type = "SUBMISSION_UNVERIFIED"
                    notes = notes or "Historical internal record — external employer confirmation unverified."

                recent_activity.append({
                    "event_id": e.event_id,
                    "application_id": e.application_id,
                    "job_id": e.job_id,
                    "event_type": evt_type,
                    "source": e.source,
                    "notes": notes,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                })

            # 5. Featured openings for instant 1-tap mobile/desktop tailoring
            featured_openings = self._get_featured_openings(db, all_jobs)

            return DashboardOverviewResponse(
                queue_counts=queue_counts,
                pipeline_counts=pipeline_counts,
                recent_submissions_count=pipeline_counts.submitted,
                active_sources_count=active_sources,
                healthy_sources_count=healthy_sources,
                authenticated_sessions_count=authenticated_cnt,
                recent_activity=recent_activity,
                featured_openings=featured_openings,
                timestamp=utc_now(),
            )
        finally:
            if should_close:
                db.close()

    def _to_dashboard_queue_item(self, j: Any) -> DashboardQueueItem:
        """Convert a CopilotJob or existing DashboardQueueItem to a DashboardQueueItem."""
        if isinstance(j, DashboardQueueItem):
            return j

        matched_skills: List[str] = []
        major_gaps: List[str] = []
        primary_reason = None

        if hasattr(j, "recommendation") and j.recommendation:
            matched_skills = j.recommendation.strengths[:5]
            raw_gaps = j.recommendation.risks or []
            risk_set = set(j.risk_flags or [])
            major_gaps = [g for g in raw_gaps if g not in risk_set and not any(r in g for r in risk_set)][:3]
            if j.recommendation.reasons:
                primary_reason = j.recommendation.reasons[0]
        elif hasattr(j, "explanation") and j.explanation:
            matched_skills = j.explanation.why_apply[:5]
            raw_gaps = j.explanation.why_not_apply or []
            risk_set = set(j.risk_flags or [])
            major_gaps = [g for g in raw_gaps if g not in risk_set and not any(r in g for r in risk_set)][:3]

        app_status = None
        if hasattr(j, "current_application_status") and j.current_application_status:
            app_status = getattr(j.current_application_status, "value", str(j.current_application_status))

        return DashboardQueueItem(
            job_id=j.job_id,
            company=normalize_company_display(j.company),
            title=j.title,
            location=j.location,
            source=j.source,
            canonical_url=j.canonical_url,
            match_score=j.match_score,
            recommendation=j.recommendation_tier,
            priority_band=j.priority_band,
            priority_score=j.priority_score,
            queue_status=j.queue_status,
            freshness_days=j.freshness_days,
            key_matched_skills=matched_skills,
            major_gaps=major_gaps,
            risk_flags=j.risk_flags,
            primary_reason=primary_reason,
            selected_strategy=j.selected_strategy,
            tracking_application_id=j.tracking_application_id,
            application_status=app_status,
            discovered_at=j.discovered_at,
        )

    def _get_featured_openings(self, db: Session, queue_jobs: List[Any]) -> List[DashboardQueueItem]:
        """Return curated high-match job openings ready for 1-tap tailoring on mobile and desktop."""
        curated_defaults = [
            DashboardQueueItem(
                job_id="barclays-software-engineer-infrastructure-ce0266",
                company="Barclays",
                title="Software Engineer – Infrastructure & Cloud",
                location="Pune, India (Hybrid)",
                remote_status=RemoteStatus.HYBRID,
                source="Barclays Careers",
                canonical_url="https://search.jobs.barclays/job/-/-/13015/9",
                match_score=94.0,
                recommendation="APPLY_IMMEDIATELY",
                priority_band=PriorityBand.CRITICAL,
                priority_score=95.0,
                queue_status=QueueStatus.NEW,
                freshness_days=1,
                key_matched_skills=["Google Cloud Platform (GCP)", "Terraform", "CI/CD", "Docker", "Python"],
                primary_reason="Direct alignment with 2,000+ GCP resources & Terraform experience at HSBC.",
                selected_strategy="cloud_devops",
                tracking_application_id="app-barclays-ce0266",
            ),
            DashboardQueueItem(
                job_id="hsbc-fintech-senior-software-engineer-backend-0da84f",
                company="HSBC FinTech",
                title="Senior Software Engineer — Payments Data Platform",
                location="Pune, India (Hybrid)",
                remote_status=RemoteStatus.HYBRID,
                source="HSBC Careers",
                canonical_url="https://mycareer.hsbc.com",
                match_score=96.0,
                recommendation="APPLY_IMMEDIATELY",
                priority_band=PriorityBand.CRITICAL,
                priority_score=98.0,
                queue_status=QueueStatus.NEW,
                freshness_days=2,
                key_matched_skills=["Apache Beam", "GCP Dataflow", "BigQuery", "Java", "Spring Boot"],
                primary_reason="Direct match for 10M+ daily payment transaction ingestion pipelines.",
                selected_strategy="cloud_devops",
                tracking_application_id="app-hsbc-fintech-0da84f",
            ),
            DashboardQueueItem(
                job_id="mastercard-software-engineer-backend-java-b5bb2c",
                company="Mastercard",
                title="Software Engineer II — Backend & Payment Systems",
                location="Pune, India / Remote Friendly",
                remote_status=RemoteStatus.HYBRID,
                source="Mastercard Careers",
                canonical_url="https://mastercard.wd1.myworkdayjobs.com",
                match_score=91.0,
                recommendation="APPLY",
                priority_band=PriorityBand.HIGH,
                priority_score=90.0,
                queue_status=QueueStatus.NEW,
                freshness_days=2,
                key_matched_skills=["Java", "Spring Boot", "Microservices", "REST APIs", "PostgreSQL"],
                primary_reason="Strong match for Java backend and electronic payment platform experience.",
                selected_strategy="backend_java",
                tracking_application_id="app-mastercard-b5bb2c",
            ),
            DashboardQueueItem(
                job_id="stripe-staff-backend-engineer-payments-platform-8eadc9",
                company="Stripe",
                title="Backend Software Engineer — Payments Infrastructure",
                location="Remote (Global)",
                remote_status=RemoteStatus.REMOTE,
                source="Stripe Careers",
                canonical_url="https://stripe.com/jobs",
                match_score=89.0,
                recommendation="APPLY",
                priority_band=PriorityBand.HIGH,
                priority_score=88.0,
                queue_status=QueueStatus.NEW,
                freshness_days=3,
                key_matched_skills=["Distributed Systems", "GCP", "High Throughput", "Reliability", "Python"],
                primary_reason="Enterprise fintech scale and high-reliability data pipeline alignment.",
                selected_strategy="cloud_devops",
                tracking_application_id="app-stripe-8eadc9",
            ),
        ]
        for item in curated_defaults:
            try:
                self._ensure_curated_job_exists(db, item.job_id)
            except Exception as e:
                logger.debug(f"Curated opening auto-seed notice: {e}")

        converted = [self._to_dashboard_queue_item(j) for j in queue_jobs]
        high_matches = [j for j in converted if (j.match_score or 0) >= 75]
        seen = set()
        combined = []
        for item in high_matches + curated_defaults:
            if item.job_id not in seen:
                seen.add(item.job_id)
                combined.append(item)
        return combined[:6]

    # ==========================================================================
    # 2. Priority Queue
    # ==========================================================================

    def get_queue(
        self,
        status: Optional[QueueStatus] = None,
        priority_band: Optional[PriorityBand] = None,
        min_priority_score: Optional[float] = None,
    ) -> DashboardQueueResponse:
        """Fetch prioritized opportunity cards with explanations and matched skills."""
        jobs = self.copilot_service.get_queue(
            status=status,
            priority_band=priority_band,
            min_priority_score=min_priority_score,
        )

        items: List[DashboardQueueItem] = []
        critical_cnt = 0
        high_cnt = 0
        medium_cnt = 0
        low_cnt = 0

        for j in jobs:
            if j.priority_band == PriorityBand.CRITICAL:
                critical_cnt += 1
            elif j.priority_band == PriorityBand.HIGH:
                high_cnt += 1
            elif j.priority_band == PriorityBand.MEDIUM:
                medium_cnt += 1
            elif j.priority_band == PriorityBand.LOW:
                low_cnt += 1

            items.append(self._to_dashboard_queue_item(j))

        return DashboardQueueResponse(
            items=items,
            total_count=len(items),
            critical_count=critical_cnt,
            high_count=high_cnt,
            medium_count=medium_cnt,
            low_count=low_cnt,
        )

    # ==========================================================================
    # 3. Job Detail & Match Explanation
    # ==========================================================================

    def get_job_detail(self, job_id: str) -> JobDetailResponse:
        """
        Fetch full job details, 7-dimensional score breakdown, requirement provenance,
        and strictly separated Fact vs Inference vs Recommendation sections.
        """
        db, should_close = self._get_db_session()
        try:
            self._ensure_curated_job_exists(db, job_id)
            job_repo = JobRepository(db)
            job_model = job_repo.get_by_job_id(job_id)
            copilot_job = self.copilot_service.get_job(job_id)

            if not job_model and not copilot_job:
                raise FileNotFoundError(f"Job '{job_id}' not found.")

            # Retrieve or compute assessment
            assessment: Optional[JobAssessment] = None
            raw_text = job_model.description if job_model else ""
            if not raw_text and copilot_job:
                raw_text = f"{copilot_job.title} at {copilot_job.company}\nLocation: {copilot_job.location or ''}"

            if raw_text:
                try:
                    assessment = self.intelligence_service.evaluate_job(
                        raw_text=raw_text,
                        company_override=job_model.company if job_model else (copilot_job.company if copilot_job else None),
                        title_override=job_model.title if job_model else (copilot_job.title if copilot_job else None),
                        save_artifacts=False,
                    )
                except Exception as e:
                    logger.warning(f"Notice while evaluating job '{job_id}': {e}")

            # 7-Dimensional Breakdown
            dimension_scores: List[MatchDimensionScore] = []
            req_matches: List[RequirementMatchDetail] = []
            strengths: List[str] = []
            partial_matches: List[str] = []
            gaps: List[str] = []
            risks: List[str] = []
            rec_strat = "backend_java"
            strat_reason = "Standard software engineering strategy"
            alt_strats: List[str] = []
            match_score = copilot_job.match_score if copilot_job and copilot_job.match_score is not None else 70.0
            priority_score = copilot_job.priority_score if copilot_job else 50.0
            priority_band = copilot_job.priority_band.value if copilot_job else "MEDIUM"
            recommendation_tier = copilot_job.recommendation_tier if copilot_job and copilot_job.recommendation_tier else "APPLY"

            if assessment:
                match_score = assessment.score_breakdown.overall_score
                recommendation_tier = assessment.recommendation.value
                rec_strat = assessment.recommended_strategy
                strat_reason = assessment.strategy_reasoning
                alt_strats = assessment.alternative_strategies
                strengths = assessment.strengths
                partial_matches = assessment.partial_matches
                gaps = assessment.gaps
                risks = assessment.risks

                # 7 Dimensions
                sb = assessment.score_breakdown
                dimension_scores = [
                    MatchDimensionScore(dimension_name="Technical Skills", score=sb.technical_score, weight=0.30, description="Evaluation of mandatory and preferred technologies"),
                    MatchDimensionScore(dimension_name="Core Responsibilities", score=sb.responsibility_score, weight=0.25, description="Alignment with day-to-day engineering duties"),
                    MatchDimensionScore(dimension_name="Role & Seniority", score=sb.role_score, weight=0.15, description="Match on title hierarchy and expected engineering level"),
                    MatchDimensionScore(dimension_name="Professional Evidence", score=sb.experience_score, weight=0.15, description="Depth of verified production work history"),
                    MatchDimensionScore(dimension_name="Domain Expertise", score=sb.domain_score, weight=0.05, description="Specialized domain context (e.g. Fintech, Payments, Distributed Systems)"),
                    MatchDimensionScore(dimension_name="Preferences", score=sb.preference_score, weight=0.05, description="Location, remote work policy, and compensation alignment"),
                    MatchDimensionScore(dimension_name="Credentials & Education", score=sb.credential_score, weight=0.05, description="Degree qualifications and verified certifications"),
                ]

                # Requirement Matches
                for rm in assessment.match_results:
                    req_matches.append(
                        RequirementMatchDetail(
                            requirement_name=rm.requirement.name,
                            normalized_name=rm.requirement.normalized_name,
                            category=rm.requirement.category,
                            importance=rm.requirement.importance.value,
                            is_must_have=rm.requirement.is_must_have,
                            classification=rm.classification,
                            confidence=rm.confidence,
                            evidence_ids=rm.candidate_evidence_ids,
                            evidence_text=rm.candidate_evidence_text,
                            reason=rm.reason,
                        )
                    )

            # Fact vs Inference vs Recommendation Separation
            facts: List[str] = []
            inferences: List[str] = []
            recommendations: List[str] = []

            for rm in req_matches:
                if rm.classification == MatchClassification.MATCH_CONFIRMED:
                    facts.append(f"Confirmed production experience: {rm.requirement_name} ({', '.join(rm.evidence_ids) if rm.evidence_ids else 'Verified history'})")
                elif rm.classification in (MatchClassification.MATCH_PROJECT_ONLY, MatchClassification.MATCH_EXPOSURE_ONLY):
                    facts.append(f"Hands-on project/exposure: {rm.requirement_name}")
                elif rm.classification == MatchClassification.NO_EVIDENCE:
                    inferences.append(f"No direct evidence found for: {rm.requirement_name}")

            if strengths:
                inferences.append(f"Strong alignment in {len(strengths)} core areas ({', '.join(strengths[:3])})")
            if gaps:
                inferences.append(f"Requirement gaps identified in {len(gaps)} areas ({', '.join(gaps[:2])})")

            recommendations.append(f"Selected Strategy: {rec_strat.upper()} ({strat_reason})")
            if match_score >= 80:
                recommendations.append("Priority Recommendation: Review prepared application package for human confirmation.")
            elif match_score >= 60:
                recommendations.append("Recommendation: Inspect identified gaps before proceeding with application.")
            else:
                recommendations.append("Recommendation: Low overall fit. Consider skipping unless strategically required.")

            explanation = ExplanationSection(
                facts=facts if facts else ["Candidate profile loaded from canonical evidence."],
                inferences=inferences if inferences else ["Role evaluated against candidate background."],
                recommendations=recommendations,
            )

            raw_c = job_model.company if job_model else (copilot_job.company if copilot_job else "Unknown Company")
            return JobDetailResponse(
                job_id=job_id,
                title=job_model.title if job_model else (copilot_job.title if copilot_job else "Unknown Role"),
                company=normalize_company_display(raw_c),
                location=job_model.location if job_model else (copilot_job.location if copilot_job else None),
                source=job_model.source if job_model and job_model.source else (copilot_job.source if copilot_job else "unknown"),
                url=job_model.canonical_url or (job_model.url if job_model else (copilot_job.canonical_url if copilot_job else None)),
                remote_status=job_model.remote_status.value if job_model else "UNKNOWN",
                employment_type=job_model.employment_type.value if job_model else "FULL_TIME",
                discovered_at=job_model.discovered_at if job_model else (copilot_job.discovered_at if copilot_job else utc_now()),
                lifecycle_status=job_model.lifecycle_status if job_model else "DISCOVERED",
                description=raw_text,
                requirements=job_model.requirements if job_model else [],
                technologies=job_model.technologies if job_model else [],
                salary_min=job_model.salary_min if job_model else None,
                salary_max=job_model.salary_max if job_model else None,
                currency=job_model.currency if job_model else "USD",
                match_score=round(match_score, 1),
                priority_score=round(priority_score, 1),
                priority_band=priority_band,
                recommendation=recommendation_tier,
                dimension_scores=dimension_scores,
                requirement_matches=req_matches,
                strengths=strengths,
                partial_matches=partial_matches,
                gaps=gaps,
                risks=risks,
                explanation=explanation,
                recommended_strategy=rec_strat,
                strategy_reasoning=strat_reason,
                alternative_strategies=alt_strats,
            )
        finally:
            if should_close:
                db.close()

    # ==========================================================================
    # 4. Application Review & Details
    # ==========================================================================

    def get_application_detail(self, application_id: str) -> ApplicationDetailResponse:
        """
        Fetch full application review package including tailored resume, cover letter,
        prepared Q&A answers, user input fields, artifacts, browser review summary, and timeline.
        Enforces canonical identity resolution and persistent user input hydration.
        """
        db, should_close = self._get_db_session()
        try:
            self._ensure_curated_job_exists(db, application_id)
            app_repo = ApplicationRepository(db)
            app_model = app_repo.get_by_application_id(application_id)
            if not app_model:
                # Try finding by job_id_str
                app_model = app_repo.get_by_job_id_str(application_id)

            # Check tracking store
            tracking_app = self.tracking_service.get_application(application_id) or self.tracking_service.get_application_by_job_id(application_id)

            resolved_job_id = None
            if app_model and app_model.job_id_str:
                resolved_job_id = app_model.job_id_str
            elif tracking_app and tracking_app.job_id:
                resolved_job_id = tracking_app.job_id
            else:
                resolved_job_id = application_id

            if not app_model and resolved_job_id:
                app_model = app_repo.get_by_job_id_str(resolved_job_id) or app_repo.get_by_application_id(resolved_job_id)

            job_repo = JobRepository(db)
            db_job = None
            if app_model and app_model.job_id:
                db_job = job_repo.get_by_id(app_model.job_id)
            if not db_job and resolved_job_id:
                db_job = job_repo.get_by_job_id(resolved_job_id)
            if not db_job:
                db_job = job_repo.get_by_job_id(application_id)

            canonical = None
            if resolved_job_id:
                canonical = self.copilot_service.orchestrator.discovery_service.store.get_canonical_job(resolved_job_id)
            if not canonical and application_id and resolved_job_id != application_id:
                canonical = self.copilot_service.orchestrator.discovery_service.store.get_canonical_job(application_id)

            job_id = resolved_job_id or (canonical.job_id if canonical else (db_job.job_id if db_job else application_id))
            
            raw_comp = (
                app_model.company if app_model and app_model.company
                else (db_job.company if db_job and db_job.company
                else (canonical.company if canonical and canonical.company
                else (tracking_app.company if tracking_app and tracking_app.company else None)))
            )
            company = normalize_company_display(raw_comp)

            role = (
                app_model.role if app_model and app_model.role
                else (db_job.title if db_job and db_job.title
                else (canonical.title if canonical and canonical.title
                else (tracking_app.role if tracking_app and tracking_app.role else None)))
            )

            source = (
                app_model.source if app_model and app_model.source
                else (db_job.source if db_job and db_job.source
                else (canonical.source if canonical and canonical.source
                else (tracking_app.source if tracking_app and tracking_app.source else None)))
            )

            canonical_url = (
                app_model.canonical_job_url if app_model and app_model.canonical_job_url
                else (db_job.canonical_url or db_job.url if db_job
                else (canonical.canonical_url or canonical.source_url if canonical
                else (tracking_app.canonical_job_url if tracking_app else None)))
            )

            # Invariant: Never return fake placeholders or fabricated records when resolution fails
            invalid_placeholders = {"company unavailable", "unknown company", "target company", "general_swe", "role unavailable", "unknown role", "source unavailable"}
            if (
                not company
                or not role
                or not source
                or company.lower() in invalid_placeholders
                or role.lower() in invalid_placeholders
                or source.lower() in invalid_placeholders
            ):
                raise ValueError(f"Could not resolve canonical application data for '{application_id}'. Canonical record missing or invalid.")

            match_score = app_model.match_score if app_model and app_model.match_score is not None else (tracking_app.match_score if tracking_app else None)
            recommendation = app_model.recommendation if app_model and app_model.recommendation else (tracking_app.recommendation if tracking_app else None)

            # Retrieve prepared package if available on disk/cache
            pkg = self.prep_service.get_application_package(job_id)
            if not pkg and job_id != application_id:
                pkg = self.prep_service.get_application_package(application_id)

            selected_strat = ResumeStrategy.normalize(app_model.resume_strategy if app_model and app_model.resume_strategy else (pkg.selected_resume_strategy if pkg else None))

            # Hydrate saved user inputs from persistent storage
            saved_answers = self.prep_service.load_saved_user_inputs(job_id)
            if not saved_answers and job_id != application_id:
                saved_answers = self.prep_service.load_saved_user_inputs(application_id)

            prepared_answers: List[PreparedAnswerItem] = []
            user_inputs: List[UserInputRequiredItem] = []
            resume_pdf_path = None
            resume_tex_content = None
            cover_letter_text = None
            cover_letter_subject = None
            cover_letter_valid = True

            if pkg:
                selected_strat = pkg.selected_resume_strategy
                resume_pdf_path = pkg.resume_pdf_path
                cover_letter_text = pkg.cover_letter.letter_text if pkg.cover_letter else None
                cover_letter_subject = getattr(pkg.cover_letter, "subject", None) if pkg.cover_letter else None
                cover_letter_valid = pkg.cover_letter.validation.is_valid if pkg.cover_letter and getattr(pkg.cover_letter, "validation", None) else True

                # TeX content from file if exists
                if pkg.resume_tex_path and Path(pkg.resume_tex_path).exists():
                    try:
                        resume_tex_content = Path(pkg.resume_tex_path).read_text(encoding="utf-8")
                    except Exception:
                        pass

                # Prepared answers with user inputs hydrated
                for ans in pkg.answers:
                    ans_text = saved_answers.get(ans.question_id) if ans.question_id in saved_answers else (ans.answer or "Pending user input")
                    requires_input = ans.requires_user_input and (ans.question_id not in saved_answers)
                    evidence_refs = [p.source_ref for p in ans.provenance] if getattr(ans, "provenance", None) else []
                    if ans.question_id in saved_answers and "USER_INPUT" not in evidence_refs:
                        evidence_refs = ["USER_INPUT"] + evidence_refs

                    prepared_answers.append(
                        PreparedAnswerItem(
                            question_text=ans.question_text,
                            field_name=ans.question_id,
                            field_category=getattr(ans.classification, "value", str(ans.classification)),
                            answer_text=ans_text,
                            confidence=1.0 if ans.question_id in saved_answers else ans.confidence,
                            source_evidence=evidence_refs,
                            requires_user_input=requires_input,
                            validation_status="VALID",
                        )
                    )

                # User inputs required with current_value populated
                for uir in pkg.user_inputs_required:
                    current_val = saved_answers.get(uir.question_id) or uir.current_value
                    user_inputs.append(
                        UserInputRequiredItem(
                            question_id=uir.question_id,
                            question_text=uir.question_text,
                            field_type=getattr(uir.expected_type, "value", "text"),
                            current_value=current_val,
                            reason_required=uir.reason,
                            options=uir.options if getattr(uir, "options", None) else None,
                            is_sensitive=True,
                        )
                    )

            # Phase 10A Artifacts
            artifacts_list = self.artifact_service.list_artifacts(application_id=application_id, job_id=job_id)
            artifact_items: List[ArtifactSummaryItem] = [
                ArtifactSummaryItem(
                    artifact_id=art.artifact_id,
                    artifact_type=art.artifact_type.value,
                    original_filename=art.original_filename,
                    content_type=art.content_type,
                    size_bytes=art.size_bytes,
                    sha256=art.sha256,
                    status=art.status.value,
                    created_at=art.created_at,
                    download_url=f"/api/dashboard/artifacts/{art.artifact_id}/content",
                )
                for art in artifacts_list
            ]

            # If resume_tex_content is not on local disk, check artifact service for full LaTeX content
            if not resume_tex_content:
                for art in artifacts_list:
                    if art.artifact_type.value == "TAILORED_RESUME_TEX":
                        try:
                            art_data, _ = self.artifact_service.get_artifact(art.artifact_id)
                            resume_tex_content = art_data.decode("utf-8")
                            break
                        except Exception:
                            pass

            # Browser Worker Review Package (Read-only query, no synthetic task creation)
            task_repo = BrowserTaskRepository(db)
            browser_task = task_repo.get_by_application_or_job_id(
                application_id=app_model.application_id if app_model else application_id,
                job_id=job_id,
            )

            # Single canonical status projection across all dashboard views
            canonical_status = resolve_canonical_application_state(app=app_model, browser_task=browser_task)
            status = canonical_status

            # Blocker and Resume state computation (Enforcing Option B - Safe Manual Takeover for headless Render)
            blocker_type = None
            blocker_instruction = None
            can_resume = False
            is_external_unverified = (canonical_status == "SUBMISSION_UNVERIFIED")

            if browser_task:
                if browser_task.status == BrowserTaskStatus.CAPTCHA_REQUIRED:
                    blocker_type = "CAPTCHA"
                    blocker_instruction = "The automated browser cannot safely continue because CAPTCHA verification is required. Complete this application manually in the employer portal. The automation will not submit or retry automatically."
                    can_resume = False
                elif browser_task.status == BrowserTaskStatus.LOGIN_REQUIRED:
                    blocker_type = "LOGIN"
                    blocker_instruction = "The automated browser cannot safely continue because authentication login is required. Complete this application manually in the employer portal. The automation will not submit or retry automatically."
                    can_resume = False
                elif browser_task.status == BrowserTaskStatus.MFA_REQUIRED:
                    blocker_type = "MFA"
                    blocker_instruction = "The automated browser cannot safely continue because MFA/OTP verification is required. Complete this application manually in the employer portal. The automation will not submit or retry automatically."
                    can_resume = False
                elif browser_task.status in (BrowserTaskStatus.HUMAN_ACTION_REQUIRED, BrowserTaskStatus.BLOCKED):
                    blocker_type = "HUMAN_ACTION"
                    blocker_instruction = browser_task.pause_reason or "The automated browser cannot safely continue because human action is required. Complete this application manually in the employer portal. The automation will not submit or retry automatically."
                    can_resume = False
                elif browser_task.status == BrowserTaskStatus.USER_INPUT_REQUIRED:
                    blocker_type = "USER_INPUT"
                    blocker_instruction = "Required questions need your answer. Complete them in the Needs Input tab and save."
                    can_resume = True
                elif browser_task.status == BrowserTaskStatus.SUBMISSION_UNVERIFIED:
                    is_external_unverified = True

            # Historical unverified record check (Mastercard production application)
            if (app_model and app_model.application_id == "app-usr-2a43a63d") or application_id == "app-usr-2a43a63d":
                is_external_unverified = True
                status = "SUBMISSION_UNVERIFIED"

            browser_review: Optional[BrowserReviewSummary] = None

            if browser_task:
                rp = browser_task.review_package_json or {}
                has_ss = bool(rp.get("screenshot_artifact_id") or rp.get("screenshot_path"))

                # Load persisted human inputs for hydration
                saved_inputs = self.prep_service.load_saved_user_inputs(job_id)
                if application_id != job_id:
                    app_inputs = self.prep_service.load_saved_user_inputs(application_id)
                    for k, v in app_inputs.items():
                        if k not in saved_inputs:
                            saved_inputs[k] = v

                mapped_fields_list: List[BrowserMappedFieldItem] = []
                seen_field_ids = set()

                # 1. Source: Structured fields in review_package_json (from worker or agent protocol)
                raw_fields = rp.get("fields_summary") or rp.get("fields") or rp.get("mapped_fields") or []
                if isinstance(raw_fields, list):
                    for rf in raw_fields:
                        if isinstance(rf, dict):
                            fid = rf.get("field_id") or rf.get("name") or rf.get("label") or f"field_{len(mapped_fields_list)+1}"
                            if fid in seen_field_ids:
                                continue
                            seen_field_ids.add(fid)
                            lbl = rf.get("label") or rf.get("name") or fid
                            name = rf.get("name") or rf.get("target_field") or fid
                            el_type = rf.get("element_type") or rf.get("field_type") or "text"
                            action = str(rf.get("action") or "AUTO_FILL")
                            val = rf.get("filled_value_masked") or rf.get("proposed_value") or rf.get("value")
                            status_val = "FILLED" if val else "PENDING_INPUT"
                            src = rf.get("evidence_source") or rf.get("source") or ("Candidate Evidence" if val else None)
                            reason = rf.get("reason") or rf.get("rationale")

                            # Check if human answer was saved for this field
                            for match_key in (fid, name, lbl, rf.get("target_field")):
                                if match_key and match_key in saved_inputs:
                                    val = str(saved_inputs[match_key])
                                    action = "USER_PROVIDED"
                                    status_val = "FILLED"
                                    src = "Human Input"
                                    reason = "User provided sensitive answer"
                                    break

                            mapped_fields_list.append(
                                BrowserMappedFieldItem(
                                    field_id=fid,
                                    label=lbl,
                                    name=name,
                                    element_type=el_type,
                                    action=action,
                                    value=val,
                                    status=status_val,
                                    source=src,
                                    reason=reason,
                                )
                            )

                # 2. Source: Check mapping.json on disk if not populated from review_package_json
                if not mapped_fields_list:
                    disk_mapping_path = Path("data/applications") / job_id / "browser" / "mapping.json"
                    if disk_mapping_path.exists():
                        try:
                            import json
                            disk_map = json.loads(disk_mapping_path.read_text(encoding="utf-8"))
                            if isinstance(disk_map, list):
                                for dm in disk_map:
                                    if isinstance(dm, dict):
                                        fid = dm.get("field_id") or dm.get("target_field") or f"field_{len(mapped_fields_list)+1}"
                                        if fid in seen_field_ids:
                                            continue
                                        seen_field_ids.add(fid)
                                        lbl = dm.get("field_label") or dm.get("target_field") or fid
                                        name = dm.get("target_field") or fid
                                        el_type = dm.get("field_type") or "text"
                                        val = dm.get("proposed_value") or dm.get("mapped_value")
                                        req_input = bool(dm.get("requires_user_input"))
                                        action = "REQUIRES_USER_INPUT" if req_input else "AUTO_FILL"
                                        status_val = "PENDING_INPUT" if req_input else ("FILLED" if val else "SKIPPED")
                                        src = dm.get("source_type") or ("Candidate Evidence" if val else None)
                                        reason = dm.get("rationale")

                                        for match_key in (fid, name, lbl, dm.get("target_field")):
                                            if match_key and match_key in saved_inputs:
                                                val = str(saved_inputs[match_key])
                                                action = "USER_PROVIDED"
                                                status_val = "FILLED"
                                                src = "Human Input"
                                                reason = "User provided sensitive answer"
                                                break

                                        mapped_fields_list.append(
                                            BrowserMappedFieldItem(
                                                field_id=fid,
                                                label=lbl,
                                                name=name,
                                                element_type=el_type,
                                                action=action,
                                                value=val,
                                                status=status_val,
                                                source=src,
                                                reason=reason,
                                            )
                                        )
                        except Exception as e:
                            logger.warning(f"Error reading disk mapping.json: {e}")

                # 3. Source: Derive from application package answers & user inputs required
                if not mapped_fields_list and pkg:
                    for ans in (pkg.answers or []):
                        fid = ans.question_id or f"q_{len(mapped_fields_list)+1}"
                        if fid in seen_field_ids:
                            continue
                        seen_field_ids.add(fid)
                        lbl = ans.question_text
                        name = getattr(ans, "field_name", None) or ans.question_id
                        el_type = "text"
                        val = ans.answer
                        req_input = bool(ans.requires_user_input)

                        # Check saved human answers first
                        saved_val = None
                        for match_key in (fid, name, lbl, ans.question_id):
                            if match_key and match_key in saved_inputs:
                                saved_val = str(saved_inputs[match_key])
                                break

                        if saved_val is not None:
                            val = saved_val
                            action = "USER_PROVIDED"
                            status_val = "FILLED"
                            src = "Human Input"
                            reason = "User provided sensitive answer"
                        elif val and not req_input:
                            action = "AUTO_FILL"
                            status_val = "FILLED"
                            src = "Candidate Evidence"
                            reason = "Evidence-backed candidate answer"
                        else:
                            val = None
                            action = "REQUIRES_USER_INPUT"
                            status_val = "PENDING_INPUT"
                            src = "Needs User Input"
                            reason = "Requires manual user answer"

                        mapped_fields_list.append(
                            BrowserMappedFieldItem(
                                field_id=fid,
                                label=lbl,
                                name=name,
                                element_type=el_type,
                                action=action,
                                value=val,
                                status=status_val,
                                source=src,
                                reason=reason,
                            )
                        )

                # Ensure all pkg.user_inputs_required are represented if not already
                if pkg and pkg.user_inputs_required:
                    for req_item in pkg.user_inputs_required:
                        fid = req_item.question_id or getattr(req_item, "field_name", None) or getattr(req_item, "question_text", None) or f"req_{len(mapped_fields_list)+1}"
                        if fid not in seen_field_ids:
                            seen_field_ids.add(fid)
                            lbl = getattr(req_item, "question_text", None) or getattr(req_item, "question", fid)
                            name = getattr(req_item, "field_name", None) or req_item.question_id
                            el_type = getattr(req_item, "expected_type", None) or "text"
                            if hasattr(el_type, "value"):
                                el_type = el_type.value

                            saved_val = None
                            for match_key in (fid, name, lbl, req_item.question_id):
                                if match_key and match_key in saved_inputs:
                                    saved_val = str(saved_inputs[match_key])
                                    break

                            if saved_val is not None:
                                val = saved_val
                                action = "USER_PROVIDED"
                                status_val = "FILLED"
                                src = "Human Input"
                                reason = "User provided sensitive answer"
                            else:
                                val = req_item.current_value
                                action = "USER_PROVIDED" if val else "REQUIRES_USER_INPUT"
                                status_val = "FILLED" if val else "PENDING_INPUT"
                                src = "Human Input" if val else "Needs User Input"
                                reason = getattr(req_item, "reason", None) or "Requires manual user answer"

                            mapped_fields_list.append(
                                BrowserMappedFieldItem(
                                    field_id=fid,
                                    label=lbl,
                                    name=name,
                                    element_type=str(el_type),
                                    action=action,
                                    value=val,
                                    status=status_val,
                                    source=src,
                                    reason=reason,
                                )
                            )

                # Calculate exact counts matching mapped_fields_list
                detected_cnt = len(mapped_fields_list)
                filled_cnt = sum(1 for f in mapped_fields_list if f.status == "FILLED" and f.value)
                unresolved_cnt = sum(1 for f in mapped_fields_list if f.status == "PENDING_INPUT" or f.action == "REQUIRES_USER_INPUT")

                # Fallback to rp counts only if no fields were resolved
                if detected_cnt == 0:
                    detected_cnt = len(rp.get("detected_fields", []))
                    filled_cnt = len(rp.get("filled_fields", []))
                    unresolved_cnt = len(rp.get("unresolved_fields", []))

                browser_review = BrowserReviewSummary(
                    task_id=browser_task.task_id,
                    source=browser_task.source,
                    target_url=browser_task.target_url,
                    status=browser_task.status.value,
                    fields_detected_count=detected_cnt,
                    fields_filled_count=filled_cnt,
                    fields_requiring_input_count=unresolved_cnt,
                    has_screenshot=has_ss,
                    screenshot_artifact_id=rp.get("screenshot_artifact_id"),
                    has_confirmation_token=bool(browser_task.confirmation_token),
                    confirmation_token=browser_task.confirmation_token,
                    is_ready_for_review=(browser_task.status == BrowserTaskStatus.READY_FOR_REVIEW),
                    pause_reason=browser_task.pause_reason,
                    failure_reason=browser_task.failure_reason,
                    warnings=rp.get("warnings", []),
                    blocker_type=blocker_type,
                    blocker_instruction=blocker_instruction,
                    can_resume=can_resume,
                    is_external_unverified=is_external_unverified,
                    mapped_fields=mapped_fields_list,
                )

            # Timeline Events
            timeline_events: List[ApplicationTimelineEvent] = []
            if app_model and app_model.events:
                for evt in app_model.events:
                    evt_type = evt.event_type
                    notes = evt.notes
                    if (app_model.application_id == "app-usr-2a43a63d" and evt_type == "SUBMITTED") or evt_type == "SUBMISSION_UNVERIFIED":
                        evt_type = "SUBMISSION_UNVERIFIED"
                        notes = notes or "Historical internal record — external employer confirmation unverified."

                    timeline_events.append(
                        ApplicationTimelineEvent(
                            event_id=evt.event_id,
                            event_type=evt_type,
                            timestamp=evt.timestamp,
                            source=evt.source,
                            notes=notes,
                            metadata=evt.metadata_json or {},
                        )
                    )

            return ApplicationDetailResponse(
                application_id=app_model.application_id if app_model and app_model.application_id else application_id,
                job_id=job_id,
                company=company,
                role=role,
                source=source,
                canonical_job_url=canonical_url,
                status=status,
                match_score=match_score,
                recommendation=recommendation,
                selected_strategy=selected_strat,
                resume_pdf_path=resume_pdf_path,
                resume_tex_content=resume_tex_content,
                cover_letter_text=cover_letter_text,
                cover_letter_subject=cover_letter_subject,
                cover_letter_valid=cover_letter_valid,
                prepared_answers=prepared_answers,
                user_inputs_required=user_inputs,
                artifacts=artifact_items,
                browser_review=browser_review,
                timeline=timeline_events,
                user_notes=app_model.user_notes if app_model else [],
                discovered_at=app_model.discovered_at if app_model else None,
                prepared_at=app_model.prepared_at if app_model else None,
                submitted_at=app_model.submitted_at if status == "SUBMITTED" else None,
                blocker_type=blocker_type,
                blocker_instruction=blocker_instruction,
                can_resume=can_resume,
                is_external_unverified=is_external_unverified,
            )
        finally:
            if should_close:
                db.close()


    # ==========================================================================
    # 5. Application Actions (Prepare, Skip, User Input, Confirm)
    # ==========================================================================

    def prepare_application(self, application_id: str, strategy_override: Optional[str] = None) -> ApplicationDetailResponse:
        """Prepare tailored resume, cover letter, and Q&A answers for an application."""
        db, should_close = self._get_db_session()
        try:
            self._ensure_curated_job_exists(db, application_id)
            app_repo = ApplicationRepository(db)
            app = app_repo.get_by_application_id(application_id) or app_repo.get_by_job_id_str(application_id)
            job_id = app.job_id_str if app and app.job_id_str else application_id

            # Trigger preparation
            pkg = self.prep_service.prepare_application(
                job_id_or_text=job_id,
                strategy_override=strategy_override,
                db_session=db,
            )

            # Update application record if existing or create if missing
            if not app:
                app = app_repo.get_by_application_id(application_id) or app_repo.get_by_job_id_str(job_id)

            if not app:
                job_repo = JobRepository(db)
                db_job = job_repo.get_by_job_id(job_id)
                app_id = f"app-{job_id[:16]}"
                app = Application(
                    application_id=app_id,
                    job_id=db_job.id if db_job else None,
                    job_id_str=job_id,
                    company=db_job.company if db_job else "Target Company",
                    role=db_job.title if db_job else "Software Engineer",
                    canonical_job_url=(db_job.canonical_url or db_job.url) if db_job else None,
                    source=db_job.source if db_job else "direct",
                    status=ApplicationStatus.READY_TO_APPLY,
                    resume_strategy=pkg.selected_resume_strategy,
                    prepared_at=utc_now(),
                )
                db.add(app)
                db.commit()
                db.refresh(app)
            else:
                app.status = ApplicationStatus.READY_TO_APPLY
                app.resume_strategy = pkg.selected_resume_strategy
                app.prepared_at = utc_now()
                app_repo.append_event(
                    application_id=app.application_id,
                    job_id=job_id,
                    event_type="PREPARED",
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    source="DASHBOARD_OPERATOR",
                    notes=f"Prepared application with strategy '{pkg.selected_resume_strategy}'",
                )
                db.commit()

            target_app_id = app.application_id if app else application_id

            # Ensure browser task exists in QUEUED status
            task_repo = BrowserTaskRepository(db)
            existing_task = task_repo.get_by_application_or_job_id(
                application_id=target_app_id,
                job_id=job_id,
            )
            review_pkg_json = {
                "detected_fields": [a.question_text for a in pkg.answers],
                "filled_fields": [a.question_text for a in pkg.answers if not a.requires_user_input],
                "unresolved_fields": [u.question_text for u in pkg.user_inputs_required],
                "warnings": [],
            }
            if not existing_task:
                task_id = f"task-bw-{uuid.uuid4().hex[:8]}"
                job_repo = JobRepository(db)
                db_job = job_repo.get_by_job_id(job_id)
                target_url = app.canonical_job_url if app and app.canonical_job_url else (db_job.canonical_url or db_job.url if db_job else None)
                new_task = BrowserTaskModel(
                    task_id=task_id,
                    application_id=target_app_id,
                    job_id=job_id,
                    source=app.source if app else (db_job.source if db_job else "manual"),
                    target_url=target_url or f"https://jobs.example.com/apply/{job_id}",
                    status=BrowserTaskStatus.QUEUED,
                    confirmation_token=None,
                    confirmation_expires_at=None,
                    review_package_json=review_pkg_json,
                )
                task_repo.create(new_task)

            return self.get_application_detail(target_app_id)
        finally:
            if should_close:
                db.close()

    def skip_application(self, application_id: str, reason: Optional[str] = None) -> ApplicationDetailResponse:
        """Mark an opportunity/application as SKIPPED without external actions."""
        db, should_close = self._get_db_session()
        try:
            app_repo = ApplicationRepository(db)
            app = app_repo.get_by_application_id(application_id) or app_repo.get_by_job_id_str(application_id)
            job_id = app.job_id_str if app and app.job_id_str else application_id

            self.copilot_service.skip(job_id=job_id, reason=reason)

            if app:
                app.status = ApplicationStatus.WITHDRAWN
                app_repo.append_event(
                    application_id=app.application_id,
                    job_id=job_id,
                    event_type="WITHDRAWN",
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    source="DASHBOARD_OPERATOR",
                    notes=f"Application skipped/archived: {reason or 'No reason provided'}",
                )
                db.commit()

            return self.get_application_detail(application_id)
        finally:
            if should_close:
                db.close()

    def submit_user_inputs(self, application_id: str, req: HumanInputSubmitRequest) -> ApplicationDetailResponse:
        """
        Record user-provided answers for sensitive/unresolved questions.
        Stores them persistently on disk in user_inputs.json and updates package.json
        WITHOUT modifying candidate truth files.
        """
        db, should_close = self._get_db_session()
        try:
            app_repo = ApplicationRepository(db)
            app = app_repo.get_by_application_id(application_id) or app_repo.get_by_job_id_str(application_id)
            tracking_app = self.tracking_service.get_application(application_id) or self.tracking_service.get_application_by_job_id(application_id)

            job_id = app.job_id_str if app and app.job_id_str else (tracking_app.job_id if tracking_app else application_id)

            # Persist human answers on disk via prep_service
            answers_dict = {a.question_id: a.answer_value for a in req.answers}
            self.prep_service.save_user_inputs(job_id=job_id, answers=answers_dict)
            if application_id != job_id:
                self.prep_service.save_user_inputs(job_id=application_id, answers=answers_dict)

            notes_entry = f"Human input provided for {len(req.answers)} questions: " + ", ".join(
                f"{a.question_id}='{a.answer_value}'" for a in req.answers
            )
            
            if app:
                existing_notes = list(app.user_notes or [])
                existing_notes.append(notes_entry)
                app.user_notes = existing_notes
                app_repo.append_event(
                    application_id=app.application_id,
                    job_id=job_id,
                    event_type="WAITING_FOR_USER",
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    source="DASHBOARD_OPERATOR",
                    notes="User supplied required application answers.",
                    metadata_json={"provided_answers": [a.model_dump() for a in req.answers]},
                )
            # Update associated BrowserTask if present
            task_repo = BrowserTaskRepository(db)
            b_task = task_repo.get_by_application_or_job_id(
                application_id=app.application_id if app else application_id,
                job_id=job_id,
            )
            if b_task:
                rp = dict(b_task.review_package_json or {})
                # Update review_package_json counts and fields
                existing_pkg = self.prep_service.get_application_package(job_id)
                if existing_pkg:
                    rp["detected_fields"] = [a.question_text for a in existing_pkg.answers]
                    rp["filled_fields"] = [a.question_text for a in existing_pkg.answers if (not a.requires_user_input or a.question_id in answers_dict)]
                    rp["unresolved_fields"] = [u.question_text for u in existing_pkg.user_inputs_required if u.question_id not in answers_dict]
                    b_task.review_package_json = rp

                # If task was paused waiting for user input and all inputs are now resolved, transition to READY_FOR_REVIEW
                unresolved_remaining = rp.get("unresolved_fields", [])
                if b_task.status == BrowserTaskStatus.USER_INPUT_REQUIRED and len(unresolved_remaining) == 0:
                    token = HumanConfirmationService.generate_confirmation_token()
                    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                    task_repo.set_review_package(
                        task_id=b_task.task_id,
                        review_package=rp,
                        confirmation_token=token,
                        confirmation_expires_at=expires_at,
                    )
                    task_repo.update_status(b_task.task_id, BrowserTaskStatus.READY_FOR_REVIEW, pause_reason=None)
                    task_repo.append_audit_event(
                        b_task.task_id,
                        {
                            "event": "user_inputs_resolved",
                            "status": BrowserTaskStatus.READY_FOR_REVIEW.value,
                            "confirmation_token_issued": True,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )

                db.commit()

            logger.info(f"Recorded human input for application '{application_id}' (candidate truth untouched).")
            return self.get_application_detail(application_id)
        finally:
            if should_close:
                db.close()

    def confirm_submission(
        self,
        payload: SubmissionConfirmPayload,
        application_id: Optional[str] = None,
    ) -> SubmissionConfirmResponse:
        """
        Gated submission authorization path delegating to HumanConfirmationService.
        Enforces confirm_text='SUBMIT' and valid confirmation_token.
        Transitions task to SUBMISSION_AUTHORIZED without faking external completion.
        """
        db, should_close = self._get_db_session()
        try:
            confirm_service = HumanConfirmationService(db=db)
            confirm_req = HumanConfirmationRequest(
                task_id=payload.task_id,
                confirmation_token=payload.confirmation_token,
                confirm_text=payload.confirm_text,
                user_notes=payload.user_notes,
            )

            result = confirm_service.validate_and_confirm(
                task_id=payload.task_id,
                request=confirm_req,
                application_id=application_id,
            )

            return SubmissionConfirmResponse(
                success=result.success,
                application_id=result.application_id,
                task_id=result.task_id,
                status=result.status.value,
                submission_reference=result.submission_reference,
                submitted_at=result.submitted_at,
                message=result.message,
            )
        except SubmissionSafetyError as sse:
            logger.warning(f"Submission confirmation blocked: {sse}")
            raise
        finally:
            if should_close:
                db.close()

    def resume_application(self, application_id: str) -> ApplicationDetailResponse:
        """
        Resume an application that paused for human action (CAPTCHA, Login, MFA, User Input).
        """
        db, should_close = self._get_db_session()
        try:
            app_repo = ApplicationRepository(db)
            app = app_repo.get_by_application_id(application_id) or app_repo.get_by_job_id_str(application_id)
            if not app:
                raise ValueError(f"Application '{application_id}' not found.")

            task_repo = BrowserTaskRepository(db)
            task = task_repo.get_by_application_or_job_id(
                application_id=app.application_id,
                job_id=app.job_id_str,
            )
            if not task:
                raise ValueError(f"No browser task found for application '{application_id}'.")

            # Check if task is in a resumable pause state
            if task.status in (
                BrowserTaskStatus.CAPTCHA_REQUIRED,
                BrowserTaskStatus.LOGIN_REQUIRED,
                BrowserTaskStatus.MFA_REQUIRED,
                BrowserTaskStatus.HUMAN_ACTION_REQUIRED,
                BrowserTaskStatus.USER_INPUT_REQUIRED,
            ):
                # Reset pause reason and transition back to QUEUED or SUBMISSION_AUTHORIZED
                has_auth_event = any(e.get("event") == "human_submission_authorized" for e in (task.audit_events or []))
                next_status = BrowserTaskStatus.SUBMISSION_AUTHORIZED if has_auth_event else BrowserTaskStatus.QUEUED
                task_repo.update_status(task.task_id, next_status, pause_reason=None)
                task_repo.append_audit_event(
                    task.task_id,
                    {
                        "event": "task_resumed_by_user",
                        "status": next_status.value,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                db.commit()

            return self.get_application_detail(application_id)
        finally:
            if should_close:
                db.close()

    def list_applications(
        self,
        status: Optional[Any] = None,
        strategy: Optional[str] = None,
    ) -> List[ApplicationRecord]:
        """
        List unified tracked applications merging Phase 8 TrackingStore
        and DB ApplicationRepository for the Kanban board and lifecycle ledger.
        Ensures canonical state mapping so unverified applications are never shown as SUBMITTED.
        """
        tracking_apps = self.tracking_service.list_applications(strategy=strategy)
        app_by_job: Dict[str, ApplicationRecord] = {a.job_id: a for a in tracking_apps}
        app_by_id: Dict[str, ApplicationRecord] = {a.application_id: a for a in tracking_apps}

        db, should_close = self._get_db_session()
        try:
            app_repo = ApplicationRepository(db)
            db_apps = app_repo.list_applications(limit=500)
            task_repo = BrowserTaskRepository(db)

            status_map = {
                ApplicationStatus.DISCOVERED: ApplicationLifecycleStatus.DISCOVERED,
                ApplicationStatus.SHORTLISTED: ApplicationLifecycleStatus.RECOMMENDED,
                ApplicationStatus.PREPARING: ApplicationLifecycleStatus.PREPARED,
                ApplicationStatus.READY_TO_APPLY: ApplicationLifecycleStatus.READY_FOR_REVIEW,
                ApplicationStatus.APPLIED: ApplicationLifecycleStatus.SUBMITTED,
                ApplicationStatus.OA: ApplicationLifecycleStatus.ASSESSMENT,
                ApplicationStatus.INTERVIEW: ApplicationLifecycleStatus.INTERVIEW,
                ApplicationStatus.OFFER: ApplicationLifecycleStatus.OFFER,
                ApplicationStatus.REJECTED: ApplicationLifecycleStatus.REJECTED,
                ApplicationStatus.WITHDRAWN: ApplicationLifecycleStatus.WITHDRAWN,
            }

            for db_app in db_apps:
                job_id = db_app.job_id_str or str(db_app.job_id or db_app.application_id)
                t = task_repo.get_by_application_or_job_id(db_app.application_id, job_id)
                c_state = resolve_canonical_application_state(app=db_app, browser_task=t)

                if c_state == "SUBMISSION_UNVERIFIED":
                    target_status = ApplicationLifecycleStatus.SUBMISSION_UNVERIFIED
                elif c_state == "MANUAL_ACTION_REQUIRED":
                    target_status = ApplicationLifecycleStatus.MANUAL_ACTION_REQUIRED
                elif c_state == "SUBMITTED":
                    target_status = ApplicationLifecycleStatus.SUBMITTED
                elif c_state == "READY_FOR_REVIEW":
                    target_status = ApplicationLifecycleStatus.READY_FOR_REVIEW
                elif c_state == "PREPARED":
                    target_status = ApplicationLifecycleStatus.PREPARED
                elif c_state == "RECOMMENDED":
                    target_status = ApplicationLifecycleStatus.RECOMMENDED
                elif c_state == "ASSESSMENT":
                    target_status = ApplicationLifecycleStatus.ASSESSMENT
                elif c_state == "INTERVIEW":
                    target_status = ApplicationLifecycleStatus.INTERVIEW
                elif c_state == "OFFER":
                    target_status = ApplicationLifecycleStatus.OFFER
                elif c_state == "REJECTED":
                    target_status = ApplicationLifecycleStatus.REJECTED
                elif c_state == "WITHDRAWN":
                    target_status = ApplicationLifecycleStatus.WITHDRAWN
                else:
                    target_status = status_map.get(db_app.status, ApplicationLifecycleStatus.DISCOVERED)

                comp_display = normalize_company_display(db_app.company)

                if job_id in app_by_job:
                    existing = app_by_job[job_id]
                    if db_app.application_id:
                        existing.application_id = db_app.application_id
                    existing.company = comp_display
                    if db_app.role:
                        existing.role = db_app.role
                    if db_app.source:
                        existing.source = db_app.source
                    if db_app.canonical_job_url:
                        existing.canonical_job_url = db_app.canonical_job_url
                    existing.current_status = target_status
                    if target_status == ApplicationLifecycleStatus.SUBMITTED:
                        existing.submitted_at = db_app.submitted_at or db_app.applied_at or utc_now()
                    elif target_status == ApplicationLifecycleStatus.SUBMISSION_UNVERIFIED:
                        existing.submitted_at = None
                elif db_app.application_id in app_by_id:
                    existing = app_by_id[db_app.application_id]
                    existing.company = comp_display
                    if db_app.role:
                        existing.role = db_app.role
                    if db_app.source:
                        existing.source = db_app.source
                    if db_app.canonical_job_url:
                        existing.canonical_job_url = db_app.canonical_job_url
                    existing.current_status = target_status
                    if target_status == ApplicationLifecycleStatus.SUBMITTED:
                        existing.submitted_at = db_app.submitted_at or db_app.applied_at or utc_now()
                    elif target_status == ApplicationLifecycleStatus.SUBMISSION_UNVERIFIED:
                        existing.submitted_at = None
                else:
                    canonical_meta = self.copilot_service.orchestrator.discovery_service.store.get_canonical_job(job_id)
                    rec = ApplicationRecord(
                        application_id=db_app.application_id or f"app-{uuid.uuid4().hex[:8]}",
                        job_id=job_id,
                        company=comp_display,
                        role=db_app.role or (canonical_meta.title if canonical_meta else "Role unavailable"),
                        canonical_job_url=db_app.canonical_job_url or (canonical_meta.canonical_url or canonical_meta.source_url if canonical_meta else None),
                        source=db_app.source or (canonical_meta.source if canonical_meta else "Source unavailable"),
                        discovered_at=db_app.discovered_at or db_app.created_at,
                        prepared_at=db_app.prepared_at,
                        submitted_at=db_app.submitted_at if target_status == ApplicationLifecycleStatus.SUBMITTED else None,
                        current_status=target_status,
                        current_status_at=db_app.current_status_at or db_app.updated_at or utc_now(),
                        resume_strategy=ResumeStrategy.normalize(db_app.resume_strategy),
                        match_score=db_app.match_score or 0.0,
                        recommendation=db_app.recommendation or "UNKNOWN",
                        user_notes=db_app.user_notes or [],
                        created_at=db_app.created_at or utc_now(),
                        updated_at=db_app.updated_at or utc_now(),
                    )
                    tracking_apps.append(rec)
                    app_by_job[job_id] = rec
                    app_by_id[rec.application_id] = rec

            if status:
                stat_val = status.value if hasattr(status, "value") else str(status)
                tracking_apps = [a for a in tracking_apps if a.current_status.value == stat_val or a.current_status == status]
            if strategy:
                tracking_apps = [a for a in tracking_apps if a.resume_strategy == strategy]

            return tracking_apps
        finally:
            if should_close:
                db.close()

    # ==========================================================================
    # 6. Analytics, Sources, Sessions, Activity, Artifacts
    # ==========================================================================

    def get_analytics(self, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Fetch Phase 8 analytics dashboard with strict N < 10 sample size labeling."""
        dashboard = self.tracking_service.get_analytics_dashboard(from_date=from_date, to_date=to_date)
        return dashboard.model_dump()

    def get_sources(self) -> List[SourceMonitoringItem]:
        """Fetch operational monitoring metadata for configured sources."""
        health_reports = self.copilot_service.get_sources_health()
        sources_list = self.copilot_service.get_sources()
        source_map = {getattr(s, "id", getattr(s, "source", "")): s for s in sources_list}

        db, should_close = self._get_db_session()
        try:
            session_mgr = AuthenticatedSessionManager(db=db)
            active_sessions = {s.source.lower(): s for s in session_mgr.list_sessions()}

            items: List[SourceMonitoringItem] = []
            for hr in health_reports:
                src_obj = source_map.get(hr.source_id)
                auth_sess = active_sessions.get(hr.source_id.lower())
                has_active = auth_sess is not None and getattr(getattr(auth_sess, "status", None), "value", "") == "ACTIVE"

                items.append(
                    SourceMonitoringItem(
                        source_name=hr.source_id,
                        display_name=hr.name or (src_obj.display_name if src_obj else hr.source_id.title()),
                        enabled=hr.enabled,
                        discovery_mode=getattr(hr.discovery_mode, "value", str(hr.discovery_mode)),
                        health_status=getattr(hr.state, "value", str(hr.state)),
                        last_run_at=hr.last_checked_at,
                        last_error=hr.message,
                        requires_login=hr.requires_login,
                        has_active_session=has_active,
                        session_status=auth_sess.status.value if auth_sess else None,
                    )
                )
            return items
        finally:
            if should_close:
                db.close()

    def get_sessions(self) -> List[SessionMetadataItem]:
        """Fetch safe metadata for authenticated source sessions (Zero cookies/tokens)."""
        db, should_close = self._get_db_session()
        try:
            session_mgr = AuthenticatedSessionManager(db=db)
            sessions = session_mgr.list_sessions()
            return [
                SessionMetadataItem(
                    id=s.id,
                    session_id=s.session_id,
                    source=s.source,
                    status=s.status,
                    has_stored_state=session_mgr.session_store.has_session_state(s.session_id),
                    created_at=s.created_at,
                    last_verified_at=s.last_verified_at,
                    expires_at=s.expires_at,
                    metadata=s.metadata_json,
                )
                for s in sessions
            ]
        finally:
            if should_close:
                db.close()

    def get_activity_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve sanitized chronological system events."""
        db, should_close = self._get_db_session()
        try:
            events = db.query(ApplicationEventModel).order_by(ApplicationEventModel.timestamp.desc()).limit(limit).all()
            return [
                {
                    "event_id": e.event_id,
                    "application_id": e.application_id,
                    "job_id": e.job_id,
                    "event_type": e.event_type,
                    "source": e.source,
                    "notes": e.notes,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                }
                for e in events
            ]
        finally:
            if should_close:
                db.close()

    def get_artifact_content(self, artifact_id: str) -> Tuple[bytes, str, str]:
        """
        Fetch binary artifact data, content type, and filename safely.
        """
        data, meta = self.artifact_service.get_artifact(artifact_id)
        filename = meta.original_filename or f"{artifact_id}.bin"
        return data, meta.content_type, filename

    def get_application_resume_pdf(self, application_id: str) -> Tuple[bytes, str, str]:
        """Fetch binary PDF for an application resume for inline viewing or download with canonical filename."""
        db, should_close = self._get_db_session()
        try:
            self._ensure_curated_job_exists(db, application_id)
            app_repo = ApplicationRepository(db)
            app = app_repo.get_by_application_id(application_id) or app_repo.get_by_job_id_str(application_id)
            job_id = app.job_id_str if app and app.job_id_str else application_id

            job_repo = JobRepository(db)
            db_job = job_repo.get_by_job_id(job_id) if job_id else None

            # Canonical deterministic download filename
            raw_c = app.company if app and app.company else (db_job.company if db_job else "Company")
            clean_company = normalize_company_display(raw_c)
            clean_role = app.role if app and app.role else (db_job.title if db_job else "Software_Engineer")
            
            clean_company = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in clean_company.replace(" ", "_"))
            clean_role = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in clean_role.replace(" ", "_"))
            canonical_filename = f"Kulmeet_Singh_{clean_company}_{clean_role}.pdf"

            # 1. Check Phase 10A Artifacts
            artifacts = self.artifact_service.list_artifacts(application_id=application_id, job_id=job_id)
            for art in artifacts:
                if art.artifact_type.value == "TAILORED_RESUME_PDF" or art.content_type == "application/pdf":
                    data, meta = self.artifact_service.get_artifact(art.artifact_id)
                    return data, "application/pdf", canonical_filename

            # 2. Check application package or generated output
            pkg = self.prep_service.get_application_package(job_id)
            if not pkg or not pkg.resume_pdf_path or not Path(pkg.resume_pdf_path).exists():
                try:
                    pkg = self.prep_service.prepare_application(job_id, db_session=db)
                except Exception as prep_e:
                    logger.debug(f"On-demand prep during PDF fetch notice: {prep_e}")

            if pkg and pkg.resume_pdf_path and Path(pkg.resume_pdf_path).exists():
                data = Path(pkg.resume_pdf_path).read_bytes()
                return data, "application/pdf", canonical_filename

            # 3. Check strategy default generated path with locked strategy whitelist
            LOCKED_STRATEGIES = {"backend_java", "cloud_devops", "data_engineering", "full_stack", "sre_devops"}
            strat = pkg.selected_resume_strategy if (pkg and pkg.selected_resume_strategy in LOCKED_STRATEGIES) else "backend_java"
            if strat not in LOCKED_STRATEGIES:
                strat = "backend_java"

            pdf_path = Path(f"data/generated/{strat}/latest.pdf")
            if pdf_path.exists():
                return pdf_path.read_bytes(), "application/pdf", canonical_filename

            # 4. Check if tex exists and compile on demand
            tex_path = Path(f"data/generated/{strat}/latest.tex")
            if tex_path.exists():
                from job_copilot.resume.renderer import LaTeXResumeRenderer
                renderer = LaTeXResumeRenderer()
                compiled_path, err, _ = renderer.compile_pdf(tex_path)
                if compiled_path and compiled_path.exists():
                    return compiled_path.read_bytes(), "application/pdf", canonical_filename

            raise FileNotFoundError(f"Compiled PDF not found for application '{application_id}'.")
        finally:
            if should_close:
                db.close()

    def retry_submission(
        self,
        application_id: str,
        payload: RetrySubmissionPayload,
    ) -> ApplicationDetailResponse:
        """
        Safe retry action for SUBMISSION_UNVERIFIED applications.
        Requires explicit acknowledgement of duplicate application risk.
        Generates a fresh confirmation token and transitions task to READY_FOR_REVIEW.
        Does NOT automatically submit; requires human confirmation with 'SUBMIT'.
        For historical Mastercard record (app-usr-2a43a63d): Blocked from automated retry.
        """
        if not payload.acknowledge_duplicate_risk:
            raise ValueError("Explicit acknowledgement of duplicate application risk is required to retry.")

        # Historical Mastercard record is non-retryable
        if application_id == "app-usr-2a43a63d":
            raise ValueError("Historical unverified Mastercard record cannot be automatically retried. Manual employer portal review is required.")

        db, should_close = self._get_db_session()
        try:
            app_repo = ApplicationRepository(db)
            app = app_repo.get_by_application_id(application_id) or app_repo.get_by_job_id_str(application_id)
            if not app:
                raise ValueError(f"Application '{application_id}' not found.")

            task_repo = BrowserTaskRepository(db)
            task = task_repo.get_by_application_or_job_id(
                application_id=app.application_id,
                job_id=app.job_id_str,
            )
            if not task:
                raise ValueError(f"No browser task found for application '{application_id}'.")

            if task.status != BrowserTaskStatus.SUBMISSION_UNVERIFIED and app.status != ApplicationStatus.APPLIED:
                raise ValueError(f"Application is in status '{task.status.value}', only SUBMISSION_UNVERIFIED applications can be retried.")

            # Generate a fresh confirmation token and transition back to READY_FOR_REVIEW
            fresh_token = f"tok-retry-{uuid.uuid4().hex[:8]}"
            task.confirmation_token = fresh_token
            task.confirmation_expires_at = utc_now() + timedelta(minutes=30)
            task_repo.update_status(task.task_id, BrowserTaskStatus.READY_FOR_REVIEW, pause_reason=None)
            
            # Reset application status to READY_TO_APPLY
            app.status = ApplicationStatus.READY_TO_APPLY
            
            note = f"Submission retry authorized by operator. Fresh confirmation token generated. Risk acknowledged: {payload.user_notes or 'Duplicate risk acknowledged'}"
            app_repo.append_event(
                application_id=app.application_id,
                job_id=app.job_id_str or application_id,
                event_type="READY_FOR_REVIEW",
                event_id=f"evt-retry-{uuid.uuid4().hex[:8]}",
                source="DASHBOARD_OPERATOR",
                notes=note,
            )
            task_repo.append_audit_event(
                task.task_id,
                {
                    "event": "submission_retry_initiated",
                    "timestamp": utc_now().isoformat(),
                    "fresh_token_prefix": fresh_token[:12],
                    "duplicate_risk_acknowledged": True,
                }
            )
            db.commit()

            return self.get_application_detail(application_id)
        finally:
            if should_close:
                db.close()

    # ==========================================================================
    # 7. User-Submitted Job Opportunities ("Found a job yourself?")
    # ==========================================================================

    @staticmethod
    def validate_user_submitted_url(url: str) -> str:
        """
        Validate that target URL has a safe HTTP/HTTPS scheme, valid hostname,
        and is not pointing to private/internal/local addresses (SSRF prevention).
        """
        if not url or not isinstance(url, str):
            raise ValueError("Target URL must be a non-empty string.")

        clean_url = url.strip()
        parsed = urlparse(clean_url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            raise ValueError("Disallowed URL scheme. Only HTTP and HTTPS are permitted.")

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ValueError("Target URL has no valid hostname.")

        # Check IP literal directly (IPv4 and IPv6)
        try:
            ip_obj = ipaddress.ip_address(hostname.strip("[]"))
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
                or ip_obj.is_unspecified
            ):
                raise ValueError("Unsafe URL: Local and private network addresses are not permitted.")
        except ValueError as ip_err:
            if "Unsafe URL" in str(ip_err):
                raise
            # Hostname is a domain name, proceed to domain checks

        # SSRF Safeguards: reject loopback, internal, metadata, and private hostnames
        blocked_hosts = {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
            "test.local",
            "metadata.google.internal",
            "instance-data",
        }
        if (
            hostname in blocked_hosts
            or hostname.startswith("127.")
            or hostname.startswith("10.")
            or hostname.startswith("192.168.")
            or hostname.startswith("169.254.")
            or hostname.endswith(".local")
            or hostname.endswith(".internal")
            or hostname.endswith(".localhost")
        ):
            raise ValueError("Unsafe URL: Local and private network addresses are not permitted.")

        # Reject private IPv4 range 172.16.0.0 - 172.31.255.255
        if hostname.startswith("172."):
            parts = hostname.split(".")
            if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
                raise ValueError("Unsafe URL: Private network addresses are not permitted.")

        # Validate domain structure (must contain a valid dot)
        if "." not in hostname or hostname.endswith("."):
            raise ValueError("This job site isn't currently supported for automated processing.")

        return clean_url

    def analyze_user_submitted_url(self, raw_url: str) -> AnalyzeOpportunityResponse:
        """
        Ingest and process a candidate-submitted opportunity URL through the pipeline:
        1. Validate URL and safe navigation target (SSRF prevention).
        2. Fetch JD content via UrlJobSource.
        3. Normalize & check deduplication against existing jobs.
        4. Evaluate JD against Candidate Truth (7 dimensions) via JobIntelligenceService.
        5. Prioritize and register in Tracking and Copilot Queue.
        6. Prepare application package, tailor resume (Phase 3 strategy), and store artifacts.
        7. Stage in READY_FOR_REVIEW without automated submission.
        """
        clean_url = self.validate_user_submitted_url(raw_url)

        db, should_close = self._get_db_session()
        try:
            # 1. Fetch raw job description
            url_source = UrlJobSource(name="user_submitted_url")
            raw_job = url_source.fetch(clean_url)
            if not raw_job or not raw_job.raw_description or len(raw_job.raw_description.strip()) < 20:
                raise ValueError("Couldn't reliably read this job posting.")

            raw_job.source = "user_submitted_url"
            raw_job.source_url = clean_url

            # 2. Normalize and Deduplicate
            normalizer = JobNormalizer()
            canonical = normalizer.normalize(raw_job)
            canonical.source = "user_submitted_url"
            canonical.source_url = clean_url

            deduplicator = JobDeduplicator()
            existing_jobs = self.copilot_service.orchestrator.discovery_service.store.list_canonical_jobs(include_duplicates=True)
            is_dup, canonical_id, reason = deduplicator.check_duplicate(canonical, existing_jobs)

            if is_dup and canonical_id:
                logger.info(f"User-submitted URL '{clean_url}' is DUPLICATE of '{canonical_id}' ({reason})")
                existing_canonical = self.copilot_service.orchestrator.discovery_service.store.get_canonical_job(canonical_id)
                existing_copilot_job = self.copilot_service.get_job(canonical_id)

                company = normalize_company_display(existing_canonical.company if existing_canonical else (existing_copilot_job.company if existing_copilot_job else canonical.company))
                title = existing_canonical.title if existing_canonical else (existing_copilot_job.title if existing_copilot_job else canonical.title)
                location = existing_canonical.location if existing_canonical else (existing_copilot_job.location if existing_copilot_job else canonical.location)
                match_score = existing_copilot_job.match_score if existing_copilot_job and existing_copilot_job.match_score is not None else 0.0
                recommendation = existing_copilot_job.recommendation_tier if existing_copilot_job else "CONSIDER"
                priority_band = existing_copilot_job.priority_band.value if existing_copilot_job and hasattr(existing_copilot_job.priority_band, "value") else "MEDIUM"
                priority_score = existing_copilot_job.priority_score if existing_copilot_job else 50.0
                selected_strat = existing_copilot_job.selected_strategy if existing_copilot_job else None

                app_repo = ApplicationRepository(db)
                existing_app = app_repo.get_by_job_id_str(canonical_id)
                tracking_app = self.tracking_service.get_application_by_job_id(canonical_id)
                app_id = existing_app.application_id if existing_app else (tracking_app.application_id if tracking_app else None)

                # Ensure application package exists and get actual needs_input count
                pkg = self.prep_service.get_application_package(canonical_id)
                if not pkg:
                    pkg = self.prep_service.prepare_application(job_id_or_text=canonical_id, db_session=db)

                job_repo = JobRepository(db)
                db_job = job_repo.get_by_job_id(canonical_id)
                if not db_job:
                    db_job = Job(
                        job_id=canonical_id,
                        title=title,
                        company=company,
                        location=location,
                        url=clean_url,
                        canonical_url=clean_url,
                        description=existing_canonical.clean_description if existing_canonical else "",
                        source="user_submitted_url",
                        lifecycle_status="RECOMMENDED",
                    )
                    db.add(db_job)
                    db.commit()
                    db.refresh(db_job)

                if not existing_app:
                    app_id = app_id or f"app-usr-{uuid.uuid4().hex[:8]}"
                    existing_app = Application(
                        application_id=app_id,
                        job_id=db_job.id if db_job else None,
                        job_id_str=canonical_id,
                        company=company,
                        role=title,
                        source="user_submitted_url",
                        canonical_job_url=clean_url,
                        status=ApplicationStatus.READY_TO_APPLY,
                        match_score=match_score,
                        resume_strategy=pkg.selected_resume_strategy if pkg else selected_strat,
                        prepared_at=utc_now(),
                        user_notes=["Added by candidate via dashboard."],
                    )
                    db.add(existing_app)
                    db.commit()
                    db.refresh(existing_app)

                needs_cnt = len(pkg.user_inputs_required) if pkg else 0

                return AnalyzeOpportunityResponse(
                    job_id=canonical_id,
                    application_id=app_id,
                    company=company,
                    title=title,
                    location=location,
                    canonical_url=clean_url,
                    source="user_submitted_url",
                    match_score=match_score,
                    recommendation=recommendation,
                    priority_band=priority_band,
                    priority_score=priority_score,
                    selected_strategy=selected_strat,
                    strengths=existing_copilot_job.recommendation.strengths if existing_copilot_job and existing_copilot_job.recommendation else [],
                    gaps=existing_copilot_job.explanation.why_not_apply if existing_copilot_job and existing_copilot_job.explanation else [],
                    risks=existing_copilot_job.risk_flags if existing_copilot_job else [],
                    is_duplicate=True,
                    duplicate_of_id=canonical_id,
                    status="READY_FOR_REVIEW",
                    resume_download_url=f"/api/dashboard/applications/{app_id or canonical_id}/resume/pdf",
                    supports_browser_prep=False,
                    has_active_session=False,
                    needs_user_input_count=needs_cnt,
                    message="This opportunity is already in Job Copilot.",
                )

            # 3. Save raw & canonical job in store
            self.copilot_service.orchestrator.discovery_service.store.save_raw_job(canonical.job_id, raw_job)
            self.copilot_service.orchestrator.discovery_service.store.save_canonical_job(canonical)

            # 4. Process through Copilot pipeline (JobIntelligence, Tracking, Prioritization, Queue)
            copilot_job = self.copilot_service.process_job(canonical.job_id)

            # 5. Create/update database Job record
            job_repo = JobRepository(db)
            db_job = job_repo.get_by_job_id(canonical.job_id)
            if not db_job:
                db_job = Job(
                    job_id=canonical.job_id,
                    title=canonical.title,
                    company=normalize_company_display(canonical.company),
                    location=canonical.location,
                    url=clean_url,
                    canonical_url=canonical.canonical_url or clean_url,
                    description=canonical.clean_description,
                    source="user_submitted_url",
                    lifecycle_status="RECOMMENDED",
                )
                db.add(db_job)
                db.commit()
                db.refresh(db_job)

            # 6. Prepare Application Package (Phase 3 Resume Tailoring, Cover Letter, Q&A)
            pkg = self.prep_service.prepare_application(job_id_or_text=canonical.job_id, db_session=db)

            app_repo = ApplicationRepository(db)
            app_model = app_repo.get_by_job_id_str(canonical.job_id)
            if not app_model:
                tracking_app = self.tracking_service.get_application_by_job_id(canonical.job_id)
                app_id = tracking_app.application_id if tracking_app else f"app-usr-{uuid.uuid4().hex[:8]}"
                app_model = Application(
                    application_id=app_id,
                    job_id=db_job.id if db_job else None,
                    job_id_str=canonical.job_id,
                    company=normalize_company_display(canonical.company),
                    role=canonical.title,
                    source="user_submitted_url",
                    canonical_job_url=clean_url,
                    status=ApplicationStatus.READY_TO_APPLY,
                    match_score=copilot_job.match_score if copilot_job else None,
                    resume_strategy=pkg.selected_resume_strategy,
                    prepared_at=utc_now(),
                    user_notes=["Added by candidate via dashboard."],
                )
                db.add(app_model)
                db.commit()
                db.refresh(app_model)
                app_repo.append_event(
                    application_id=app_model.application_id,
                    job_id=canonical.job_id,
                    event_type="DISCOVERED",
                    event_id=f"evt-usr-disc-{uuid.uuid4().hex[:8]}",
                    source="user_submitted_url",
                    notes="Opportunity submitted by candidate.",
                )
                app_repo.append_event(
                    application_id=app_model.application_id,
                    job_id=canonical.job_id,
                    event_type="PREPARED",
                    event_id=f"evt-usr-prep-{uuid.uuid4().hex[:8]}",
                    source="user_submitted_url",
                    notes=f"Application prepared with strategy '{pkg.selected_resume_strategy}'.",
                )

            # 7. Store artifacts in Object Storage & PostgreSQL metadata
            if pkg.resume_tex_path and Path(pkg.resume_tex_path).exists():
                tex_data = Path(pkg.resume_tex_path).read_bytes()
                try:
                    self.artifact_service.store_artifact(
                        data=tex_data,
                        artifact_type=ArtifactType.TAILORED_RESUME_TEX,
                        application_id=app_model.application_id,
                        job_id=canonical.job_id,
                        original_filename=f"resume_{canonical.job_id}.tex",
                        content_type="application/x-tex",
                    )
                except Exception as e:
                    logger.warning(f"Failed to store tex artifact: {e}")

            if pkg.resume_pdf_path and Path(pkg.resume_pdf_path).exists():
                pdf_data = Path(pkg.resume_pdf_path).read_bytes()
                try:
                    self.artifact_service.store_artifact(
                        data=pdf_data,
                        artifact_type=ArtifactType.TAILORED_RESUME_PDF,
                        application_id=app_model.application_id,
                        job_id=canonical.job_id,
                        original_filename=f"resume_{canonical.job_id}.pdf",
                        content_type="application/pdf",
                    )
                except Exception as e:
                    logger.warning(f"Failed to store pdf artifact: {e}")

            # 8. Create BrowserTask in QUEUED state (awaiting browser worker execution)
            task_repo = BrowserTaskRepository(db)
            browser_task = task_repo.get_by_application_or_job_id(
                application_id=app_model.application_id,
                job_id=canonical.job_id,
            )
            if not browser_task:
                task_id = f"task-usr-{uuid.uuid4().hex[:8]}"
                review_pkg_json = {
                    "detected_fields": [a.question_text for a in pkg.answers],
                    "filled_fields": [a.question_text for a in pkg.answers if not a.requires_user_input],
                    "unresolved_fields": [u.question_text for u in pkg.user_inputs_required],
                    "warnings": [],
                }
                browser_task = BrowserTaskModel(
                    task_id=task_id,
                    application_id=app_model.application_id,
                    job_id=canonical.job_id,
                    source="user_submitted_url",
                    target_url=clean_url,
                    status=BrowserTaskStatus.QUEUED,
                    confirmation_token=None,
                    confirmation_expires_at=None,
                    review_package_json=review_pkg_json,
                )
                task_repo.create(browser_task)

            # 9. Check browser adapter and active authenticated session
            session_mgr = AuthenticatedSessionManager(db)
            hostname = (urlparse(clean_url).hostname or "").lower()
            source_type = "generic"
            if "linkedin.com" in hostname:
                source_type = "linkedin"
            elif "naukri.com" in hostname:
                source_type = "naukri"
            elif "instahyre.com" in hostname:
                source_type = "instahyre"
            elif "greenhouse.io" in hostname:
                source_type = "greenhouse"
            elif "lever.co" in hostname:
                source_type = "lever"
            elif "workday.com" in hostname:
                source_type = "workday"
            elif "ashbyhq.com" in hostname:
                source_type = "ashby"

            has_active_session = bool(session_mgr.get_session(source_type))
            supports_browser = source_type in ["linkedin", "naukri", "instahyre", "greenhouse", "lever", "workday", "ashby", "generic"]

            strengths = copilot_job.recommendation.strengths if copilot_job and copilot_job.recommendation else []
            gaps = copilot_job.explanation.why_not_apply if copilot_job and copilot_job.explanation else []
            risks = copilot_job.risk_flags if copilot_job else []

            return AnalyzeOpportunityResponse(
                job_id=canonical.job_id,
                application_id=app_model.application_id,
                company=normalize_company_display(canonical.company),
                title=canonical.title,
                location=canonical.location,
                canonical_url=clean_url,
                source="user_submitted_url",
                match_score=copilot_job.match_score if copilot_job and copilot_job.match_score is not None else 0.0,
                recommendation=copilot_job.recommendation_tier if copilot_job else "APPLY",
                priority_band=copilot_job.priority_band.value if copilot_job and hasattr(copilot_job.priority_band, "value") else "HIGH",
                priority_score=copilot_job.priority_score if copilot_job else 75.0,
                selected_strategy=pkg.selected_resume_strategy,
                strengths=strengths,
                gaps=gaps,
                risks=risks,
                is_duplicate=False,
                duplicate_of_id=None,
                status="READY_FOR_REVIEW",
                resume_download_url=f"/api/dashboard/applications/{app_model.application_id}/resume/pdf",
                supports_browser_prep=supports_browser,
                has_active_session=has_active_session,
                needs_user_input_count=len(pkg.user_inputs_required),
                message="Opportunity successfully analyzed and prepared for review.",
            )
        finally:
            if should_close:
                db.close()

    # ==========================================================================
    # 7. Local Interactive Browser Agent Devices
    # ==========================================================================

    def generate_device_pairing_code(
        self, device_name: str = "Local Browser Agent", server_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a short-lived 6-digit pairing code for connecting a local browser agent."""
        db, should_close = self._get_db_session()
        try:
            device_repo = DeviceRepository(db)
            device, code = device_repo.generate_pairing_code(device_name=device_name, validity_minutes=10)
            server_str = (server_url or "https://job-copilot-x3kc.onrender.com").rstrip("/")
            cli_cmd = f"python -m job_copilot.browser_agent pair {code} --server {server_str}"
            return {
                "device_id": device.device_id,
                "pairing_code": code,
                "expires_at": device.pairing_expires_at.isoformat() if device.pairing_expires_at else "",
                "server_url": server_str,
                "instructions": f"Run `{cli_cmd}` on your machine.",
                "cli_command": cli_cmd,
            }
        finally:
            if should_close:
                db.close()

    def list_paired_devices(self) -> List[Dict[str, Any]]:
        """List all paired local browser agent devices and their connectivity state."""
        db, should_close = self._get_db_session()
        try:
            device_repo = DeviceRepository(db)
            devices = device_repo.list_devices()
            now = datetime.now(timezone.utc)
            results = []
            for d in devices:
                is_active = False
                if d.last_seen_at and d.status.value in ("CONNECTED", "BUSY"):
                    is_active = (now - d.last_seen_at.replace(tzinfo=timezone.utc if d.last_seen_at.tzinfo is None else d.last_seen_at.tzinfo)).total_seconds() < 60

                results.append({
                    "device_id": d.device_id,
                    "device_name": d.device_name,
                    "status": d.status.value,
                    "is_active": is_active,
                    "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
                    "capabilities": d.capabilities or [],
                    "agent_version": d.agent_version or "1.0.0",
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                })
            return results
        finally:
            if should_close:
                db.close()

    def revoke_device(self, device_id: str) -> bool:
        """Revoke pairing and authorization for a local browser agent device."""
        db, should_close = self._get_db_session()
        try:
            device_repo = DeviceRepository(db)
            return device_repo.revoke_device(device_id)
        finally:
            if should_close:
                db.close()



