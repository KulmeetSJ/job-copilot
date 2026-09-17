"""Focused unit and integration tests for LLM Resume Tailoring, Provider Abstraction,
Evidence Grounding, and Deterministic Fallback."""

import pytest

from job_copilot.resume.analyzer import JobDescriptionAnalyzer, derive_dominant_themes
from job_copilot.resume.llm.models import (
    LLMBulletItem,
    LLMProjectItem,
    LLMResumeDraft,
    LLMSkillGroupItem,
)
from job_copilot.resume.llm.prompts import (
    build_grounded_resume_prompt,
    rank_ats_keywords,
    rank_responsibilities,
)
from job_copilot.resume.llm.provider import (
    LLMResumeProvider,
    OpenAICompatibleResumeProvider,
)
from job_copilot.resume.llm.validator import (
    GroundingValidator,
    resolve_canonical_project,
)
from job_copilot.resume.llm.writer import LLMResumeWriter
from job_copilot.resume.models import JobAnalysis, JobRequirement, JobRequirementType
from job_copilot.resume.validator import ResumeValidator
from job_copilot.schemas.candidate import Achievement, Experience
from job_copilot.services.resume_service import ResumeService


class MockLLMProvider(LLMResumeProvider):
    """Mock LLM Provider returning pre-configured drafts or simulated errors."""

    def __init__(self, draft_to_return: LLMResumeDraft | None = None, should_fail: bool = False):
        self.draft_to_return = draft_to_return
        self.should_fail = should_fail
        self.call_count = 0
        self.last_retry_error: str | None = None

    def is_available(self) -> bool:
        return not self.should_fail

    def generate_resume_draft(
        self,
        system_prompt: str,
        user_prompt: str,
        retry_error: str | None = None,
    ) -> LLMResumeDraft | None:
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
                text="Engineered CI/CD pipelines in Jenkins integrating SonarQube, Checkmarx, and Nexus for **100+ Cloud Composer (Airflow) DAG deployments**, automating releases.",
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
# 3. Explicit Adversarial Tests (Requirement 7)
# ==============================================================================

def test_adversarial_valid_evidence_id_plus_invented_metric(valid_llm_draft, candidate_profile):
    """
    Adversarial Case 1: Valid evidence ID + invented metric.
    EXP-HSBC-TF-001 supports 2,000+ resources and 60% acceleration.
    Injecting '95%' or '50M+' must fail deterministically.
    Expected Result: FAIL (is_valid is False)
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.experience_bullets[1].text = (
        "Provisioned **2,000+ GCP resources** using Terraform IaC modules, accelerating cycle time by **95%**."
    )
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("95%" in err and "unverified metric" in err.lower() for err in errors)


def test_adversarial_valid_evidence_id_plus_unsupported_technology(valid_llm_draft, candidate_profile):
    """
    Adversarial Case 2: Valid evidence ID + unsupported technology.
    EXP-HSBC-TF-001 does not include AWS or Kafka.
    Expected Result: FAIL (is_valid is False)
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.experience_bullets[1].text = (
        "Provisioned **2,000+ AWS resources** using modular Terraform IaC."
    )
    draft.experience_bullets[1].technologies = ["Terraform", "AWS"]
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("aws" in err.lower() for err in errors)


def test_adversarial_valid_evidence_id_plus_unsupported_claim_like_architected(valid_llm_draft, candidate_profile):
    """
    Adversarial Case 3: Valid evidence ID + unsupported verb like 'Architected'.
    EXP-HSBC-TF-001 supports 'Provisioned 2,000+ GCP resources', not 'Architected'.
    Expected Result: FAIL (is_valid is False)
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.experience_bullets[1].text = (
        "Architected enterprise Terraform IaC modules for **2,000+ GCP resources**, accelerating deployment by **60%**."
    )
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("architected" in err.lower() or "architectural ownership" in err.lower() for err in errors)


def test_adversarial_unknown_skill(valid_llm_draft, candidate_profile):
    """
    Adversarial Case 4: Unknown skill not confirmed in CandidateProfile.
    Injecting 'Kubeflow' or 'Snowflake' must invalidate the draft.
    Expected Result: FAIL (is_valid is False)
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.skill_groups[0].skills.append("Kubeflow")
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("kubeflow" in err.lower() and "unknown or unconfirmed skill" in err.lower() for err in errors)


