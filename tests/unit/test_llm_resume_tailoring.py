"""Focused unit and integration tests for LLM Resume Tailoring, Provider Abstraction,
Evidence Grounding, and Deterministic Fallback."""

import pytest

from job_copilot.resume.llm.models import (
    LLMBulletItem,
    LLMProjectItem,
    LLMResumeDraft,
    LLMSkillGroupItem,
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

