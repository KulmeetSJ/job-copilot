"""High-level Dashboard Service coordinating human review, queue, match evidence, and control workflows."""

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.matching.models import JobAssessment, MatchClassification
from job_copilot.models.application import Application, ApplicationEventModel
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.job import Job
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.schemas.dashboard import (
    ApplicationDetailResponse,
    ApplicationTimelineEvent,
    ArtifactSummaryItem,
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
from job_copilot.tracking.models import ApplicationLifecycleStatus
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


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
        self.copilot_service = copilot_service or CopilotService()
        self.tracking_service = tracking_service or TrackingService()
        self.prep_service = prep_service or ApplicationPrepService()
        self.intelligence_service = intelligence_service or JobIntelligenceService()
        self.artifact_service = artifact_service or ArtifactService(db=db)

    def _get_db_session(self) -> Tuple[Session, bool]:
        """Resolve database session and ownership flag."""
        if self._db is not None:
            return self._db, False
        gen = get_db()
        return next(gen), True

    # ==========================================================================
    # 1. Overview & Metrics
    # ==========================================================================

    def get_overview(self) -> DashboardOverviewResponse:
        """Aggregate high-level metrics, pipeline stages, and active queues."""
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

            # 2. Pipeline counts from TrackingService & Applications
            app_repo = ApplicationRepository(db)
            tracked_apps = app_repo.list_applications()
            
            # Browser task review inspection
            task_repo = BrowserTaskRepository(db)
            ready_tasks = task_repo.list_by_status(BrowserTaskStatus.READY_FOR_REVIEW)
            awaiting_confirm_cnt = len(ready_tasks)

            # Stage counts
            pipeline_counts = PipelineCounts(
                discovered=sum(1 for a in tracked_apps if a.status == ApplicationStatus.DISCOVERED),
                recommended=sum(1 for a in tracked_apps if a.status == ApplicationStatus.SHORTLISTED),
                prepared=sum(1 for a in tracked_apps if a.status == ApplicationStatus.PREPARING),
                ready_for_review=sum(1 for a in tracked_apps if a.status == ApplicationStatus.READY_TO_APPLY) or awaiting_confirm_cnt,
                needs_user_input=awaiting_confirm_cnt,
                awaiting_confirmation=awaiting_confirm_cnt,
                submitted=sum(1 for a in tracked_apps if a.status == ApplicationStatus.APPLIED),
                recruiter_response=sum(1 for a in tracked_apps if a.status == ApplicationStatus.OA),
                interview=sum(1 for a in tracked_apps if a.status == ApplicationStatus.INTERVIEW),
                offer=sum(1 for a in tracked_apps if a.status == ApplicationStatus.OFFER),
                rejected=sum(1 for a in tracked_apps if a.status == ApplicationStatus.REJECTED),
                withdrawn=sum(1 for a in tracked_apps if a.status == ApplicationStatus.WITHDRAWN),
            )

            # 3. Source & Session health
            source_reports = self.copilot_service.get_sources_health()
            active_sources = sum(1 for s in source_reports if getattr(s, "enabled", True))
            healthy_sources = sum(1 for s in source_reports if getattr(getattr(s, "state", None), "value", str(getattr(s, "state", ""))) in ("HEALTHY", "ACTIVE"))

            session_mgr = AuthenticatedSessionManager(db=db)
            auth_sessions = session_mgr.list_sessions()
            authenticated_cnt = sum(1 for s in auth_sessions if s.status.value == "ACTIVE")

            # 4. Recent activity (last 10 events)
            events = db.query(ApplicationEventModel).order_by(ApplicationEventModel.timestamp.desc()).limit(10).all()
            recent_activity = [
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

            return DashboardOverviewResponse(
                queue_counts=queue_counts,
                pipeline_counts=pipeline_counts,
                recent_submissions_count=pipeline_counts.submitted,
                active_sources_count=active_sources,
                healthy_sources_count=healthy_sources,
                authenticated_sessions_count=authenticated_cnt,
                recent_activity=recent_activity,
                timestamp=utc_now(),
            )
        finally:
            if should_close:
                db.close()

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

            matched_skills: List[str] = []
            major_gaps: List[str] = []
            primary_reason = None

            if j.recommendation:
                matched_skills = j.recommendation.strengths[:5]
                major_gaps = j.recommendation.risks[:3]
                if j.recommendation.reasons:
                    primary_reason = j.recommendation.reasons[0]
            elif j.explanation:
                matched_skills = j.explanation.why_apply[:5]
                major_gaps = j.explanation.why_not_apply[:3]

            items.append(
                DashboardQueueItem(
                    job_id=j.job_id,
                    company=j.company,
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
                    application_status=j.current_application_status.value if j.current_application_status else None,
                    discovered_at=j.discovered_at,
                )
            )

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
            job_repo = JobRepository(db)
            job_model = job_repo.get_by_job_id(job_id)
            copilot_job = self.copilot_service.get_job(job_id)

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
            rec_strat = "general_swe"
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
                    MatchDimensionScore(dimension_name="Technical Skills", score=sb.technical_score, weight=0.25, description="Evaluation of mandatory and preferred technologies"),
                    MatchDimensionScore(dimension_name="Core Responsibilities", score=sb.responsibility_score, weight=0.20, description="Alignment with day-to-day engineering duties"),
                    MatchDimensionScore(dimension_name="Role & Seniority", score=sb.role_score, weight=0.15, description="Match on title hierarchy and expected engineering level"),
                    MatchDimensionScore(dimension_name="Professional Evidence", score=sb.experience_score, weight=0.15, description="Depth of verified production work history"),
                    MatchDimensionScore(dimension_name="Domain Expertise", score=sb.domain_score, weight=0.10, description="Specialized domain context (e.g. Fintech, Payments, Distributed Systems)"),
                    MatchDimensionScore(dimension_name="Preferences", score=sb.preference_score, weight=0.10, description="Location, remote work policy, and compensation alignment"),
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

            return JobDetailResponse(
                job_id=job_id,
                title=job_model.title if job_model else (copilot_job.title if copilot_job else "Unknown Role"),
                company=job_model.company if job_model else (copilot_job.company if copilot_job else "Unknown Company"),
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
        """
        db, should_close = self._get_db_session()
        try:
            app_repo = ApplicationRepository(db)
            app_model = app_repo.get_by_application_id(application_id)
            if not app_model:
                # Try finding by job_id_str
                app_model = app_repo.get_by_job_id_str(application_id)

            job_id = app_model.job_id_str if app_model and app_model.job_id_str else application_id
            company = app_model.company if app_model and app_model.company else "Target Company"
            role = app_model.role if app_model and app_model.role else "Software Engineer"
            status = app_model.status.value if app_model else "DISCOVERED"
            source = app_model.source if app_model else "unknown"
            canonical_url = app_model.canonical_job_url if app_model else None
            match_score = app_model.match_score if app_model else None
            recommendation = app_model.recommendation if app_model else None
            selected_strat = app_model.resume_strategy if app_model and app_model.resume_strategy else "general_swe"

            # Retrieve prepared package if available
            pkg = self.prep_service.get_application_package(job_id)
            if not pkg and app_model:
                try:
                    # Attempt generation if not yet prepared
                    pkg = self.prep_service.prepare_application(job_id_or_text=job_id)
                except Exception as e:
                    logger.debug(f"Application package generation notice for '{job_id}': {e}")

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

                # Prepared answers
                for ans in pkg.answers:
                    evidence_refs = [p.source_ref for p in ans.provenance] if getattr(ans, "provenance", None) else []
                    prepared_answers.append(
                        PreparedAnswerItem(
                            question_text=ans.question_text,
                            field_name=ans.question_id,
                            field_category=getattr(ans.classification, "value", str(ans.classification)),
                            answer_text=ans.answer or "Pending user input",
                            confidence=ans.confidence,
                            source_evidence=evidence_refs,
                            requires_user_input=ans.requires_user_input,
                            validation_status="VALID",
                        )
                    )

                # User inputs required
                for uir in pkg.user_inputs_required:
                    user_inputs.append(
                        UserInputRequiredItem(
                            question_id=uir.question_id,
                            question_text=uir.question_text,
                            field_type=getattr(uir.expected_type, "value", "text"),
                            current_value=None,
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

            # Browser Worker Review Package
            task_repo = BrowserTaskRepository(db)
            browser_task = task_repo.get_by_application_id(application_id) or task_repo.get_by_application_id(job_id)
            browser_review: Optional[BrowserReviewSummary] = None

            if browser_task:
                rp = browser_task.review_package_json or {}
                detected_cnt = len(rp.get("detected_fields", []))
                filled_cnt = len(rp.get("filled_fields", []))
                unresolved_cnt = len(rp.get("unresolved_fields", []))
                has_ss = bool(rp.get("screenshot_artifact_id") or rp.get("screenshot_path"))

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
                    is_ready_for_review=(browser_task.status == BrowserTaskStatus.READY_FOR_REVIEW),
                    pause_reason=browser_task.pause_reason,
                    failure_reason=browser_task.failure_reason,
                    warnings=rp.get("warnings", []),
                )

            # Timeline Events
            timeline_events: List[ApplicationTimelineEvent] = []
            if app_model and app_model.events:
                for evt in app_model.events:
                    timeline_events.append(
                        ApplicationTimelineEvent(
                            event_id=evt.event_id,
                            event_type=evt.event_type,
                            timestamp=evt.timestamp,
                            source=evt.source,
                            notes=evt.notes,
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
                submitted_at=app_model.submitted_at if app_model else None,
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
            app_repo = ApplicationRepository(db)
            app = app_repo.get_by_application_id(application_id) or app_repo.get_by_job_id_str(application_id)
            job_id = app.job_id_str if app and app.job_id_str else application_id

            # Trigger preparation
            pkg = self.prep_service.prepare_application(
                job_id_or_text=job_id,
                strategy_override=strategy_override,
            )

            # Update application record if existing
            if app:
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

            return self.get_application_detail(application_id)
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
        Stores them in application session state WITHOUT modifying candidate truth files.
        """
        db, should_close = self._get_db_session()
        try:
            app_repo = ApplicationRepository(db)
            app = app_repo.get_by_application_id(application_id) or app_repo.get_by_job_id_str(application_id)
            job_id = app.job_id_str if app and app.job_id_str else application_id

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
                db.commit()

            logger.info(f"Recorded human input for application '{application_id}' (candidate truth untouched).")
            return self.get_application_detail(application_id)
        finally:
            if should_close:
                db.close()

    def confirm_submission(self, payload: SubmissionConfirmPayload) -> SubmissionConfirmResponse:
        """
        Gated submission path delegating directly to the authoritative HumanConfirmationService.
        Enforces confirm_text='SUBMIT' and valid confirmation_token.
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
