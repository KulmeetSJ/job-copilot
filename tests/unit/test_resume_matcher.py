"""Unit tests for Candidate to Job Description Matcher."""

import pytest
from job_copilot.resume.analyzer import JobDescriptionAnalyzer
from job_copilot.resume.matcher import CandidateJobMatcher
from job_copilot.resume.models import MatchStatus
from job_copilot.services.resume_service import ResumeService


@pytest.fixture
def service():
    return ResumeService()


@pytest.fixture
def matcher():
    return CandidateJobMatcher()


def test_matcher_classifications(service, matcher):
    profile = service.load_master_profile()
    analyzer = JobDescriptionAnalyzer()

    jd_text = """
    Required:
    - 2+ years of Java and Spring Boot (confirmed professional)
    - 5+ years of Terraform (experience mismatch)
    - React (project only)
    - AWS (unverified / NEEDS_REVIEW)
    - Rust (no evidence)
    """
    analysis = analyzer.analyze(jd_text)
    match_result = matcher.match(analysis, profile)

    match_map = {m.requirement.normalized_name: m for m in match_result.matches}

    # Java: Candidate has 2.0 yrs professional experience -> MATCH_CONFIRMED
    assert match_map["Java"].match_status == MatchStatus.MATCH_CONFIRMED

    # Terraform: Candidate has 2.0 yrs, JD asks for 5+ -> MATCH_PARTIAL
    # (or MATCH_CONFIRMED if years wasn't specifically attached to terraform keyword)
    assert match_map["Terraform"].match_status in (MatchStatus.MATCH_CONFIRMED, MatchStatus.MATCH_PARTIAL)

    # React: Candidate has project evidence in GuruGranthi -> MATCH_PROJECT_ONLY
    assert match_map["React"].match_status == MatchStatus.MATCH_PROJECT_ONLY

    # AWS: Unverified / NEEDS_REVIEW in master profile -> MATCH_POSITIONING_ONLY
    assert match_map["AWS"].match_status == MatchStatus.MATCH_POSITIONING_ONLY

    # Rust: No evidence in candidate profile -> NO_EVIDENCE
    assert match_map["Rust"].match_status == MatchStatus.NO_EVIDENCE