def test_adversarial_certification_not_present_in_profile(valid_llm_draft, candidate_profile):
    """
    Adversarial Case 5: Certification not present in canonical profile.
    Candidate only has GCP PCA. Hallucinating 'AWS Certified Solutions Architect' must fail.
    Expected Result: FAIL (is_valid is False)
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.summary = (
        "AWS Certified Solutions Architect with 3+ years experience engineering scalable cloud systems at HSBC."
    )
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("unconfirmed certification" in err.lower() for err in errors)


def test_adversarial_project_benchmark_presented_as_production(valid_llm_draft, candidate_profile):
    """
    Adversarial Case 6: Project benchmark presented as production.
    The Rate Limiter '100K+ RPS' was a local/demo benchmark, not production infrastructure.
    Expected Result: FAIL (is_valid is False)
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.projects[0].bullets[0].text = (
        "Deployed token bucket rate limiter achieving **100K+ RPS** in production environment at HSBC."
    )
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("production" in err.lower() for err in errors)


def test_adversarial_valid_bullet_that_should_pass(valid_llm_draft, candidate_profile):
    """
    Adversarial Case 7: Valid bullet that should pass.
    Fully grounded bullet citing EXP-HSBC-BEAM-001 with supported verb, metric, and tech.
    Expected Result: PASS (is_valid is True, 0 errors)
    """
    validator = GroundingValidator()
    is_valid, errors = validator.validate(valid_llm_draft, candidate_profile)
    assert is_valid is True
    assert len(errors) == 0


def test_adversarial_valid_project_evidence_in_experience_fails(valid_llm_draft, candidate_profile):
    """
    Adversarial Requirement 7.1:
    Valid project evidence ID (e.g. PRJ-RL-001 or PRJ-MCP-001) used in HSBC experience -> FAIL.
    Experience bullets may cite ONLY employment evidence IDs. Project evidence IDs must be rejected.
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.experience_bullets[0].evidence_ids = ["PRJ-RL-001"]
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("experience bullets may cite only employment evidence ids" in err.lower() for err in errors)


def test_adversarial_hsbc_evidence_in_unrelated_project_fails(valid_llm_draft, candidate_profile):
    """
    Adversarial Requirement 7.2:
    HSBC employment evidence (e.g. EXP-HSBC-TF-001) used in unrelated project (e.g. Rate Limiter) -> FAIL.
    Project bullets may cite ONLY evidence belonging to that specific canonical project.
    """
    validator = GroundingValidator()
    # 1. Project bullet cites employment evidence
    draft = valid_llm_draft.model_copy(deep=True)
    draft.projects[0].bullets[0].evidence_ids = ["EXP-HSBC-TF-001"]
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("project bullets may cite only evidence belonging to that specific canonical project" in err.lower() for err in errors)

    # 2. Project cites another project's evidence (e.g. PRJ-MCP-001 in Rate Limiter)
    draft2 = valid_llm_draft.model_copy(deep=True)
    draft2.projects[0].bullets[0].evidence_ids = ["PRJ-MCP-001"]
    is_valid2, errors2 = validator.validate(draft2, candidate_profile)
    assert is_valid2 is False
    assert any("project bullets may cite only evidence belonging to that specific canonical project" in err.lower() for err in errors2)


def test_adversarial_valid_project_benchmark_rewritten_as_production_fails(valid_llm_draft, candidate_profile):
    """
    Adversarial Requirement 7.3:
    Valid project benchmark rewritten as production -> FAIL.
    Rate Limiter deployment status is PORTFOLIO_DEMO and claim type is BENCHMARK in CandidateProfile.
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.projects[0].bullets[0].text = (
        "Engineered token bucket rate limiter deployed into live production Kubernetes clusters serving 100K+ RPS."
    )
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("claims simulated benchmark/demo project" in err.lower() and "production" in err.lower() for err in errors)


