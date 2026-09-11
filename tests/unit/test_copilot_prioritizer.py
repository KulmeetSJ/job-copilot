"""Unit tests for OpportunityPrioritizer."""

from datetime import datetime, timezone, timedelta
from job_copilot.copilot.config import CopilotConfig
from job_copilot.copilot.models import PriorityBand, utc_now
from job_copilot.copilot.prioritizer import OpportunityPrioritizer


def test_prioritizer_deterministic_bands():
    prioritizer = OpportunityPrioritizer()
    now = utc_now()

    # 1. Critical Priority: High fit (92), STRONG_APPLY (+5), very recent (+10) -> score = 100.0 (>= 90)
    score, band, breakdown = prioritizer.calculate_priority(
        match_score=92.0,
        recommendation_tier="STRONG_APPLY",
        discovered_at=now,
    )
    assert score >= 90.0
    assert band == PriorityBand.CRITICAL
    assert breakdown["fit_signal"] == 92.0
    assert breakdown["recommendation_tier_adjustment"] == 5.0

    # 2. High Priority: Fit (80), APPLY (0), recent (+5) -> score 85.0 (75 <= score < 90)
    score, band, _ = prioritizer.calculate_priority(
        match_score=80.0,
        recommendation_tier="APPLY",
        discovered_at=now - timedelta(days=5),
    )
    assert 75.0 <= score < 90.0
    assert band == PriorityBand.HIGH

    # 3. Medium Priority: Fit (65), CONSIDER (-5), older (+0) -> score 60.0 (50 <= score < 75)
    score, band, _ = prioritizer.calculate_priority(
        match_score=65.0,
        recommendation_tier="CONSIDER",
        discovered_at=now - timedelta(days=15),
    )
    assert 50.0 <= score < 75.0
    assert band == PriorityBand.MEDIUM

    # 4. Ignore / Low Priority: SKIP (-40), Fit (30) -> score 0.0 (< 30)
    score, band, _ = prioritizer.calculate_priority(
        match_score=30.0,
        recommendation_tier="SKIP",
        discovered_at=now - timedelta(days=20),
    )
    assert score < 30.0
    assert band == PriorityBand.IGNORE


def test_prioritizer_risk_penalties():
    prioritizer = OpportunityPrioritizer()
    now = utc_now()

    # High match but with hard conflict and missing critical skill
    score_clean, _, _ = prioritizer.calculate_priority(
        match_score=85.0,
        recommendation_tier="APPLY",
        discovered_at=now,
    )

    score_risky, band_risky, breakdown = prioritizer.calculate_priority(
        match_score=85.0,
        recommendation_tier="APPLY",
        discovered_at=now,
        risk_flags=["Hard conflict on location", "Missing critical skill Go"],
    )

    assert score_risky < score_clean
    assert breakdown["risk_signal"] < 0
    assert band_risky in [PriorityBand.LOW, PriorityBand.IGNORE]
