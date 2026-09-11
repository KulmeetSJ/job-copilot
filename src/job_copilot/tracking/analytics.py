"""Deterministic Analytics and Funnel Metrics Engine."""

from datetime import datetime
import statistics
from typing import Dict, List, Optional
from job_copilot.tracking.models import (
    AnalyticsDashboard,
    ApplicationEvent,
    ApplicationLifecycleStatus,
    ApplicationRecord,
    CohortMetric,
    ConversionRates,
    FunnelMetrics,
    ResponseTimeMetrics,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

MIN_SAMPLE_SIZE_THRESHOLD = 10


class AnalyticsEngine:
    """Computes funnel, conversion, cohort, and response-time metrics."""

    @classmethod
    def filter_by_date(
        cls,
        applications: List[ApplicationRecord],
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[ApplicationRecord]:
        """Filter applications by creation / submission date range."""
        filtered = []
        for app in applications:
            target_dt = app.submitted_at or app.created_at
            if from_date and target_dt < from_date:
                continue
            if to_date and target_dt > to_date:
                continue
            filtered.append(app)
        return filtered

    @classmethod
    def compute_funnel(
        cls,
        applications: List[ApplicationRecord],
        events: List[ApplicationEvent],
    ) -> FunnelMetrics:
        """Calculate aggregate pipeline stage counts."""
        funnel = FunnelMetrics()

        # Track unique applications that reached each stage
        stage_apps: Dict[ApplicationLifecycleStatus, set] = {
            s: set() for s in ApplicationLifecycleStatus
        }

        for app in applications:
            # 1. Base stages from record fields
            if app.discovered_at or app.application_id:
                stage_apps[ApplicationLifecycleStatus.DISCOVERED].add(app.application_id)
            if app.recommended_at or (app.recommendation and app.recommendation != "UNKNOWN"):
                stage_apps[ApplicationLifecycleStatus.RECOMMENDED].add(app.application_id)
            if app.prepared_at:
                stage_apps[ApplicationLifecycleStatus.PREPARED].add(app.application_id)
            if app.submitted_at:
                stage_apps[ApplicationLifecycleStatus.SUBMITTED].add(app.application_id)

            # 2. Record explicit events
            for e in app.events:
                if e.event_type in stage_apps:
                    stage_apps[e.event_type].add(app.application_id)

            # 3. Record current status
            if app.current_status in stage_apps:
                stage_apps[app.current_status].add(app.application_id)

        # Ingest all global events
        for e in events:
            if e.event_type in stage_apps:
                stage_apps[e.event_type].add(e.application_id)

        funnel.discovered = len(stage_apps[ApplicationLifecycleStatus.DISCOVERED])
        funnel.recommended = len(stage_apps[ApplicationLifecycleStatus.RECOMMENDED])
        funnel.prepared = len(stage_apps[ApplicationLifecycleStatus.PREPARED])
        funnel.ready_for_review = len(stage_apps[ApplicationLifecycleStatus.READY_FOR_REVIEW])
        funnel.submitted = len(stage_apps[ApplicationLifecycleStatus.SUBMITTED])
        funnel.acknowledged = len(stage_apps[ApplicationLifecycleStatus.ACKNOWLEDGED])
        funnel.recruiter_responses = len(stage_apps[ApplicationLifecycleStatus.RECRUITER_RESPONSE])
        funnel.assessments = len(stage_apps[ApplicationLifecycleStatus.ASSESSMENT])
        funnel.interviews = len(stage_apps[ApplicationLifecycleStatus.INTERVIEW])
        funnel.final_rounds = len(stage_apps[ApplicationLifecycleStatus.FINAL_ROUND])
        funnel.offers = len(stage_apps[ApplicationLifecycleStatus.OFFER])
        funnel.accepted = len(stage_apps[ApplicationLifecycleStatus.ACCEPTED])
        funnel.rejected = len(stage_apps[ApplicationLifecycleStatus.REJECTED])
        funnel.withdrawn = len(stage_apps[ApplicationLifecycleStatus.WITHDRAWN])
        funnel.expired = len(stage_apps[ApplicationLifecycleStatus.EXPIRED])
        funnel.closed = len(stage_apps[ApplicationLifecycleStatus.CLOSED])

        return funnel

    @classmethod
    def compute_conversion(cls, funnel: FunnelMetrics) -> ConversionRates:
        """Calculate conversion percentages across the funnel."""
        submitted = funnel.submitted
        discovered = funnel.discovered
        responses = funnel.recruiter_responses
        interviews = funnel.interviews
        offers = funnel.offers
        accepted = funnel.accepted

        app_rate = (submitted / discovered * 100.0) if discovered > 0 else 0.0
        resp_rate = (responses / submitted * 100.0) if submitted > 0 else 0.0
        int_rate = (interviews / submitted * 100.0) if submitted > 0 else 0.0
        off_rate = (offers / submitted * 100.0) if submitted > 0 else 0.0
        acc_rate = (accepted / offers * 100.0) if offers > 0 else 0.0

        is_reliable = submitted >= MIN_SAMPLE_SIZE_THRESHOLD
        warning = None
        if not is_reliable:
            warning = f"Insufficient sample size (N={submitted} < {MIN_SAMPLE_SIZE_THRESHOLD}) for reliable statistical comparison."

        return ConversionRates(
            application_rate=round(app_rate, 2),
            response_rate=round(resp_rate, 2),
            interview_rate=round(int_rate, 2),
            offer_rate=round(off_rate, 2),
            acceptance_rate=round(acc_rate, 2),
            is_statistically_reliable=is_reliable,
            sample_size_warning=warning,
        )

    @classmethod
    def compute_cohort_performance(
        cls,
        applications: List[ApplicationRecord],
        dimension: str,
    ) -> List[CohortMetric]:
        """Group applications by dimension and compute performance."""
        groups: Dict[str, List[ApplicationRecord]] = {}

        for app in applications:
            key = "unknown"
            if dimension == "strategy":
                key = app.resume_strategy or (app.snapshot.resume_strategy if app.snapshot else "unknown")
            elif dimension == "recommendation":
                key = app.recommendation or (app.snapshot.recommendation if app.snapshot else "unknown")
            elif dimension == "source":
                key = app.source or (app.snapshot.job_source if app.snapshot else "unknown")
            elif dimension == "score_bucket":
                score = app.match_score or (app.snapshot.match_score if app.snapshot else 0)
                if score >= 90:
                    key = "90-100"
                elif score >= 80:
                    key = "80-89"
                elif score >= 70:
                    key = "70-79"
                elif score >= 60:
                    key = "60-69"
                elif score >= 50:
                    key = "50-59"
                else:
                    key = "<50"

            if key not in groups:
                groups[key] = []
            groups[key].append(app)

        cohorts: List[CohortMetric] = []
        for name, apps in sorted(groups.items()):
            total = len(apps)
            resp_count = 0
            int_count = 0
            off_count = 0

            for a in apps:
                statuses = {e.event_type for e in a.events}
                if a.current_status:
                    statuses.add(a.current_status)

                if ApplicationLifecycleStatus.RECRUITER_RESPONSE in statuses or ApplicationLifecycleStatus.INTERVIEW in statuses or ApplicationLifecycleStatus.OFFER in statuses:
                    resp_count += 1
                if ApplicationLifecycleStatus.INTERVIEW in statuses or ApplicationLifecycleStatus.FINAL_ROUND in statuses or ApplicationLifecycleStatus.OFFER in statuses:
                    int_count += 1
                if ApplicationLifecycleStatus.OFFER in statuses or ApplicationLifecycleStatus.ACCEPTED in statuses:
                    off_count += 1

            r_rate = (resp_count / total * 100.0) if total > 0 else 0.0
            i_rate = (int_count / total * 100.0) if total > 0 else 0.0
            o_rate = (off_count / total * 100.0) if total > 0 else 0.0

            is_reliable = total >= MIN_SAMPLE_SIZE_THRESHOLD
            note = None if is_reliable else f"N={total} (<{MIN_SAMPLE_SIZE_THRESHOLD})"

            cohorts.append(
                CohortMetric(
                    cohort_name=name,
                    total_applications=total,
                    recruiter_responses=resp_count,
                    interviews=int_count,
                    offers=off_count,
                    response_rate=round(r_rate, 2),
                    interview_rate=round(i_rate, 2),
                    offer_rate=round(o_rate, 2),
                    is_statistically_reliable=is_reliable,
                    notes=note,
                )
            )

        return cohorts

    @classmethod
    def compute_response_times(
        cls,
        applications: List[ApplicationRecord],
    ) -> List[ResponseTimeMetrics]:
        """Calculate elapsed days between key application milestones."""
        durations: Dict[str, List[float]] = {
            "submission_to_acknowledgement": [],
            "submission_to_response": [],
            "submission_to_interview": [],
            "submission_to_rejection": [],
            "interview_to_offer": [],
        }

        for app in applications:
            # Map events by type
            events_by_type: Dict[ApplicationLifecycleStatus, datetime] = {}
            for e in app.events:
                if e.event_type not in events_by_type:
                    events_by_type[e.event_type] = e.timestamp

            sub_time = app.submitted_at or events_by_type.get(ApplicationLifecycleStatus.SUBMITTED)
            if not sub_time:
                continue

            # Submission to Ack
            if ApplicationLifecycleStatus.ACKNOWLEDGED in events_by_type:
                days = (events_by_type[ApplicationLifecycleStatus.ACKNOWLEDGED] - sub_time).total_seconds() / 86400.0
                if days >= 0:
                    durations["submission_to_acknowledgement"].append(days)

            # Submission to Response
            if ApplicationLifecycleStatus.RECRUITER_RESPONSE in events_by_type:
                days = (events_by_type[ApplicationLifecycleStatus.RECRUITER_RESPONSE] - sub_time).total_seconds() / 86400.0
                if days >= 0:
                    durations["submission_to_response"].append(days)

            # Submission to Interview
            if ApplicationLifecycleStatus.INTERVIEW in events_by_type:
                days = (events_by_type[ApplicationLifecycleStatus.INTERVIEW] - sub_time).total_seconds() / 86400.0
                if days >= 0:
                    durations["submission_to_interview"].append(days)

            # Submission to Rejection
            if ApplicationLifecycleStatus.REJECTED in events_by_type:
                days = (events_by_type[ApplicationLifecycleStatus.REJECTED] - sub_time).total_seconds() / 86400.0
                if days >= 0:
                    durations["submission_to_rejection"].append(days)

            # Interview to Offer
            if ApplicationLifecycleStatus.INTERVIEW in events_by_type and ApplicationLifecycleStatus.OFFER in events_by_type:
                days = (events_by_type[ApplicationLifecycleStatus.OFFER] - events_by_type[ApplicationLifecycleStatus.INTERVIEW]).total_seconds() / 86400.0
                if days >= 0:
                    durations["interview_to_offer"].append(days)

        metrics: List[ResponseTimeMetrics] = []
        for name, vals in durations.items():
            if not vals:
                metrics.append(
                    ResponseTimeMetrics(
                        metric_name=name,
                        sample_count=0,
                        median_days=0.0,
                        mean_days=0.0,
                        min_days=0.0,
                        max_days=0.0,
                    )
                )
            else:
                metrics.append(
                    ResponseTimeMetrics(
                        metric_name=name,
                        sample_count=len(vals),
                        median_days=round(statistics.median(vals), 2),
                        mean_days=round(statistics.mean(vals), 2),
                        min_days=round(min(vals), 2),
                        max_days=round(max(vals), 2),
                    )
                )

        return metrics

    @classmethod
    def build_dashboard(
        cls,
        applications: List[ApplicationRecord],
        events: List[ApplicationEvent],
    ) -> AnalyticsDashboard:
        """Assemble full analytics dashboard."""
        funnel = cls.compute_funnel(applications, events)
        conversion = cls.compute_conversion(funnel)
        strategies = cls.compute_cohort_performance(applications, "strategy")
        recommendations = cls.compute_cohort_performance(applications, "recommendation")
        scores = cls.compute_cohort_performance(applications, "score_bucket")
        sources = cls.compute_cohort_performance(applications, "source")
        response_times = cls.compute_response_times(applications)

        return AnalyticsDashboard(
            total_tracked=len(applications),
            funnel=funnel,
            conversion=conversion,
            strategy_performance=strategies,
            recommendation_performance=recommendations,
            score_bucket_performance=scores,
            source_performance=sources,
            response_times=response_times,
        )