def test_adversarial_valid_evidence_with_invented_business_impact_fails(valid_llm_draft, candidate_profile):
    """
    Adversarial Requirement 7.4:
    Valid evidence ID with invented business impact / revenue / cost savings -> FAIL.
    Citing EXP-HSBC-BEAM-001 with '$5M annual cost savings' or '10x revenue growth'.
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.experience_bullets[0].text = (
        "Architected real-time Apache Beam pipelines ingesting **10M+ daily payment transactions** into BigQuery, generating **$5M annual cost savings**."
    )
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("unverified metric" in err.lower() and "$5m" in err.lower() for err in errors)


def test_adversarial_valid_evidence_with_unsupported_ownership_leadership_fails(valid_llm_draft, candidate_profile):
    """
    Adversarial Requirement 7.5:
    Valid evidence with unsupported ownership/leadership -> FAIL.
    - Leadership: 'Led a team of 6 engineers' or 'Managed a team of developers'
    - Ownership: 'Architected...' when citing EXP-HSBC-TF-001 (which only substantiates 'Provisioned')
    """
    validator = GroundingValidator()

    # 1. Unsupported leadership claim
    draft_leadership = valid_llm_draft.model_copy(deep=True)
    draft_leadership.experience_bullets[0].text = (
        "Led a team of 6 engineers architecting real-time Apache Beam pipelines ingesting **10M+ daily payment transactions**."
    )
    is_valid_lead, errors_lead = validator.validate(draft_leadership, candidate_profile)
    assert is_valid_lead is False
    assert any("unsupported leadership/management" in err.lower() for err in errors_lead)

    # 2. Unsupported ownership verb
    draft_ownership = valid_llm_draft.model_copy(deep=True)
    draft_ownership.experience_bullets[1].text = (
        "Architected Terraform IaC modules for **2,000+ GCP resources**, accelerating provisioning by **60%**."
    )
    is_valid_own, errors_own = validator.validate(draft_ownership, candidate_profile)
    assert is_valid_own is False
    assert any("claims 'architected' or architectural ownership" in err.lower() for err in errors_own)


def test_canonical_project_metadata_comes_from_profile(candidate_profile, valid_llm_draft, service):
    """
    Adversarial Requirement 7.6:
    Canonical project metadata (canonical name, claim_type, deployment_status, metric_type)
    must come dynamically from CandidateProfile rather than hard-coded name matching.
    """
    # 1. Verify resolve_canonical_project resolves various LLM phrasing cleanly
    resolved_rl = resolve_canonical_project("Distributed Rate Limiter", candidate_profile)
    assert resolved_rl is not None
    assert resolved_rl.name == "Distributed Rate Limiter Service"
    assert resolved_rl.claim_type == "BENCHMARK"
    assert resolved_rl.deployment_status == "PORTFOLIO_DEMO"

    resolved_mcp = resolve_canonical_project("MCP Diagnostic Tools", candidate_profile)
    assert resolved_mcp is not None
    assert resolved_mcp.name == "MCP Diagnostic Tools for Data Pipelines"
    assert resolved_mcp.claim_type == "PERSONAL_PROJECT"
    assert resolved_mcp.deployment_status == "PORTFOLIO_DEMO"

    # Unknown project returns None
    assert resolve_canonical_project("Unknown Crypto Trader", candidate_profile) is None

    # 2. Verify LLMResumeWriter._build_tailored_resume derives metadata strictly from profile
    writer = LLMResumeWriter(provider=MockLLMProvider())
    strat = service.get_strategy("backend_java")
    tailored = writer._build_tailored_resume(valid_llm_draft, candidate_profile, strat)

    # Distributed Rate Limiter Service must inherit BENCHMARK from CandidateProfile
    p_rl = next(p for p in tailored.projects if "Rate Limiter" in p.name)
    assert p_rl.name == "Distributed Rate Limiter Service"
    assert p_rl.deployment_status == "PORTFOLIO_DEMO"
    assert p_rl.bullets[0].claim_type == "BENCHMARK"
    assert p_rl.bullets[0].metric_type == "BENCHMARK"

    # MCP Diagnostic Tools must inherit PERSONAL_PROJECT from CandidateProfile
    p_mcp = next(p for p in tailored.projects if "MCP" in p.name)
    assert p_mcp.name == "MCP Diagnostic Tools for Data Pipelines"
    assert p_mcp.deployment_status == "PORTFOLIO_DEMO"
    assert p_mcp.bullets[0].claim_type == "PERSONAL_PROJECT"
    assert p_mcp.bullets[0].metric_type == "PROJECT"


def test_adversarial_project_evidence_in_correct_project_passes(valid_llm_draft, candidate_profile):
    """
    Test C: Project evidence cited in its correct canonical project must PASS.
    PRJ-RL-001 in Distributed Rate Limiter Service and PRJ-MCP-001 in MCP Diagnostic Tools.
    """
    validator = GroundingValidator()
    is_valid, errors = validator.validate(valid_llm_draft, candidate_profile)
    assert is_valid is True
    assert len(errors) == 0


def test_adversarial_unknown_project_alias_cannot_bypass_ownership(valid_llm_draft, candidate_profile):
    """
    Test F: Unknown or hardcoded project alias cannot bypass ownership -> FAIL.
    An LLM cannot introduce a non-existent project (e.g. 'Arbitrary Crypto Trading Bot')
    even if it cites valid evidence IDs.
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.projects[0].name = "Arbitrary Crypto Trading Bot"
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("not in candidate's verified projects" in err.lower() for err in errors)


