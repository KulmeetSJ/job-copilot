import asyncio
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from job_copilot.application.models import ApplicationPackage
from job_copilot.browser.models import BrowserSession, BrowserSessionStatus, SubmissionResult
from job_copilot.copilot.config import CopilotConfig, load_copilot_config
from job_copilot.copilot.explanations import ExplanationEngine
from job_copilot.copilot.learning import HistoricalLearningEngine
from job_copilot.copilot.models import (
    CopilotAction,
    CopilotDashboard,
    CopilotJob,
    CopilotRecommendation,
    HistoricalInsight,
    PriorityBand,
    QueueStatus,
    utc_now,
)
from job_copilot.copilot.prioritizer import OpportunityPrioritizer
from job_copilot.copilot.queue import CopilotQueueStore
from job_copilot.copilot.sources import (
    JobSource,
    JobSourcesConfig,
    SourceHealthReport,
    load_job_sources_config,
)
from job_copilot.copilot.targeting import (
    JobTargetsConfig,
    load_job_targets_config,
)
from job_copilot.ingestion.models import CanonicalJob, DiscoveryQuery, DiscoveryResult
from job_copilot.matching.models import JobAssessment
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.browser_workflow_service import BrowserWorkflowService
from job_copilot.services.discovery_service import DiscoveryService
from job_copilot.services.job_intelligence_service import JobIntelligenceService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.adapter import TrackingAdapter
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def _run_sync(coro_fn):
    """Run an async coroutine factory synchronously, handling existing event loops safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(coro_fn()))
            return future.result()
    else:
        return asyncio.run(coro_fn())


class CopilotOrchestrator:
    """
    Central orchestration coordinator for Phase 9 Continuous Job Copilot.
    Coordinates Phases 4–8 while preserving locked behavior and human decision boundaries.
    """

    def __init__(
        self,
        config: Optional[CopilotConfig] = None,
        discovery_service: Optional[DiscoveryService] = None,
        intelligence_service: Optional[JobIntelligenceService] = None,
        prep_service: Optional[ApplicationPrepService] = None,
        browser_service: Optional[BrowserWorkflowService] = None,
        tracking_service: Optional[TrackingService] = None,
        queue_store: Optional[CopilotQueueStore] = None,
        targets_config: Optional[JobTargetsConfig] = None,
        sources_config: Optional[JobSourcesConfig] = None,
    ):
        self.config = config or load_copilot_config()
        self.discovery_service = discovery_service or DiscoveryService()
        self.intelligence_service = intelligence_service or JobIntelligenceService()
        self.prep_service = prep_service or ApplicationPrepService()
        self.browser_service = browser_service or BrowserWorkflowService(
            application_prep_service=self.prep_service,
            applications_data_dir=self.prep_service.applications_data_dir,
        )
        self.tracking_service = tracking_service or TrackingService(prep_service=self.prep_service)
        self.queue_store = queue_store or CopilotQueueStore()
        self.targets_config = targets_config or load_job_targets_config()
        self.sources_config = sources_config or load_job_sources_config()

        self.prioritizer = OpportunityPrioritizer(config=self.config)
        self.learning_engine = HistoricalLearningEngine(tracking_service=self.tracking_service)
        self.adapter = TrackingAdapter(tracking_service=self.tracking_service)

    def discover_opportunities(self, query: Optional[DiscoveryQuery] = None) -> List[CopilotJob]:
        """
        Continuous discovery orchestration:
        1. Run Phase 5 discovery.
        2. Normalize & deduplicate.
        3. Register DISCOVERED in Phase 8 tracking.
        4. Evaluate with Phase 4 matching.
        5. Register RECOMMENDED in Phase 8 tracking.
        6. Calculate Phase 9 priority & explanations.
        7. Enqueue in Copilot Queue.
        """
        disc_result: DiscoveryResult = self.discovery_service.discover_jobs(query=query)
        processed_jobs: List[CopilotJob] = []

        for job in disc_result.jobs:
            copilot_job = self.process_job(job.job_id)
            if copilot_job:
                processed_jobs.append(copilot_job)

        return processed_jobs

    def process_job(self, job_id: str) -> Optional[CopilotJob]:
        """
        Process a single job ID through matching, prioritization, and queueing.
        Idempotent: updates existing queue entries without creating duplicate events.
        """
        canonical: Optional[CanonicalJob] = self.discovery_service.store.get_canonical_job(job_id)
        if not canonical:
            logger.warning(f"Job '{job_id}' not found in job store.")
            return None

        # 1. Register Phase 5 Discovered in Phase 8 Tracking
        track_rec = self.adapter.on_job_discovered(
            job_id=canonical.job_id,
            company=canonical.company,
            role=canonical.title,
            source=canonical.source,
            canonical_url=canonical.canonical_url or canonical.source_url,
            discovered_at=canonical.discovered_at,
        )

        # 2. Evaluate with Phase 4 Job Intelligence
        assessment: JobAssessment = self.intelligence_service.evaluate_job(
            raw_text=canonical.clean_description,
            company_override=canonical.company,
            title_override=canonical.title,
            source=canonical.source,
            source_url=canonical.source_url,
            save_artifacts=True,
        )

        # 3. Register Phase 4 Recommendation in Phase 8 Tracking
        self.adapter.on_recommendation(job_id=job_id, assessment=assessment)

        # 4. Phase 9 Prioritization & Targeting Context
        strategy_boost = self.learning_engine.get_strategy_boost(assessment.recommended_strategy)
        risk_flags = list(assessment.risks)
        match_score = assessment.score_breakdown.overall_score if assessment.score_breakdown else 0.0
        rec_tier = assessment.recommendation.value

        # Check company targeting preference
        target_info = self.targets_config.get_company_targeting_info(canonical.company)
        company_tier = target_info["tier"] if target_info else None

        priority_score, priority_band, breakdown = self.prioritizer.calculate_priority(
            match_score=match_score,
            recommendation_tier=rec_tier,
            discovered_at=canonical.discovered_at,
            strategy_historical_boost=strategy_boost,
            risk_flags=risk_flags,
            company_tier=company_tier,
        )

        # 5. Phase 9 Explanation Generation
        hist_note = f"Strategy '{assessment.recommended_strategy}' historical boost: +{strategy_boost:.1f} pts" if strategy_boost != 0.0 else None
        targeting_note = f"{target_info['tier_name']}. Reason: {target_info['reason']}" if target_info else None

        explanation = ExplanationEngine.generate_explanation(
            assessment=assessment,
            profile=self.intelligence_service.profile,
            historical_context=hist_note,
            targeting_context=targeting_note,
        )

        # 6. Action Assignment
        if rec_tier in ["STRONG_APPLY", "APPLY"] and priority_band in [PriorityBand.CRITICAL, PriorityBand.HIGH, PriorityBand.MEDIUM]:
            action = CopilotAction.REVIEW
            q_status = QueueStatus.REVIEW
        elif rec_tier == "CONSIDER":
            action = CopilotAction.REVIEW
            q_status = QueueStatus.REVIEW
        elif rec_tier in ["SKIP", "HIGH_RISK"]:
            action = CopilotAction.SKIP
            q_status = QueueStatus.SKIPPED
        else:
            action = CopilotAction.REVIEW
            q_status = QueueStatus.REVIEW

        # Preserve existing queue status if already progressed
        existing_q = self.queue_store.get(job_id)
        if existing_q and existing_q.queue_status not in [QueueStatus.NEW, QueueStatus.REVIEW]:
            q_status = existing_q.queue_status

        recommendation = CopilotRecommendation(
            job_id=job_id,
            action=action,
            priority_band=priority_band,
            priority_score=priority_score,
            reasons=explanation.why_apply,
            strengths=explanation.why_apply,
            risks=explanation.why_not_apply,
            missing_information=explanation.uncertainties,
            historical_context=hist_note,
            evidence_references=explanation.evidence_references,
        )

        now = utc_now()
        if canonical.discovered_at:
            disc_dt = canonical.discovered_at if canonical.discovered_at.tzinfo is not None else canonical.discovered_at.replace(tzinfo=timezone.utc)
            freshness = max(0, (now - disc_dt).days)
        else:
            freshness = 0

        copilot_job = CopilotJob(
            job_id=job_id,
            title=canonical.title,
            company=canonical.company,
            location=canonical.location,
            source=canonical.source,
            canonical_url=canonical.canonical_url or canonical.source_url,
            discovered_at=canonical.discovered_at,
            match_score=match_score,
            recommendation_tier=rec_tier,
            selected_strategy=assessment.recommended_strategy,
            tracking_application_id=track_rec.application_id if track_rec else None,
            current_application_status=track_rec.current_status if track_rec else None,
            queue_status=q_status,
            priority_score=priority_score,
            priority_band=priority_band,
            freshness_days=freshness,
            risk_flags=risk_flags,
            explanation=explanation,
            recommendation=recommendation,
        )

        return self.queue_store.add_or_update(copilot_job)

    def prepare_job(
        self,
        job_id: str,
        custom_questions: Optional[List[Any]] = None,
        strategy_override: Optional[str] = None,
    ) -> ApplicationPackage:
        """
        One-Click Preparation: Reuses Phase 6 application package builder
        and registers PREPARED in Phase 8 tracking.
        """
        package = self.prep_service.prepare_application(
            job_id_or_text=job_id,
            custom_questions=custom_questions,
            strategy_override=strategy_override,
        )

        # Register Phase 6 preparation in Phase 8 Tracking
        self.adapter.on_application_prepared(package=package)

        # Update Copilot Queue Status
        self.queue_store.update_status(
            job_id=job_id,
            new_status=QueueStatus.READY_FOR_REVIEW,
            notes=f"Application prepared with strategy '{package.selected_resume_strategy}'",
        )

        return package

    async def apply_job_async(
        self,
        job_id: str,
        confirmation_token: Optional[str] = None,
        headless: bool = True,
    ) -> Dict[str, Any]:
        """
        Browser Handoff: Calls Phase 7 Browser Workflow Service for interactive inspection/filling.
        Mandatory safety invariants:
        1. Never uses synthetic or fabricated application URLs (example.com, manual.application.portal).
           If no real canonical/source URL is available, fails safely immediately without launching a browser.
        2. Arbitrary non-empty tokens ('x', '123', 'SUBMIT') must NEVER count as confirmation.
           Submission authorization delegates strictly to the canonical HumanConfirmationService.
        3. Real automated submission proceeds ONLY through the canonical hardened path:
           HumanConfirmationService -> BrowserTaskExecutor.execute_submission_task().
        """
        package = self.prep_service.get_application_package(job_id)
        if not package:
            package = self.prepare_job(job_id)

        # Invariant 1: Validate real canonical/source URL (no fabricated/synthetic URLs)
        raw_url = ""
        if package and package.assessment and hasattr(package.assessment, "job") and package.assessment.job:
            raw_url = getattr(package.assessment.job, "source_url", "") or getattr(package.assessment.job, "canonical_url", "") or ""
            raw_url = (raw_url or "").strip()

        if not raw_url and hasattr(self, "discovery_service") and hasattr(self.discovery_service, "store"):
            canonical = self.discovery_service.store.get_canonical_job(job_id)
            if canonical:
                raw_url = (canonical.canonical_url or canonical.source_url or "").strip()

        is_valid_url = (
            bool(raw_url)
            and (raw_url.startswith("http://") or raw_url.startswith("https://") or raw_url.startswith("file://") or raw_url.startswith("/"))
            and "example.com" not in raw_url.lower()
            and "manual.application.portal" not in raw_url.lower()
        )
        if not is_valid_url:
            raise ValueError(f"Submission blocked: Job '{job_id}' has no valid canonical application URL.")
        app_url = raw_url

        # Check Explicit Human Confirmation Token
        if not confirmation_token:
            # Check for existing session or start review session
            session = None
            for sess in self.browser_service._active_sessions.values():
                if sess.job_id == job_id:
                    session = sess
                    break

            if not session:
                session = await self.browser_service.start_session(
                    job_id=job_id,
                    application_url=app_url,
                    headless=headless,
                )
            else:
                session = await self.browser_service.inspect_session(session.session_id)

            # Auto-fill fields if not already filled
            if session.status in [BrowserSessionStatus.CREATED, BrowserSessionStatus.READY_FOR_REVIEW, BrowserSessionStatus.INSPECTING]:
                session = await self.browser_service.fill_session(session.session_id)

            # Register READY_FOR_REVIEW in Phase 8 Tracking
            self.adapter.on_ready_for_review(job_id=job_id, browser_session_id=session.session_id)

            self.queue_store.update_status(
                job_id=job_id,
                new_status=QueueStatus.WAITING_FOR_USER,
                notes="Form filled. Waiting for explicit candidate confirmation before submission.",
            )
            return {
                "status": "SUBMISSION_BLOCKED",
                "reason": "Explicit human confirmation token required before external portal submission.",
                "session_id": session.session_id,
                "review_required": True,
            }

        # Invariants 2 & 3: Delegate authorization exclusively to canonical HumanConfirmationService.
        # Arbitrary strings ("x", "123", "SUBMIT") must NEVER authorize submission.
        from job_copilot.db.database import SessionLocal
        from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
        from job_copilot.browser_worker.models import HumanConfirmationRequest
        from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
        from job_copilot.repositories.application_repository import ApplicationRepository
        from job_copilot.browser_worker.exceptions import SubmissionSafetyError
        from job_copilot.domain.browser_worker_enums import BrowserTaskStatus

        db = SessionLocal()
        try:
            task_repo = BrowserTaskRepository(db)
            task = task_repo.get_by_application_or_job_id(job_id)
            if not task:
                app_repo = ApplicationRepository(db)
                app = app_repo.get_by_job_id_str(job_id) or app_repo.get_by_application_id(job_id)
                if app and app.application_id:
                    task = task_repo.get_by_application_or_job_id(app.application_id)

            if not task:
                raise SubmissionSafetyError(f"Submission blocked: No authorized browser task found for job '{job_id}'.")

            confirm_svc = HumanConfirmationService(db=db)
            req = HumanConfirmationRequest(
                task_id=task.task_id,
                confirmation_token=confirmation_token,
                confirm_text="SUBMIT",
            )
            # Validates single-use token cryptographically via hmac.compare_digest
            # Arbitrary tokens like "x", "yes", "123", "SUBMIT" will fail with SubmissionSafetyError
            confirm_res = confirm_svc.validate_and_confirm(
                task_id=task.task_id,
                request=req,
                application_id=task.application_id,
            )

            # Delegate execution to the hardened BrowserTaskExecutor
            from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
            executor = BrowserTaskExecutor(db=db)
            executed_task = await executor.execute_submission_task(task.task_id)

            success = executed_task.status == BrowserTaskStatus.COMPLETED
            if success:
                self.queue_store.update_status(
                    job_id=job_id,
                    new_status=QueueStatus.SUBMITTED,
                    notes=f"Submitted successfully via canonical hardened path. Ref: {executed_task.submission_reference}",
                )
                self.tracking_service.register_submission(
                    job_id=job_id,
                    package=package,
                )
            return {
                "status": "SUBMITTED" if success else "FAILED",
                "task_id": executed_task.task_id,
                "submission_reference": executed_task.submission_reference,
            }
        finally:
            db.close()

    def apply_job(
        self,
        job_id: str,
        confirmation_token: Optional[str] = None,
        headless: bool = True,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for apply_job_async."""
        return _run_sync(lambda: self.apply_job_async(job_id, confirmation_token, headless))

    def get_dashboard(self) -> CopilotDashboard:
        """Assemble concise daily dashboard."""
        all_jobs = self.queue_store.list_jobs()

        critical_jobs = [j for j in all_jobs if j.priority_band == PriorityBand.CRITICAL and j.queue_status in [QueueStatus.NEW, QueueStatus.REVIEW]]
        high_jobs = [j for j in all_jobs if j.priority_band == PriorityBand.HIGH and j.queue_status in [QueueStatus.NEW, QueueStatus.REVIEW]]
        medium_jobs = [j for j in all_jobs if j.priority_band == PriorityBand.MEDIUM and j.queue_status in [QueueStatus.NEW, QueueStatus.REVIEW]]
        low_jobs = [j for j in all_jobs if j.priority_band == PriorityBand.LOW and j.queue_status in [QueueStatus.NEW, QueueStatus.REVIEW]]
        waiting_jobs = [j for j in all_jobs if j.queue_status in [QueueStatus.WAITING_FOR_USER, QueueStatus.READY_FOR_REVIEW]]

        queue_counts = self.queue_store.get_counts()
        insights = self.learning_engine.analyze_history()

        # Recent outcomes from Phase 8
        funnel = self.tracking_service.get_funnel()
        recent_outcomes = {
            "discovered": funnel.discovered,
            "recommended": funnel.recommended,
            "prepared": funnel.prepared,
            "submitted": funnel.submitted,
            "recruiter_responses": funnel.recruiter_responses,
            "interviews": funnel.interviews,
            "offers": funnel.offers,
            "accepted": funnel.accepted,
        }

        return CopilotDashboard(
            critical_priority_jobs=critical_jobs,
            high_priority_jobs=high_jobs,
            medium_priority_jobs=medium_jobs,
            low_jobs=low_jobs,
            waiting_for_user_jobs=waiting_jobs,
            queue_summary=queue_counts,
            recent_outcomes=recent_outcomes,
            top_historical_insights=insights[:4],
        )

    def get_insights(self) -> List[HistoricalInsight]:
        """Fetch all historical insights."""
        return self.learning_engine.analyze_history()

    def get_targets(self) -> JobTargetsConfig:
        """Fetch candidate job targets and preferences configuration."""
        return self.targets_config

    def get_sources(self, enabled_only: bool = False) -> List[JobSource]:
        """List configured career discovery sources."""
        return self.sources_config.list_sources(enabled_only=enabled_only)

    def get_sources_health(self) -> List[SourceHealthReport]:
        """Fetch operational health reports for all sources."""
        return self.sources_config.get_health_reports()
