"""Unit tests for Job Intelligence & Matching domain models."""

import pytest
from job_copilot.matching.models import (
    AnalyzedJob,
    FitScoreBreakdown,
    JobAssessment,
    JobRecommendation,
    JobSeniority,
    MatchClassification,
    RequirementImportance,
    RequirementMatchResult,
    TechnicalRequirement,
    WorkAuthorizationRequirement,
)


def test_technical_requirement_model():
    req = TechnicalRequirement(
        name="java",
        normalized_name="Java",
        category="Language",
        importance=RequirementImportance.CRITICAL,
        is_must_have=True,
        years_required=3.0,
    )
    assert req.normalized_name == "Java"
    assert req.is_must_have is True
    assert req.years_required == 3.0


def test_analyzed_job_model():
    job = AnalyzedJob(
        job_id="stripe-backend-12345",
        company="Stripe",
        title="Software Engineer",
        description="Sample JD text",
        seniority=JobSeniority.MID_LEVEL,
    )
    assert job.job_id == "stripe-backend-12345"
    assert job.company == "Stripe"
    assert job.seniority == JobSeniority.MID_LEVEL


def test_fit_score_breakdown_model():
    scores = FitScoreBreakdown(
        technical_score=85.0,
        responsibility_score=80.0,
        role_score=90.0,
        experience_score=75.0,
        domain_score=100.0,
        preference_score=100.0,
        credential_score=100.0,
        overall_score=84.5,
    )
    assert scores.overall_score == 84.5
    assert scores.technical_score == 85.0