def test_adversarial_unsupported_latency_scale_claim_fails(valid_llm_draft, candidate_profile):
    """
    Test I: Unsupported latency/scale claim without evidence grounding -> FAIL.
    Citing EXP-HSBC-TF-001 while claiming 'sub-second latency' and 'millions of transactions'.
    """
    validator = GroundingValidator()
    draft = valid_llm_draft.model_copy(deep=True)
    draft.experience_bullets[1].text = (
        "Provisioned **2,000+ GCP resources** using Terraform IaC modules with sub-second latency serving millions of transactions."
    )
    is_valid, errors = validator.validate(draft, candidate_profile)
    assert is_valid is False
    assert any("latency" in err.lower() or "scale" in err.lower() for err in errors)


def test_canonical_employer_title_dates_cannot_be_overwritten(valid_llm_draft, candidate_profile, service):
    """
    Test L: Canonical employer, title, and dates cannot be overwritten by LLM -> PASS with canonical values.
    The writer must enforce company='HSBC', role='Software Engineer', start_date='2024-07', etc. from CandidateProfile.
    """
    writer = LLMResumeWriter(provider=MockLLMProvider())
    strat = service.get_strategy("backend_java")
    tailored = writer._build_tailored_resume(valid_llm_draft, candidate_profile, strat)

    canonical_emp = candidate_profile.employment[0]
    res_emp = tailored.experience[0]

    assert res_emp.company == canonical_emp.company
    assert res_emp.role == canonical_emp.role
    assert res_emp.start_date == canonical_emp.start_date
    assert res_emp.end_date == canonical_emp.end_date
    assert res_emp.location == canonical_emp.location


# ==============================================================================
# 4. Retry with Validation Feedback Tests
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
# 5. End-to-End Actual ResumeService Integration Tests (Requirement 8)
# ==============================================================================

def test_resumeservice_uses_valid_llm_writer_output(service, valid_llm_draft):
    """
    Verify actual integration path:
    JD -> ResumeService.generate_tailored_resume() -> LLM writer -> validated TailoredResume
    actually uses the LLM-generated content when the provider returns a valid draft.
    """
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

    # 1. Verify LLM tailored draft was used
    assert res.tailored_resume.metadata.get("llm_tailored") is True
    assert res.tailored_resume.summary == valid_llm_draft.summary
    assert res.tailored_resume.experience[0].bullets[0].text == valid_llm_draft.experience_bullets[0].text
    assert res.tailored_resume.projects[0].name == valid_llm_draft.projects[0].name

    # 2. Verify PDF generation and 1-page compliance
    assert res.validation.is_valid is True
    assert res.validation.pdf_generated is True
    assert res.validation.page_count == 1
    assert len(res.validation.truth_violations) == 0

    # 3. Canonical employment facts strictly preserved from CandidateProfile
    assert res.tailored_resume.personal_info.full_name == "Kulmeet Singh Jaggi"
    assert res.tailored_resume.experience[0].company == "HSBC"
    assert res.tailored_resume.experience[0].role == "Software Engineer"
    assert res.tailored_resume.experience[0].location == "Pune, India"
    assert res.tailored_resume.education[0].institution == "Graphic Era Deemed to be University"


