"""Focused unit and integration tests for LLM Resume Tailoring, Provider Abstraction,
Evidence Grounding, and Deterministic Fallback."""

from pathlib import Path
from typing import Optional
import pytest

from job_copilot.resume.llm.models import (
    LLMBulletItem,
    LLMProjectItem,
    LLMResumeDraft,
    LLMSkillGroupItem,
)
from job_copilot.resume.llm.prompts import (
    RESUME_SYSTEM_PROMPT,
    build_grounded_resume_prompt,
)
from job_copilot.resume.llm.provider import (
    LLMResumeProvider,
    OpenAICompatibleResumeProvider,
    get_resume_llm_provider,
)
from job_copilot.resume.llm.validator import GroundingValidator
from job_copilot.resume.llm.writer import LLMResumeWriter
from job_copilot.resume.models import JobAnalysis, JobRequirement, JobRequirementType
from job_copilot.services.resume_service import ResumeService


class MockLLMProvider(LLMResumeProvider):
    """Mock LLM Provider returning pre-configured drafts or simulated errors."""

    def __init__(self, draft_to_return: Optional[LLMResumeDraft] = None, should_fail: bool = False):
        self.draft_to_return = draft_to_return
        self.should_fail = should_fail
        self.call_count = 0
        self.last_retry_error: Optional[str] = None

    def is_available(self) -> bool:
        return not self.should_fail

    def generate_resume_draft(
        self,
        system_prompt: str,
        user_prompt: str,
        retry_error: Optional[str] = None,
    ) -> Optional[LLMResumeDraft]:
        self.call_count += 1
        self.last_retry_error = retry_error
        if self.should_fail:
            return None
        return self.draft_to_return


@pytest.fixture
def service():
    return ResumeService()


@pytest.fixture
def candidate_profile(service):
    return service.load_master_profile()


@pytest.fixture
def valid_llm_draft():
    """A realistic, highly tailored, 100% grounded LLM draft for Backend Java / GCP role."""
    return LLMResumeDraft(
        summary=(
            "Software Engineer with enterprise fintech experience at HSBC architecting real-time payment data pipelines "
            "and Google Cloud Platform (GCP) infrastructure. Google Cloud Certified Professional Cloud Architect with hands-on "
            "expertise in Java, Spring Boot, Apache Beam, BigQuery, and Terraform IaC, operating mission-critical payment ingestion "
            "with sub-second latency and 99.9% availability."
        ),
        experience_bullets=[
            LLMBulletItem(
                text="Architected real-time Apache Beam pipelines in Java (Spring Boot) ingesting **10M+ daily payment transactions** into BigQuery via GCP Dataflow, maintaining **99.9% uptime** and sub-second latency.",
                evidence_ids=["EXP-HSBC-BEAM-001"],
                technologies=["Java", "Spring Boot", "Apache Beam", "GCP Dataflow", "BigQuery"],
            ),
            LLMBulletItem(
                text="Provisioned **2,000+ GCP cloud resources** using modular Terraform IaC (Pub/Sub, BigQuery, GCS, IAM), accelerating provisioning cycle time by **60%**.",
                evidence_ids=["EXP-HSBC-TF-001"],
                technologies=["Terraform", "Google Cloud Platform (GCP)", "Pub/Sub", "BigQuery"],
            ),
            LLMBulletItem(
                text="Engineered CI/CD pipelines in Jenkins integrating SonarQube, Checkmarx, and Nexus for **100+ Cloud Composer (Airflow) DAG deployments**, reducing deployment incidents by **45%**.",
                evidence_ids=["EXP-HSBC-CICD-001"],
                technologies=["Jenkins", "CI/CD", "Apache Airflow", "SonarQube", "Nexus"],
            ),
            LLMBulletItem(
                text="Automated scheduled Dataflow pipeline lifecycle management in Jenkins, optimizing cloud compute expenditure by **30% ($150K+ annually)**.",
                evidence_ids=["EXP-HSBC-COST-001"],
                technologies=["Jenkins", "GCP Dataflow", "Cloud Cost Optimization"],
            ),
        ],
        projects=[
            LLMProjectItem(
                name="Distributed Rate Limiter Service",
                evidence_ids=["PRJ-RL-001"],
                bullets=[
                    LLMBulletItem(
                        text="Designed high-throughput token bucket rate limiter in Java and Spring Boot achieving **100K+ RPS benchmark** throughput using Redis cluster caching and PostgreSQL.",
                        evidence_ids=["PRJ-RL-001"],
                        technologies=["Java", "Spring Boot", "Redis", "PostgreSQL"],
                    )
                ],
                technologies=["Java", "Spring Boot", "Redis", "PostgreSQL"],
            ),
            LLMProjectItem(
                name="MCP Diagnostic Tools for Data Pipelines",
                evidence_ids=["PRJ-MCP-001"],
                bullets=[
                    LLMBulletItem(
                        text="Built diagnostic toolsuite integrating Claude AI with Google Cloud operations for automated root-cause analysis across streaming pipelines.",
                        evidence_ids=["PRJ-MCP-001"],
                        technologies=["Python", "MCP", "BigQuery", "Dataflow"],
                    )
                ],
                technologies=["Python", "MCP", "BigQuery", "Dataflow"],
            ),
        ],
        skill_groups=[
            LLMSkillGroupItem(
                category="Languages & Backend Frameworks",
                skills=["Java", "Spring Boot", "Python", "Microservices", "REST APIs"],
            ),
            LLMSkillGroupItem(
                category="Cloud & Data Streaming",
                skills=["Google Cloud Platform (GCP)", "Apache Beam", "GCP Dataflow", "BigQuery", "Cloud Pub/Sub"],
            ),
            LLMSkillGroupItem(
                category="DevOps & Infrastructure",
                skills=["Terraform", "Docker", "Kubernetes", "Jenkins", "CI/CD"],
            ),
        ],
        tailoring_rationale="Tailored for Backend Java & GCP payment platform engineering.",
    )


