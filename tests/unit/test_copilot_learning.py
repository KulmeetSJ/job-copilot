"""Unit tests for HistoricalLearningEngine and statistical safety."""

from pathlib import Path
from unittest.mock import MagicMock

from job_copilot.copilot.learning import HistoricalLearningEngine
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.models import AnalyticsDashboard, CohortMetric, FunnelMetrics, ConversionRates, utc_now


def test_insufficient_sample_size_handling():
    """Verify N < 10 is flagged as INSUFFICIENT_SAMPLE and suppresses bold inferences."""
    mock_tracking = MagicMock(spec=TrackingService)

    # 3 applications, 2 interviews (rate looks like 66.7% but N=3 is too small)
    mock_tracking.get_analytics_dashboard.return_value = AnalyticsDashboard(
        total_tracked=3,
        funnel=FunnelMetrics(discovered=3, submitted=3, interviews=2),
        conversion=ConversionRates(submitted=3, interviews=2, interview_rate=66.7),
        strategy_performance=[
            CohortMetric(
                cohort_name="backend_java",
                total_applications=3,
                recruiter_responses=2,
                interviews=2,
                offers=0,
                response_rate=66.7,
                interview_rate=66.7,
                offer_rate=0.0,
                is_statistically_reliable=False,
            )
        ],
    )

    engine = HistoricalLearningEngine(tracking_service=mock_tracking)
    insights = engine.analyze_history()

    assert len(insights) == 1
    ins = insights[0]
    assert ins.sample_size == 3
    assert ins.sample_threshold_met is False
    assert ins.is_statistically_reliable is False
    assert ins.sample_size_warning is not None
    assert "N=3 < 10" in ins.sample_size_warning
    assert any("below minimum threshold" in inf.lower() for inf in ins.inference_statements)
    assert "No configuration change made" in ins.action_required


def test_sufficient_sample_size_insight():
    """Verify N >= 10 surfaces statistical comparison with strict Fact/Inference/Recommendation structure."""
    mock_tracking = MagicMock(spec=TrackingService)

    # 24 applications, 7 interviews (29.2% interview conversion)
    mock_tracking.get_analytics_dashboard.return_value = AnalyticsDashboard(
        total_tracked=24,
        funnel=FunnelMetrics(discovered=30, submitted=24, interviews=7),
        conversion=ConversionRates(submitted=24, interviews=7, interview_rate=29.2),
        strategy_performance=[
            CohortMetric(
                cohort_name="backend_java",
                total_applications=24,
                recruiter_responses=10,
                interviews=7,
                offers=2,
                response_rate=41.7,
                interview_rate=29.2,
                offer_rate=8.3,
                is_statistically_reliable=True,
            )
        ],
    )

    engine = HistoricalLearningEngine(tracking_service=mock_tracking)
    insights = engine.analyze_history()

    assert len(insights) == 1
    ins = insights[0]
    assert ins.sample_size == 24
    assert ins.sample_threshold_met is True
    assert ins.is_statistically_reliable is True
    assert ins.sample_size_warning is None
    assert any("FACT:" in f for f in ins.fact_statements)
    assert any("INFERENCE:" in i for i in ins.inference_statements)
    assert any("RECOMMENDATION:" in r for r in ins.recommendation_statements)
    assert "No configuration change made" in ins.action_required