def test_resumeservice_falls_back_when_llm_writer_output_invalid(service, valid_llm_draft):
    """
    Verify actual integration path:
    JD -> ResumeService.generate_tailored_resume() -> LLM writer -> invalid draft -> deterministic fallback.
    Must fall back cleanly to deterministic selector and still generate a valid 1-page resume.
    """
    bad_draft = valid_llm_draft.model_copy(deep=True)
    # Inject invented metric that fails validation
    bad_draft.experience_bullets[0].text = (
        "Architected real-time Apache Beam pipelines ingesting **500M+ daily payment transactions** into BigQuery."
    )

    provider = MockLLMProvider(draft_to_return=bad_draft)
    writer = LLMResumeWriter(provider=provider)
    service.llm_writer = writer

    sample_jd = "Senior Software Engineer — Google Cloud Platform & Terraform"
    res = service.generate_tailored_resume("backend_java", job_description_text=sample_jd)

    # 1. Verify fallback to deterministic generator happened
    assert res.tailored_resume.metadata.get("llm_tailored") is not True

    # 2. Verify resume is still valid and compiles to 1-page PDF
    assert res.validation.is_valid is True
    assert res.validation.pdf_generated is True
    assert res.validation.page_count == 1
    assert len(res.validation.truth_violations) == 0


# ==============================================================================
# 6. Batch 2 Quality & Dominant Themes Regression Tests
# ==============================================================================

def test_materially_different_jds_cause_different_dominant_themes():
    """
    Verify that materially different JDs derive distinct dominant technical themes:
    - JD A: Java/Spring backend + distributed systems
    - JD B: GCP/Dataflow/BigQuery + data streaming
    """
    analyzer = JobDescriptionAnalyzer()

    jd_java = """
    Senior Java Backend Software Engineer
    Company: FinTech Core
    We are seeking a Senior Backend Engineer to build high-throughput payment microservices.
    Requirements:
    - 4+ years of Java and Spring Boot backend architecture.
    - Deep knowledge of distributed systems, concurrency, and transaction processing.
    - REST APIs and microservices design.
    - Relational databases (PostgreSQL) and caching.
    """
    analysis_java = analyzer.analyze(jd_java)
    assert "Java/Spring backend development" in analysis_java.dominant_themes
    assert any(t in analysis_java.dominant_themes for t in ["distributed systems/payment processing", "microservices/API engineering"])
    assert "GCP/data platform engineering" not in analysis_java.dominant_themes

    jd_gcp = """
    GCP Data Platform Engineer
    Company: CloudData Corp
    Looking for a Data Platform Engineer to design scalable cloud streaming pipelines.
    Requirements:
    - Expertise with Google Cloud Platform (GCP), BigQuery, and GCP Dataflow.
    - Real-time pipeline engineering using Apache Beam.
    - Data orchestration using Apache Airflow or Cloud Composer.
    - Cloud Pub/Sub and ETL data platform architecture.
    """
    analysis_gcp = analyzer.analyze(jd_gcp)
    assert "GCP/data platform engineering" in analysis_gcp.dominant_themes
    assert any(t in analysis_gcp.dominant_themes for t in ["data streaming/ETL pipelines", "infrastructure/DevOps"])
    assert "Java/Spring backend development" not in analysis_gcp.dominant_themes


def test_different_jds_generate_different_prompt_emphasis(candidate_profile):
    """
    Verify that materially different JDs result in prompts with different dominant theme instructions
    guiding experience bullet selection, ordering, and skills emphasis.
    """
    analyzer = JobDescriptionAnalyzer()

    jd_java = """
    Backend Java Engineer
    Requirements:
    - Java, Spring Boot, Microservices, Distributed Systems.
    """
    analysis_java = analyzer.analyze(jd_java)
    prompt_java = build_grounded_resume_prompt(candidate_profile, analysis_java, "backend_java")

    jd_gcp = """
    GCP Cloud Data Engineer
    Requirements:
    - GCP, BigQuery, Dataflow, Apache Beam, Cloud Composer.
    """
    analysis_gcp = analyzer.analyze(jd_gcp)
    prompt_gcp = build_grounded_resume_prompt(candidate_profile, analysis_gcp, "gcp_cloud")

    assert "Java/Spring backend development" in prompt_java
    assert "GCP/data platform engineering" not in prompt_java

    assert "GCP/data platform engineering" in prompt_gcp
    assert "Java/Spring backend development" not in prompt_gcp

    assert prompt_java != prompt_gcp