# ==============================================================================
# 1. Provider Abstraction & Fallback Tests
# ==============================================================================

def test_missing_api_key_falls_back_to_deterministic():
    """Verify that when no API key is set, provider is unavailable and generator falls back seamlessly."""
    provider = OpenAICompatibleResumeProvider(api_key=None)
    assert provider.is_available() is False
    assert provider.generate_resume_draft("sys", "user") is None


def test_custom_provider_abstraction():
    """Verify that any provider implementing LLMResumeProvider works with LLMResumeWriter."""
    mock_provider = MockLLMProvider(should_fail=False)
    writer = LLMResumeWriter(provider=mock_provider)
    assert writer.is_available() is True


def test_writer_falls_back_when_provider_returns_none(service, candidate_profile):
    """When LLM provider returns None, LLMResumeWriter returns None (triggering deterministic fallback)."""
    failing_provider = MockLLMProvider(draft_to_return=None)
    writer = LLMResumeWriter(provider=failing_provider)
    strat = service.get_strategy("backend_java")

    res = writer.generate_tailored_resume(candidate_profile, strat)
    assert res is None


# ==============================================================================
# 2. Grounding & Truth Invariant Validation Tests
# ==============================================================================

def test_evidence_grounding_validation_success(valid_llm_draft, candidate_profile):
    """Valid draft containing only verified facts and metrics passes grounding validation."""
    validator = GroundingValidator()
    is_valid, errors = validator.validate(valid_llm_draft, candidate_profile)
    assert is_valid is True
    assert len(errors) == 0


def test_unsupported_metric_rejected(valid_llm_draft, candidate_profile):
    """Invented metrics (e.g. 50M+ daily transactions, $1M cost savings) must be rejected."""
    validator = GroundingValidator()
    
    # Inject fabricated 50M+ metric
    valid_llm_draft.experience_bullets[0].text = (
        "Architected real-time Apache Beam pipelines ingesting **50M+ daily payment transactions** into BigQuery."
    )
    is_valid, errors = validator.validate(valid_llm_draft, candidate_profile)
    assert is_valid is False
    assert any("50m+" in err.lower() or "unverified metric" in err.lower() for err in errors)


def test_unsupported_technology_rejected(valid_llm_draft, candidate_profile):
    """Unconfirmed technologies (such as AWS or Kafka) must be rejected."""
    validator = GroundingValidator()

    # Inject unconfirmed technology in skills
    valid_llm_draft.skill_groups[1].skills.append("AWS")
    is_valid, errors = validator.validate(valid_llm_draft, candidate_profile)
    assert is_valid is False
    assert any("aws" in err.lower() for err in errors)


def test_production_vs_benchmark_distinction(valid_llm_draft, candidate_profile):
    """Claiming the 100K+ RPS benchmark as enterprise production must be rejected."""
    validator = GroundingValidator()

    # Claim benchmark as HSBC production work
    valid_llm_draft.experience_bullets.append(
        LLMBulletItem(
            text="Deployed 100K+ RPS rate limiter into HSBC production environment.",
            evidence_ids=["EXP-HSBC-BEAM-001"],
        )
    )
    is_valid, errors = validator.validate(valid_llm_draft, candidate_profile)
    assert is_valid is False
    assert any("rate limiter" in err.lower() or "benchmark" in err.lower() for err in errors)


