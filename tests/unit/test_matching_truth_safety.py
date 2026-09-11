"""Unit tests verifying Phase 4 Truth and Claim Safety Invariants."""

import pytest
from job_copilot.matching.analyzer import JobAnalyzer
from job_copilot.matching.matcher import CandidateMatcher
from job_copilot.matching.models import MatchClassification, WorkAuthorizationRequirement
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


def test_aws_never_becomes_confirmed_experience(service, analyzer, matcher):
    """Ensure AWS in JD is classified as MATCH_POSITIONING_ONLY and never confirmed."""
    profile = service.load_master_profile()
    job = analyzer.analyze("Seeking an engineer with deep AWS EC2, S3, and IAM experience.")
    matches = matcher.match_job(job, profile)

    aws_match = next((m for m in matches if m.requirement.normalized_name == "AWS"), None)
    assert aws_match is not None
    assert aws_match.classification == MatchClassification.MATCH_POSITIONING_ONLY
    assert "unverified" in aws_match.reason.lower()


def test_gke_and_helm_classified_as_exposure_only(service, analyzer, matcher):
    """Ensure GKE and Helm are strictly classified as MATCH_EXPOSURE_ONLY."""
    profile = service.load_master_profile()
    job = analyzer.analyze("Looking for experience with Google Kubernetes Engine (GKE) and Helm Charts.")
    matches = matcher.match_job(job, profile)

    gke_match = next((m for m in matches if "GKE" in m.requirement.normalized_name), None)
    assert gke_match is not None
    assert gke_match.classification == MatchClassification.MATCH_EXPOSURE_ONLY
    assert "SKL-GKE-001" in gke_match.candidate_evidence_ids

    helm_match = next((m for m in matches if "Helm" in m.requirement.normalized_name), None)
    assert helm_match is not None
    assert helm_match.classification == MatchClassification.MATCH_EXPOSURE_ONLY
    assert "SKL-HELM-001" in helm_match.candidate_evidence_ids


def test_google_adk_classified_as_exposure_only(service, analyzer, matcher):
    """Ensure Google ADK is classified as MATCH_EXPOSURE_ONLY."""
    profile = service.load_master_profile()
    job = analyzer.analyze("Experience with Google ADK (Agent Development Kit) for AI orchestration.")
    matches = matcher.match_job(job, profile)

    adk_match = next((m for m in matches if "ADK" in m.requirement.normalized_name), None)
    assert adk_match is not None
    assert adk_match.classification == MatchClassification.MATCH_EXPOSURE_ONLY
    assert "SKL-ADK-001" in adk_match.candidate_evidence_ids


def test_redis_classified_as_project_only(service, analyzer, matcher):
    """Ensure Redis is classified as MATCH_PROJECT_ONLY via Rate Limiter."""
    profile = service.load_master_profile()
    job = analyzer.analyze("Experience with Redis caching.")
    matches = matcher.match_job(job, profile)

    redis_match = next((m for m in matches if m.requirement.normalized_name == "Redis"), None)
    assert redis_match is not None
    assert redis_match.classification == MatchClassification.MATCH_PROJECT_ONLY
    assert "PRJ-RL-001" in redis_match.candidate_evidence_ids


def test_payments_ai_professional_context_without_invented_scale(service, analyzer, matcher):
    """Ensure PaymentsAI and Orchestration match confirmed HSBC professional experience."""
    profile = service.load_master_profile()
    job = analyzer.analyze("Building PaymentsAI platforms and orchestration services.")
    matches = matcher.match_job(job, profile)

    pay_match = next((m for m in matches if "PaymentsAI" in m.requirement.normalized_name), None)
    assert pay_match is not None
    assert pay_match.classification == MatchClassification.MATCH_CONFIRMED
    assert "EXP-HSBC-PAYMENTS-AI-001" in pay_match.candidate_evidence_ids


def test_unknown_work_authorization_remains_unknown(analyzer):
    """Ensure work authorization is not invented if unspecified in JD."""
    job = analyzer.analyze("Software Engineer needed for backend systems.")
    assert job.work_authorization == WorkAuthorizationRequirement.SPONSORSHIP_UNKNOWN