def test_different_jds_guide_different_claude_output_selection(service, candidate_profile, valid_llm_draft):
    """
    Verify that different target JDs yield tailored resumes reflecting their respective dominant themes
    in metadata, summary, bullet ordering, and skill groups.
    """
    # Draft tailored for Java Backend
    draft_java = valid_llm_draft.model_copy(deep=True)
    draft_java.dominant_themes = ["Java/Spring backend development", "distributed systems/payment processing"]
    draft_java.summary = "Software Engineer specializing in Java, Spring Boot, and distributed payment systems."
    draft_java.tailoring_rationale = "Emphasized Java/Spring backend and distributed systems."

    # Draft tailored for GCP Cloud Platform
    draft_gcp = valid_llm_draft.model_copy(deep=True)
    draft_gcp.dominant_themes = ["GCP/data platform engineering", "infrastructure/DevOps"]
    draft_gcp.summary = "Software Engineer specializing in Google Cloud Platform (GCP) infrastructure and Terraform."
    draft_gcp.tailoring_rationale = "Emphasized GCP platform engineering and IaC automation."
    # Reorder bullets so GCP Terraform is #1
    draft_gcp.experience_bullets = [
        valid_llm_draft.experience_bullets[1],  # Terraform
        valid_llm_draft.experience_bullets[0],  # Beam/Dataflow
        valid_llm_draft.experience_bullets[2],  # Jenkins/Airflow
        valid_llm_draft.experience_bullets[3],  # Cost savings
    ]

    writer_java = LLMResumeWriter(provider=MockLLMProvider(draft_to_return=draft_java))
    writer_gcp = LLMResumeWriter(provider=MockLLMProvider(draft_to_return=draft_gcp))

    strat = service.get_strategy("backend_java")
    tailored_java = writer_java.generate_tailored_resume(candidate_profile, strat)
    tailored_gcp = writer_gcp.generate_tailored_resume(candidate_profile, strat)

    assert tailored_java is not None
    assert tailored_gcp is not None

    # Dominant themes in metadata differ
    assert "Java/Spring backend development" in tailored_java.metadata["dominant_themes"]
    assert "GCP/data platform engineering" in tailored_gcp.metadata["dominant_themes"]

    # First bullet emphasis differs
    assert "Java" in tailored_java.experience[0].bullets[0].text or "Beam" in tailored_java.experience[0].bullets[0].text
    assert "Terraform" in tailored_gcp.experience[0].bullets[0].text or "GCP" in tailored_gcp.experience[0].bullets[0].text


def test_importance_ranking_preserves_late_occurring_requirements():
    """
    Verify that important technical requirements are not lost merely because they occur
    later in the input list (e.g. index 8 after generic responsibilities, or late in keywords).
    """
    analysis = JobAnalysis(
        job_title="Senior Backend Engineer",
        required_skills=[
            JobRequirement(name="Java", normalized_name="Java", is_required=True),
            JobRequirement(name="Spring Boot", normalized_name="Spring Boot", is_required=True),
            JobRequirement(name="Terraform", normalized_name="Terraform", is_required=True),
        ],
        ats_keywords=[
            "Agile", "Scrum", "Jira", "Slack", "Git", "Clean Code", "Collaboration",
            "Communication", "Documentation", "Problem Solving", "Unit Testing",
            "Code Reviews", "Pair Programming", "Standups", "Design Patterns",
            "CI/CD", "Docker", "Spring Boot", "Terraform", "Java",
        ],
        responsibilities=[
            "Attend daily standup meetings and participate in sprint ceremonies.",
            "Coordinate with product managers and stakeholders on requirement specifications.",
            "Document system design decisions and maintain internal engineering wikis.",
            "Review pull requests and provide constructive feedback to teammates.",
            "Support team onboarding and mentor junior engineers.",
            "Participate in weekly team syncs and retrospectives.",
            "Assist in triage of customer-reported tickets.",
            # Critical technical responsibility placed at position 8
            "Architect high-throughput distributed Java and Spring Boot microservices processing real-time payment transactions with 99.9% uptime SLA.",
        ],
    )

    # 1. Verify importance-ranked responsibilities
    ranked_resps = rank_responsibilities(analysis, limit=5)
    assert len(ranked_resps) == 5
    # The technical responsibility from position 8 must be prioritized in the top 5
    assert any("Architect high-throughput" in r for r in ranked_resps)
    # The top-ranked responsibility must be the high-impact technical one, not the standup meeting
    assert "Architect high-throughput" in ranked_resps[0]

    # 2. Verify importance-ranked keywords
    ranked_keywords = rank_ats_keywords(analysis, limit=15)
    assert len(ranked_keywords) <= 15
    # Required skills located at indices 17, 18, 19 must NOT be dropped
    assert "Java" in ranked_keywords
    assert "Spring Boot" in ranked_keywords
    assert "Terraform" in ranked_keywords


