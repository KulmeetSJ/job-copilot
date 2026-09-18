"""Configuration loader for Phase 9 Continuous Job Copilot."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import yaml

from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class PriorityConfig(BaseModel):
    """Configurable weights for opportunity prioritization."""
    recommendation_tier_adjustments: Dict[str, float] = Field(
        default_factory=lambda: {
            "STRONG_APPLY": 5.0,
            "APPLY": 0.0,
            "CONSIDER": -5.0,
            "REVIEW": -5.0,
            "LOW_PRIORITY": -15.0,
            "SKIP": -40.0,
            "HIGH_RISK": -50.0,
        }
    )
    recommendation_weights: Optional[Dict[str, float]] = None
    very_recent_days: int = 3
    very_recent_points: float = 10.0
    recent_days: int = 7
    recent_points: float = 5.0
    old_points: float = 0.0

    targeting_enabled: bool = True
    tier_1_bonus: float = 5.0
    tier_2_bonus: float = 2.0

    historical_enabled: bool = True
    minimum_sample_size: int = 10
    high_performing_bonus: float = 10.0
    low_performing_penalty: float = -10.0

    hard_conflict_penalty: float = -50.0
    missing_critical_skill_penalty: float = -20.0
    unsupported_seniority_penalty: float = -25.0
    unknown_sponsorship_penalty: float = -5.0


class QueueConfig(BaseModel):
    """Queue capacity and processing limits."""
    max_active_review: int = 50
    auto_skip_below_priority: float = 20.0
    default_sort: str = "priority_score_desc"
    max_daily_auto_apply: int = 10


class CopilotConfig(BaseModel):
    """Full Copilot configuration."""
    priority: PriorityConfig = Field(default_factory=PriorityConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    human_approval_required: List[str] = Field(
        default_factory=lambda: [
            "sensitive_application_questions",
            "salary_expectations",
            "sponsorship_and_work_authorization",
            "notice_period_and_start_date",
            "legal_declarations",
            "unverified_experience_claims",
            "final_application_review",
            "external_portal_submission",
        ]
    )


def load_copilot_config(config_path: Optional[Path] = None) -> CopilotConfig:
    """Load copilot configuration from yaml or return safe defaults."""
    target_path = config_path or Path("data/config/copilot.yaml")
    if not target_path.exists():
        logger.info(f"Copilot config not found at {target_path}, using built-in defaults.")
        return CopilotConfig()

    try:
        data = yaml.safe_load(target_path.read_text(encoding="utf-8")) or {}
        pri_data = data.get("priority", {})
        q_data = data.get("queue", {})

        priority_cfg = PriorityConfig(
            recommendation_weights=pri_data.get("recommendation_weights", {}),
            targeting_enabled=pri_data.get("targeting", {}).get("enabled", True),
            tier_1_bonus=pri_data.get("targeting", {}).get("tier_1_bonus", 5.0),
            tier_2_bonus=pri_data.get("targeting", {}).get("tier_2_bonus", 2.0),
            very_recent_days=pri_data.get("freshness_bonus", {}).get("very_recent_days", 3),
            very_recent_points=pri_data.get("freshness_bonus", {}).get("very_recent_points", 10.0),
            recent_days=pri_data.get("freshness_bonus", {}).get("recent_days", 7),
            recent_points=pri_data.get("freshness_bonus", {}).get("recent_points", 5.0),
            old_points=pri_data.get("freshness_bonus", {}).get("old_points", 0.0),
            historical_enabled=pri_data.get("historical", {}).get("enabled", True),
            minimum_sample_size=pri_data.get("historical", {}).get("minimum_sample_size", 10),
            high_performing_bonus=pri_data.get("historical", {}).get("high_performing_bonus", 15.0),
            low_performing_penalty=pri_data.get("historical", {}).get("low_performing_penalty", -10.0),
            hard_conflict_penalty=pri_data.get("risk_penalties", {}).get("hard_conflict", -50.0),
            missing_critical_skill_penalty=pri_data.get("risk_penalties", {}).get("missing_critical_skill", -20.0),
            unsupported_seniority_penalty=pri_data.get("risk_penalties", {}).get("unsupported_seniority", -25.0),
            unknown_sponsorship_penalty=pri_data.get("risk_penalties", {}).get("unknown_sponsorship", -5.0),
        )

        queue_cfg = QueueConfig(
            max_active_review=q_data.get("max_active_review", 50),
            auto_skip_below_priority=q_data.get("auto_skip_below_priority", 20.0),
            default_sort=q_data.get("default_sort", "priority_score_desc"),
            max_daily_auto_apply=q_data.get("max_daily_auto_apply", 10),
        )

        return CopilotConfig(
            priority=priority_cfg,
            queue=queue_cfg,
            human_approval_required=data.get("human_approval_required", []),
        )
    except Exception as e:
        logger.warning(f"Error reading copilot config: {e}. Falling back to default configuration.")
        return CopilotConfig()
