"""Unit tests for Phase 6 Cover Letter generation and validation."""

from pathlib import Path
import pytest
import yaml

from job_copilot.application.cover_letter import CoverLetterEngine
from job_copilot.application.models import ClaimProvenance
from job_copilot.matching.analyzer import JobAnalyzer
from job_copilot.matching.matcher import CandidateMatcher
from job_copilot.matching.models import JobAssessment
from job_copilot.matching.recommender import JobRecommender
from job_copilot.matching.scorer import FitScorer
from job_copilot.matching.strategy_selector import StrategySelector
from job_copilot.schemas.candidate import CandidateProfile


@pytest.fixture
def profile():
    data = yaml.safe_load(Path("data/candidate/master_profile.yaml").read_text(encoding="utf-8"))
    return CandidateProfile.model_validate(data)


@pytest.fixture
def assessment(profile):
    analyzer = JobAnalyzer()
    matcher = CandidateMatcher()
    scorer = FitScorer()
    strat_selector = StrategySelector()
    recommender = JobRecommender()

    job = analyzer.analyze("""
    Company: Stripe
    Job Title: Software Engineer - Java Backend
    Location: Remote
    Requirements: Java, Spring Boot, GCP, REST APIs.
    """)
    matches = matcher.match_job(job, profile)
    scores = scorer.compute_score(job, profile, matches)
    rec_strat, alt_strats, reason = strat_selector.select_strategy(job, matches)
    rec, strengths, partials, gaps, risks, report = recommender.evaluate(job, matches, scores, rec_strat)

    return JobAssessment(
        job=job,
        match_results=matches,
        score_breakdown=scores,
        recommendation=rec,
        strengths=strengths,
        partial_matches=partials,
        gaps=gaps,
        risks=risks,
        recommended_strategy=rec_strat,
        alternative_strategies=alt_strats,
        strategy_reasoning=reason,
        human_report=report,
    )


def test_cover_letter_generation(profile, assessment):
    engine = CoverLetterEngine()
    cl = engine.generate_cover_letter(assessment, profile)
    assert cl.company == "Stripe"
    assert cl.title == "Software Engineer - Java Backend"
    assert 200 <= cl.word_count <= 450
    assert cl.validation.is_valid is True
    assert len(cl.provenance) >= 3


def test_cover_letter_truth_validation_rejects_unsupported_claims():
    engine = CoverLetterEngine()
    prov = [
        ClaimProvenance(
            claim_text="Java backend at HSBC",
            source_type="PROFESSIONAL",
            source_ref="EXP-HSBC-BEAM-001",
        )
    ]
    # Letter claiming AWS and 10+ years
    invalid_letter = "I have 10+ years experience with AWS and Java at Stripe."
    val = engine.validate_cover_letter(invalid_letter, prov, "Stripe", "Senior Engineer")
    assert val.is_valid is False
    assert any("aws" in e.lower() for e in val.errors)
    assert any("years" in e.lower() for e in val.errors)