def test_multi_employment_support_with_multiple_employers(valid_llm_draft, candidate_profile):
    """
    Verify that when candidate profile contains multiple employment entries,
    the resume builder partitions experience bullets to their matching employers
    based on evidence IDs rather than blindly assuming index 0.
    """
    # Create multi-employer profile
    multi_profile = candidate_profile.model_copy(deep=True)
    second_emp = Experience(
        company="Fintech Innovations Labs",
        role="Junior Software Engineer",
        canonical_role="Software Engineer",
        location="Bengaluru, India",
        start_date="2023-01",
        end_date="2024-06",
        current=False,
        evidence_ids=["EXP-FIN-001"],
        achievements=[
            Achievement(
                description="Built automated data verification scripts in Python.",
                claim_type="PROFESSIONAL",
                metrics=["100+ automated tests"],
                technologies=["Python", "SQL"],
                evidence_ids=["EXP-FIN-DATA-001"],
            )
        ],
    )
    multi_profile.employment.append(second_emp)

    # Create draft containing bullets for both employers
    draft = valid_llm_draft.model_copy(deep=True)
    draft.experience_bullets.append(
        LLMBulletItem(
            text="Built automated data verification scripts in Python maintaining **100+ automated tests**.",
            evidence_ids=["EXP-FIN-DATA-001"],
            technologies=["Python", "SQL"],
        )
    )

    writer = LLMResumeWriter(provider=MockLLMProvider())
    from job_copilot.resume.strategy import ResumeStrategyConfig
    strat = ResumeStrategyConfig(
        name="backend_java",
        display_title="Software Engineer",
        summary_template="Test summary",
        max_bullets_per_experience=5,
        max_projects=2,
    )
    tailored = writer._build_tailored_resume(draft, multi_profile, strat)

    # Must contain 2 distinct experience entries corresponding to the 2 employers
    assert len(tailored.experience) == 2
    hsbc_exp = next((e for e in tailored.experience if e.company == "HSBC"), None)
    fin_exp = next((e for e in tailored.experience if e.company == "Fintech Innovations Labs"), None)

    assert hsbc_exp is not None
    assert fin_exp is not None
    # Bullets were partitioned to the correct employer
    assert all("EXP-HSBC" in b.evidence_ids[0] for b in hsbc_exp.bullets)
    assert any("EXP-FIN-DATA-001" in b.evidence_ids for b in fin_exp.bullets)

    # Multi-employment validation passes cleanly
    validator = ResumeValidator()
    val_res = validator.validate(tailored, multi_profile)
    assert len(val_res.truth_violations) == 0


def test_validation_failure_observability_telemetry(candidate_profile, valid_llm_draft):
    """
    Verify that when an LLM draft fails validation, structured diagnostic telemetry is logged
    with stage (retry/fallback), job_id, failure category, and provider/model metadata,
    without logging candidate secrets, API keys, or full personal data.
    """
    bad_draft = valid_llm_draft.model_copy(deep=True)
    # Inject fabricated metric and unconfirmed skill
    bad_draft.experience_bullets[0].text = "Ingesting **999M+ daily transactions**."
    bad_draft.skill_groups[0].skills.append("Kubeflow")

    failing_provider = MockLLMProvider(draft_to_return=bad_draft)
    writer = LLMResumeWriter(provider=failing_provider)
    from job_copilot.resume.strategy import ResumeStrategyConfig
    strat = ResumeStrategyConfig(
        name="backend_java",
        display_title="Software Engineer",
        summary_template="Test summary",
    )

    import logging
    from job_copilot.resume.llm.writer import logger as writer_logger

    writer_logger.disabled = False
    captured_records: list[logging.LogRecord] = []

    class RecordCaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured_records.append(record)

    test_handler = RecordCaptureHandler()
    writer_logger.addHandler(test_handler)
    try:
        res = writer.generate_tailored_resume(
            candidate_profile,
            strat,
            job_id="job-observability-test-999",
        )
    finally:
        writer_logger.removeHandler(test_handler)

    # Must fall back cleanly
    assert res is None

    # Diagnostic logs were emitted for retry and fallback stages
    diag_logs = [record.getMessage() for record in captured_records if "[RESUME_VALIDATION_DIAGNOSTIC]" in record.getMessage()]
    assert len(diag_logs) >= 2

    retry_log = next(log for log in diag_logs if "stage=retry" in log)
    fallback_log = next(log for log in diag_logs if "stage=fallback" in log)

    assert "job_id=job-observability-test-999" in retry_log
    assert "provider=MockLLMProvider" in retry_log
    assert "METRIC_GROUNDING_VIOLATION" in retry_log or "UNCONFIRMED_TECHNOLOGY" in retry_log

    assert "job_id=job-observability-test-999" in fallback_log
    assert "stage=fallback" in fallback_log

    # Verify no sensitive personal secrets/profile leaks in log records
    for record in captured_records:
        msg = record.getMessage()
        assert "7906490585" not in msg
        assert "singhkulmeet3@gmail.com" not in msg


