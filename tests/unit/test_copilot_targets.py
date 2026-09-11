"""Unit tests for Phase 9.2 Job Targeting & Preferences Configuration."""

import pytest
from job_copilot.copilot.config import CopilotConfig, PriorityConfig
from job_copilot.copilot.models import PriorityBand
from job_copilot.copilot.prioritizer import OpportunityPrioritizer
from job_copilot.copilot.targeting import (
    JobTargetsConfig,
    load_job_targets_config,
)


def test_job_targets_configuration_loading():
    """Verify that Tier 1 and Tier 2 companies, job families, skills, and locations load correctly."""
    cfg: JobTargetsConfig = load_job_targets_config()

    # Tier 1 - Financial Services
    t1_names = [c.name for c in cfg.tier_1.companies]
    expected_t1 = [
        "Mastercard",
        "Deutsche Bank",
        "Morgan Stanley",
        "JPMorgan Chase",
        "Goldman Sachs",
        "Citi",
        "UBS",
        "Barclays",
        "Bajaj Finance",
        "Stripe",
        "Finastra",
        "American Express",
    ]
    for exp in expected_t1:
        assert exp in t1_names, f"Expected {exp} in Tier 1 target companies"
    assert cfg.tier_1.priority_tier == 1
    assert cfg.tier_1.domain_group == "financial_services"
    assert cfg.tier_1.bonus_points == 5.0

    # Tier 2 - Technology / Product
    t2_names = [c.name for c in cfg.tier_2.companies]
    expected_t2 = [
        "Zomato",
        "Blinkit",
        "Myntra",
        "Microsoft",
        "Google",
        "Uber",
        "Ola",
        "Siemens",
        "Meta",
        "Optum",
    ]
    for exp in expected_t2:
        assert exp in t2_names, f"Expected {exp} in Tier 2 target companies"
    assert cfg.tier_2.priority_tier == 2
    assert cfg.tier_2.domain_group == "technology_product"
    assert cfg.tier_2.bonus_points == 2.0

    # Non-target companies allowed
    assert cfg.other_companies.allow_non_target_companies is True
    assert cfg.other_companies.default_bonus_points == 0.0


def test_target_company_lookup_and_tier_assignment():
    """Verify company matching against Tier 1, Tier 2, and unknown companies."""
    cfg = load_job_targets_config()

    # Tier 1 match
    t1_info = cfg.get_company_targeting_info("Mastercard Inc.")
    assert t1_info is not None
    assert t1_info["tier"] == 1
    assert t1_info["domain_group"] == "financial_services"
    assert t1_info["bonus_points"] == 5.0

    # Tier 2 match
    t2_info = cfg.get_company_targeting_info("Google LLC")
    assert t2_info is not None
    assert t2_info["tier"] == 2
    assert t2_info["domain_group"] == "technology_product"
    assert t2_info["bonus_points"] == 2.0

    # Non-target unknown company
    non_target_info = cfg.get_company_targeting_info("Acme Startup Inc")
    assert non_target_info is None


def test_company_targeting_cannot_override_poor_fit():
    """
    CRITICAL RULE: Company targeting preference must NOT override poor job fit.
    A Tier 1 company with fit 45 must NOT achieve HIGH/CRITICAL priority.
    An unknown non-target company with fit 94 must remain HIGH/CRITICAL priority.
    """
    prioritizer = OpportunityPrioritizer()

    # Target company with poor fit (45)
    score_tier1_poor, band_tier1_poor, _ = prioritizer.calculate_priority(
        match_score=45.0,
        recommendation_tier="REVIEW",
        company_tier=1,
    )
    # 45.0 (fit) - 5.0 (review tier) + 10.0 (freshness) + 5.0 (tier 1 bonus) = 55.0 (MEDIUM)
    assert score_tier1_poor < 75.0, "Tier 1 company with poor fit must not be prioritized as HIGH/CRITICAL"
    assert band_tier1_poor in [PriorityBand.MEDIUM, PriorityBand.LOW]

    # Non-target company with excellent fit (94)
    score_non_target_high, band_non_target_high, _ = prioritizer.calculate_priority(
        match_score=94.0,
        recommendation_tier="STRONG_APPLY",
        company_tier=None,
    )
    # 94.0 (fit) + 5.0 (strong apply tier) + 10.0 (freshness) + 0.0 (tier bonus) = 100.0 (CRITICAL)
    assert score_non_target_high >= 90.0
    assert band_non_target_high == PriorityBand.CRITICAL


def test_job_families_broad_semantic_matching():
    """Verify that job families are broad preferences and exact titles are not required."""
    cfg = load_job_targets_config()

    # Primary match
    assert cfg.matches_job_family("Software Engineer II - Payment Data Infrastructure")["matched"] is True
    assert cfg.matches_job_family("Staff Java Backend Engineer")["matched"] is True
    assert cfg.matches_job_family("Principal Distributed Systems Architect")["matched"] is True
    assert cfg.matches_job_family("Lead SRE / Cloud Platform")["matched"] is True

    # Secondary match
    assert cfg.matches_job_family("Payment Systems Specialist")["matched"] is True
    assert cfg.matches_job_family("Senior Full Stack GCP Engineer")["matched"] is True

    # Non-matching unrelated title
    assert cfg.matches_job_family("Chief Marketing Officer")["matched"] is False


def test_locations_recognition_and_remote_policies():
    """Verify recognition of primary, secondary, international, and remote locations."""
    cfg = load_job_targets_config()

    # Primary
    assert cfg.matches_location("Pune, Maharashtra, India")["matched"] is True
    assert cfg.matches_location("Bangalore / Bengaluru")["matched"] is True
    assert cfg.matches_location("Gurgaon, Delhi NCR")["matched"] is True

    # Secondary
    assert cfg.matches_location("Chennai, Tamil Nadu")["matched"] is True
    assert cfg.matches_location("Noida, UP")["matched"] is True

    # Remote
    assert cfg.matches_location("Remote - Worldwide")["matched"] is True
    assert cfg.matches_location("Remote (India)")["matched"] is True

    # International
    assert cfg.matches_location("Singapore, Central")["matched"] is True
    assert cfg.matches_location("Tokyo, Japan")["matched"] is True

    # Remote modes
    assert "REMOTE_WORLDWIDE" in cfg.remote_policies.supported_modes
    assert "REMOTE_INDIA" in cfg.remote_policies.supported_modes
    assert "HYBRID" in cfg.remote_policies.supported_modes
    assert "ONSITE" in cfg.remote_policies.supported_modes
