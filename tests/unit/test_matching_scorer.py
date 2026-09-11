"""Unit tests for multi-dimensional fit scoring."""

import pytest
from job_copilot.matching.analyzer import JobAnalyzer
from job_copilot.matching.matcher import CandidateMatcher
from job_copilot.matching.models import FitScoreBreakdown
from job_copilot.matching.scorer import FitScorer
from job_copilot.services.job_intelligence_service import JobIntelligenceService


@pytest.fixture
def service():
    return JobIntelligenceService()


@pytest.fixture
def analyzer():
    return JobAnalyzer()


@pytest.fixture
def matcher():
    return CandidateMatcher()


@pytest.fixture
def scorer():
    return FitScorer()


def test_scorer_produces_valid_7_dimensional_breakdown(service, analyzer, matcher, scorer):
    profile = service.load_master_profile()
    job = analyzer.analyze("""
    Job Title: Software Engineer - Java Backend
    Company: Stripe
    Requirements:
    - 2+ years of Java, Spring Boot, PostgreSQL, Redis.
    - GCP cloud infrastructure.
    """)
    matches = matcher.match_job(job, profile)
    scores = scorer.compute_score(job, profile, matches)

    assert isinstance(scores, FitScoreBreakdown)
    assert 0.0 <= scores.overall_score <= 100.0
    assert 0.0 <= scores.technical_score <= 100.0
    assert 0.0 <= scores.responsibility_score <= 100.0
    assert 0.0 <= scores.role_score <= 100.0
    assert 0.0 <= scores.experience_score <= 100.0
    assert 0.0 <= scores.domain_score <= 100.0
    assert 0.0 <= scores.preference_score <= 100.0
    assert 0.0 <= scores.credential_score <= 100.0