def test_unrelated_jd_dominant_themes_fallback_safe(service, candidate_profile, valid_llm_draft):
    """
    Verify that an unrelated JD (e.g. Python / Computer Vision / ML) where the deterministic
    scorer finds no matching theme in the catalog:
    1. Returns an empty dominant_themes list [] (no unrelated Java/backend or distributed-systems theme is injected).
    2. Builds a grounded prompt focusing on ranked requirements and instructing Claude not to invent a dominant theme.
    3. Successfully generates a tailored resume using normal ranked requirements and verified candidate truth.
    4. Intact deterministic fallback behavior.
    """
    analyzer = JobDescriptionAnalyzer()

    jd_ml = """
    Computer Vision / Machine Learning Engineer
    Company: VisionTech AI
    Location: Remote
    We are seeking a Machine Learning Engineer to design state-of-the-art vision models.
    Requirements:
    - 4+ years of Python development with PyTorch, OpenCV, and NumPy.
    - Experience training convolutional neural networks (CNNs) and vision transformers (ViT).
    - Model optimization using TensorRT and ONNX.
    - Deep knowledge of GPU cluster training and CUDA kernels.
    Nice to have:
    - Experience with HuggingFace, PyTorch Lightning, and MLflow.
    - Background in linear algebra, optimization, and statistical modeling.
    Responsibilities:
    - Design, train, and benchmark deep neural network architectures for visual perception.
    - Optimize inference latency and memory footprint using quantization and pruning.
    - Build automated data curation and active learning annotation pipelines.
    - Collaborate with product engineers to deploy optimized models to edge devices.
    """

    # 1. Verify JobAnalysis derives an empty dominant_themes list
    analysis = analyzer.analyze(jd_ml)
    assert analysis.dominant_themes == []
    assert "Java/Spring backend development" not in analysis.dominant_themes
    assert "distributed systems/payment processing" not in analysis.dominant_themes
    assert "GCP/data platform engineering" not in analysis.dominant_themes

    # 2. Verify Grounded Prompt focuses on ranked requirements without inventing themes
    prompt = build_grounded_resume_prompt(candidate_profile, analysis, "backend_java")
    assert "Java/Spring backend development" not in prompt
    assert "distributed systems/payment processing" not in prompt
    assert "### TARGET JOB DOMINANT THEMES:" not in prompt
    assert "### TARGET JOB REQUIREMENTS FOCUS:" in prompt
    assert "Do NOT invent, fabricate, or assume an ungrounded dominant technical theme" in prompt
    assert "Python" in prompt

    # 3. Verify Resume Generation with MockLLMProvider works using normal ranked requirements
    draft_ml = valid_llm_draft.model_copy(deep=True)
    draft_ml.dominant_themes = []
    draft_ml.tailoring_rationale = "Tailored strictly against ranked JD requirements with zero fabricated dominant themes."

    provider = MockLLMProvider(draft_to_return=draft_ml)
    writer = LLMResumeWriter(provider=provider)
    strat = service.get_strategy("backend_java")

    tailored = writer.generate_tailored_resume(candidate_profile, strat, analysis=analysis)
    assert tailored is not None
    assert tailored.metadata.get("dominant_themes") == []
    assert "Java/Spring backend development" not in tailored.metadata.get("dominant_themes", [])
    assert "distributed systems/payment processing" not in tailored.metadata.get("dominant_themes", [])

    # 4. Verify ResumeService end-to-end integration and deterministic fallback generate valid 1-page resume
    res = service.generate_tailored_resume("backend_java", job_description_text=jd_ml)
    assert res.validation.is_valid is True
    assert res.validation.pdf_generated is True
    assert res.validation.page_count == 1
    assert len(res.validation.truth_violations) == 0



