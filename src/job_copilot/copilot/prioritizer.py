"""Deterministic Opportunity Prioritizer for Phase 9 Copilot."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from job_copilot.copilot.config import CopilotConfig, PriorityConfig
from job_copilot.copilot.models import PriorityBand, utc_now
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class OpportunityPrioritizer:
    """
    Computes explainable, deterministic opportunity priority scores and assigns PriorityBands.
    Does NOT modify Phase 4 fit scores or change recommendation rules.
    """

    def __init__(self, config: Optional[CopilotConfig] = None):
        self.config = config or CopilotConfig()

    def calculate_priority(
        self,
        match_score: float,
        recommendation_tier: str,
        discovered_at: Optional[datetime] = None,
        strategy_historical_boost: float = 0.0,
        risk_flags: Optional[List[str]] = None,
        company_tier: Optional[int] = None,
    ) -> Tuple[float, PriorityBand, Dict[str, float]]:
        """
        Calculate composite priority score and band.

        Formula:
          fit_signal = Phase 4 match score (0.0 .. 100.0)
          base_signal = fit_signal + recommendation_tier_adjustment
          freshness_signal = bonus based on age (0.0 .. 10.0)
          historical_signal = validated bonus from Phase 8 (N >= 10)
          risk_signal = penalties for identified risks/conflicts
          targeting_signal = preference bonus for Tier 1 (+5.0) or Tier 2 (+2.0) companies

          priority_score = clamp(base_signal + freshness_signal + historical_signal + risk_signal + targeting_signal, 0.0, 100.0)
        """
        cfg: PriorityConfig = self.config.priority
        risks = risk_flags or []

        # 1. Fit signal: Continuous Phase 4 match score (0.0 .. 100.0)
        fit_signal = max(0.0, min(100.0, float(match_score)))

        # 2. Recommendation tier adjustment: Explicit policy modifier for categorical decisions
        tier_adjustments = cfg.recommendation_tier_adjustments or {
            "STRONG_APPLY": 5.0,
            "APPLY": 0.0,
            "CONSIDER": -5.0,
            "REVIEW": -5.0,
            "LOW_PRIORITY": -15.0,
            "SKIP": -40.0,
            "HIGH_RISK": -50.0,
        }
        rec_adj = tier_adjustments.get(recommendation_tier.upper(), 0.0)

        # 3. Base signal: Combines continuous fit with categorical tier policy
        base_signal = fit_signal + rec_adj

        # 4. Freshness signal
        now = utc_now()
        if discovered_at:
            disc_dt = discovered_at if discovered_at.tzinfo is not None else discovered_at.replace(tzinfo=timezone.utc)
            age_days = max(0, (now - disc_dt).days)
        else:
            age_days = 0

        freshness_signal = cfg.old_points
        if age_days <= cfg.very_recent_days:
            freshness_signal = cfg.very_recent_points
        elif age_days <= cfg.recent_days:
            freshness_signal = cfg.recent_points

        # 5. Historical signal (from Phase 8 with N >= 10)
        historical_signal = strategy_historical_boost if cfg.historical_enabled else 0.0

        # 6. Risk deductions
        risk_signal = 0.0
        for r in risks:
            r_lower = r.lower()
            if "conflict" in r_lower:
                risk_signal += cfg.hard_conflict_penalty
            elif "missing" in r_lower:
                risk_signal += cfg.missing_critical_skill_penalty
            elif "seniority" in r_lower:
                risk_signal += cfg.unsupported_seniority_penalty
            elif "sponsorship" in r_lower or "visa" in r_lower:
                risk_signal += cfg.unknown_sponsorship_penalty

        # 7. Company targeting preference signal (Phase 9.2)
        targeting_signal = 0.0
        if getattr(cfg, "targeting_enabled", True) and company_tier:
            if company_tier == 1:
                targeting_signal = getattr(cfg, "tier_1_bonus", 5.0)
            elif company_tier == 2:
                targeting_signal = getattr(cfg, "tier_2_bonus", 2.0)

        # 8. Composite score calculation
        raw_score = base_signal + freshness_signal + historical_signal + risk_signal + targeting_signal
        final_score = round(max(0.0, min(100.0, raw_score)), 1)

        # 9. Deterministic band assignment
        if final_score >= 90.0:
            band = PriorityBand.CRITICAL
        elif final_score >= 75.0:
            band = PriorityBand.HIGH
        elif final_score >= 50.0:
            band = PriorityBand.MEDIUM
        elif final_score >= 30.0:
            band = PriorityBand.LOW
        else:
            band = PriorityBand.IGNORE

        breakdown = {
            "fit_signal": round(fit_signal, 1),
            "recommendation_tier_adjustment": round(rec_adj, 1),
            "recommendation_signal": round(rec_adj, 1),
            "base_signal": round(base_signal, 1),
            "freshness_signal": round(freshness_signal, 1),
            "historical_signal": round(historical_signal, 1),
            "risk_signal": round(risk_signal, 1),
            "targeting_signal": round(targeting_signal, 1),
            "company_tier_signal": round(targeting_signal, 1),
            "final_score": final_score,
        }

        return final_score, band, breakdown
