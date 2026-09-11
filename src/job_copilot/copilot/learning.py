"""Sample-Safe Historical Learning Engine for Phase 9 Copilot."""

from typing import List, Optional

from job_copilot.copilot.models import HistoricalInsight, utc_now
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.models import AnalyticsDashboard, CohortMetric
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

MINIMUM_SAMPLE_SIZE = 10


class HistoricalLearningEngine:
    """
    Analyzes historical application outcomes from Phase 8 to generate actionable,
    conservative insights.
    
    GUARANTEES:
      1. Statistical Safety: N < 10 is explicitly surfaced as INSUFFICIENT_SAMPLE.
      2. Clear Distinction: Strict separation of FACT, INFERENCE, and RECOMMENDATION.
      3. Immutability: Zero automatic system or configuration mutation.
    """

    def __init__(self, tracking_service: Optional[TrackingService] = None):
        self.tracking_service = tracking_service or TrackingService()

    def analyze_history(self) -> List[HistoricalInsight]:
        """
        Analyze Phase 8 historical dashboard metrics and generate insights.
        """
        dashboard: AnalyticsDashboard = self.tracking_service.get_analytics_dashboard()
        insights: List[HistoricalInsight] = []

        # 1. Strategy Performance Insights
        strategy_insights = self._analyze_cohort(
            cohorts=dashboard.strategy_performance,
            dimension_name="Resume Strategy",
            topic="Strategy Performance",
        )
        if strategy_insights:
            insights.extend(strategy_insights)

        # 2. Recommendation Tier Performance Insights
        rec_insights = self._analyze_cohort(
            cohorts=dashboard.recommendation_performance,
            dimension_name="Recommendation Tier",
            topic="Recommendation Accuracy",
        )
        if rec_insights:
            insights.extend(rec_insights)

        # 3. Source Performance Insights
        source_insights = self._analyze_cohort(
            cohorts=dashboard.source_performance,
            dimension_name="Discovery Source",
            topic="Source Effectiveness",
        )
        if source_insights:
            insights.extend(source_insights)

        # If no history exists yet, return empty list or initial placeholder
        return insights

    def _analyze_cohort(
        self,
        cohorts: List[CohortMetric],
        dimension_name: str,
        topic: str,
    ) -> List[HistoricalInsight]:
        """Generate cohort-specific insights with sample-size enforcement."""
        results: List[HistoricalInsight] = []
        if not cohorts:
            return results

        # Find best and comparison cohorts
        for c in cohorts:
            facts: List[str] = [
                f"FACT: {c.total_applications} application(s) submitted under {dimension_name} '{c.cohort_name}'.",
                f"FACT: {c.recruiter_responses} recruiter response(s) observed ({c.response_rate:.1f}% response rate).",
                f"FACT: {c.interviews} interview(s) reached ({c.interview_rate:.1f}% interview rate).",
                f"FACT: {c.offers} offer(s) extended ({c.offer_rate:.1f}% offer rate).",
            ]

            inferences: List[str] = []
            recommendations: List[str] = []
            warning: Optional[str] = None

            if c.total_applications < MINIMUM_SAMPLE_SIZE:
                warning = f"Insufficient sample size (N={c.total_applications} < {MINIMUM_SAMPLE_SIZE}). Minimum sample threshold for surfacing historical signals not met."
                inferences.append(f"INFERENCE: Sample size (N={c.total_applications}) is below minimum threshold ({MINIMUM_SAMPLE_SIZE}); strong historical inferences are not surfaced.")
                recommendations.append(f"RECOMMENDATION: Continue observing outcomes for '{c.cohort_name}' until at least {MINIMUM_SAMPLE_SIZE} applications are submitted.")
            else:
                if c.interview_rate >= 20.0:
                    inferences.append(f"INFERENCE: '{c.cohort_name}' demonstrates strong interview conversion ({c.interview_rate:.1f}% with N={c.total_applications}).")
                    recommendations.append(f"RECOMMENDATION: Consider prioritizing '{c.cohort_name}' opportunities when reviewing queue.")
                elif c.interview_rate < 10.0:
                    inferences.append(f"INFERENCE: '{c.cohort_name}' has historically yielded lower interview conversion ({c.interview_rate:.1f}% with N={c.total_applications}).")
                    recommendations.append(f"RECOMMENDATION: Review alignment criteria or consider alternative positioning for '{c.cohort_name}'.")
                else:
                    inferences.append(f"INFERENCE: '{c.cohort_name}' performance is within typical baseline expectations (N={c.total_applications}).")
                    recommendations.append(f"RECOMMENDATION: Maintain standard review cadence for '{c.cohort_name}'.")

            insight = HistoricalInsight(
                topic=f"{topic}: {c.cohort_name}",
                fact_statements=facts,
                inference_statements=inferences,
                recommendation_statements=recommendations,
                sample_size=c.total_applications,
                sample_threshold_met=(c.total_applications >= MINIMUM_SAMPLE_SIZE),
                is_statistically_reliable=(c.total_applications >= MINIMUM_SAMPLE_SIZE),
                sample_size_warning=warning,
                action_required="No configuration change made (human decision required)",
                generated_at=utc_now(),
            )
            results.append(insight)

        return results

    def get_strategy_boost(self, strategy_name: str) -> float:
        """
        Derive safe priority boost for a strategy only if sample threshold is met (N >= 10).
        """
        dashboard: AnalyticsDashboard = self.tracking_service.get_analytics_dashboard()
        for c in dashboard.strategy_performance:
            if c.cohort_name == strategy_name and c.total_applications >= MINIMUM_SAMPLE_SIZE:
                if c.interview_rate >= 25.0:
                    return 10.0
                elif c.interview_rate < 10.0:
                    return -5.0
        return 0.0
