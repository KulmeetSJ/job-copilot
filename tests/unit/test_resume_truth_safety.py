"""Unit tests verifying strict Truth and Claim Safety invariants."""

import pytest
from job_copilot.services.resume_service import ResumeService


@pytest.fixture
def service():
    return ResumeService()


def test_truth_safety_unconfirmed_tech_excluded(service):
    """Ensure AWS and Kafka are never presented as confirmed in generated resume skills."""
    profile = service.load_master_profile()
    for strat_name in service.list_strategies():
        strat = service.get_strategy(strat_name)
        res = service.selector.select_content(profile, strat)
        
        all_skills = set()
        for grp in res.skill_groups:
            for s in grp.skills:
                all_skills.add(s.lower())

        assert "aws" not in all_skills
        assert "apache kafka" not in all_skills
        assert "kafka" not in all_skills


def test_truth_safety_canonical_employment(service):
    """Ensure canonical role remains Software Engineer at HSBC."""
    profile = service.load_master_profile()
    for strat_name in service.list_strategies():
        strat = service.get_strategy(strat_name)
        res = service.selector.select_content(profile, strat)
        
        assert len(res.experience) > 0
        for exp in res.experience:
            assert exp.company == "HSBC"
            assert exp.canonical_role == "Software Engineer"
            assert exp.role == "Software Engineer"
            assert exp.start_date == "2024-07"
            assert exp.current is True


def test_truth_safety_benchmark_metrics(service):
    """Ensure 100K+ RPS remains a benchmark metric."""
    profile = service.load_master_profile()
    strat = service.get_strategy("backend_java")
    res = service.selector.select_content(profile, strat)

    rate_limiter = next((p for p in res.projects if "Rate Limiter" in p.name), None)
    assert rate_limiter is not None
    assert rate_limiter.deployment_status in ("PORTFOLIO_DEMO", "BENCHMARK")
    for b in rate_limiter.bullets:
        assert b.claim_type == "BENCHMARK"
        assert b.metric_type == "BENCHMARK"
        assert "production" not in b.text.lower()


def test_truth_safety_bullet_provenance(service):
    """Ensure every generated bullet has non-empty evidence IDs."""
    profile = service.load_master_profile()
    for strat_name in service.list_strategies():
        strat = service.get_strategy(strat_name)
        res = service.selector.select_content(profile, strat)

        for exp in res.experience:
            for b in exp.bullets:
                assert len(b.evidence_ids) > 0

        for prj in res.projects:
            for b in prj.bullets:
                assert len(b.evidence_ids) > 0