def test_unauthorized_evidence_id_rejected(valid_llm_draft, candidate_profile):
    """Citing a non-existent or fake evidence ID must be rejected."""
    validator = GroundingValidator()
    valid_llm_draft.experience_bullets[0].evidence_ids = ["EXP-FAKE-001"]

    is_valid, errors = validator.validate(valid_llm_draft, candidate_profile)
    assert is_valid is False
    assert any("EXP-FAKE-001" in err for err in errors)


# ==============================================================================
# 3. Retry with Validation Feedback Tests
# ==============================================================================

def test_writer_retries_with_error_feedback(candidate_profile, service, valid_llm_draft):
    """When the initial draft has an error, LLMResumeWriter retries with error feedback."""
    # First draft has invalid metric '99.999%'
    bad_draft = valid_llm_draft.model_copy(deep=True)
    bad_draft.experience_bullets[0].text = "Apache Beam pipelines maintaining **99.999% uptime**."

    # Second draft is clean and valid
    good_draft = valid_llm_draft.model_copy(deep=True)

    class TwoStageMockProvider(LLMResumeProvider):
        def __init__(self):
            self.calls = 0
            self.received_retry_error = None

        def is_available(self):
            return True

        def generate_resume_draft(self, system_prompt, user_prompt, retry_error=None):
            self.calls += 1
            if self.calls == 1:
                return bad_draft
            self.received_retry_error = retry_error
            return good_draft

    provider = TwoStageMockProvider()
    writer = LLMResumeWriter(provider=provider)
    strat = service.get_strategy("backend_java")

    res = writer.generate_tailored_resume(candidate_profile, strat)
    assert res is not None
    assert provider.calls == 2
    assert provider.received_retry_error is not None
    assert "99.999%" in provider.received_retry_error or "unverified metric" in provider.received_retry_error.lower()


# ==============================================================================
# 4. End-to-End PDF Compilation & Integration Tests
# ==============================================================================

def test_successful_jd_specific_tailoring_and_1_page_pdf(service, valid_llm_draft):
    """Verify that a valid LLM draft renders to LaTeX and compiles to a 1-page PDF."""
    provider = MockLLMProvider(draft_to_return=valid_llm_draft)
    writer = LLMResumeWriter(provider=provider)
    service.llm_writer = writer

    sample_jd = """
    Stripe is seeking a Backend Software Engineer to join our Payments Infrastructure team.
    Requirements:
    - 3+ years experience with Java, Spring Boot, or Python in backend systems.
    - Deep knowledge of Google Cloud Platform (GCP), distributed streaming, and BigQuery.
    - Hands-on infrastructure automation with Terraform.
    - Experience maintaining 99.9% uptime across high-throughput financial pipelines.
    """

    res = service.generate_tailored_resume("backend_java", job_description_text=sample_jd)

    assert res.validation.is_valid is True
    assert res.validation.pdf_generated is True
    assert res.validation.page_count == 1
    assert len(res.validation.truth_violations) == 0
    assert res.tailored_resume.metadata.get("llm_tailored") is True

    # Check that canonical employment facts remain completely unchanged
    assert res.tailored_resume.personal_info.full_name == "Kulmeet Singh Jaggi"
    assert res.tailored_resume.experience[0].company == "HSBC"
    assert res.tailored_resume.experience[0].role == "Software Engineer"
    assert res.tailored_resume.education[0].institution == "Graphic Era Deemed to be University"

    # Check that tailored summary reflects target role
    assert "payment" in res.tailored_resume.summary.lower()
    assert "google cloud" in res.tailored_resume.summary.lower()


def test_fallback_to_deterministic_when_llm_unconfigured(service):
    """When no LLM API key is provided, resume generation still succeeds via deterministic selector."""
    service.llm_writer = LLMResumeWriter(provider=OpenAICompatibleResumeProvider(api_key=None))

    sample_jd = "Senior Software Engineer — Google Cloud Platform & Terraform"
    res = service.generate_tailored_resume("cloud_devops", job_description_text=sample_jd)

    assert res.validation.is_valid is True
    assert res.validation.pdf_generated is True
    assert res.validation.page_count == 1
    assert res.tailored_resume.metadata.get("llm_tailored") is not True  # Deterministic path
