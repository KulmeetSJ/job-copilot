"""Truth-grounding and seniority matching regression tests."""

import hashlib
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from job_copilot.application.classifier import QuestionClassifier
from job_copilot.application.cover_letter import CoverLetterEngine
from job_copilot.application.models import ApplicationQuestion, QuestionType
from job_copilot.application.qa_engine import ApplicationQAEngine
from job_copilot.copilot.explanations import ExplanationEngine
from job_copilot.domain.enums import ApplicationStatus, ResumeStrategy
from job_copilot.matching.analyzer import JobAnalyzer
from job_copilot.matching.matcher import CandidateMatcher
from job_copilot.matching.models import AnalyzedJob, JobAssessment, TechnicalRequirement, JobSeniority, RequirementImportance
from job_copilot.matching.recommender import JobRecommender
from job_copilot.matching.scorer import FitScorer
from job_copilot.models.application import Application
from job_copilot.models.browser_task import BrowserTaskModel, BrowserTaskStatus
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.services.resume_service import ResumeService
from job_copilot.services.dashboard_service import DashboardService, resolve_canonical_application_state
from job_copilot.services.job_intelligence_service import JobIntelligenceService


def test_jd_8_years_does_not_claim_candidate_has_8_years():
    """
    Invariant: When a JD requires 8+ years, the system must NEVER claim
    the candidate has 8+ years or that seniority matches 8+ years.
    """
    raw_jd = """
    Company: TechCorp
    Title: Senior Backend Java Engineer
    Requirements:
    - 8+ years of professional backend software engineering experience with Java and Spring Boot.
    - Deep expertise in GCP, BigQuery, Pub/Sub, Dataflow.
    - Distributed systems architecture.
    """
    intelligence = JobIntelligenceService()
    assessment = intelligence.evaluate_job(raw_jd, company_override="TechCorp", title_override="Senior Backend Java Engineer")

    explanation = ExplanationEngine.generate_explanation(assessment)

    # 1. Ensure fabricated "8+ years" string is NEVER in why_apply
    for reason in explanation.why_apply:
        assert "8+ years" not in reason
        assert "8 years" not in reason
        assert "Seniority level matches candidate's 8+ years" not in reason

    # 2. Ensure JD requirement is identified and candidate experience gap is surfaced in why_not_apply or risks
    all_reasons = explanation.why_apply + explanation.why_not_apply + assessment.risks
    has_gap_explanation = any("JD requests" in r or "Seniority" in r or "Experience Gap" in r for r in all_reasons)
    assert has_gap_explanation, "Expected seniority/experience gap to be surfaced in explanations/risks"


def test_missing_candidate_evidence_treated_as_unconfirmed():
    """
    Invariant: When candidate has no evidence for a JD requirement (e.g. C++, Rust),
    the system marks it as NO_EVIDENCE, not confirmed or fabricated.
    """
    raw_jd = """
    Company: EmbeddedSystems Inc
    Title: C++ Systems Engineer
    Requirements:
    - 5+ years C++ / Rust firmware development.
    - Hardware-in-the-loop testing.
    """
    intelligence = JobIntelligenceService()
    assessment = intelligence.evaluate_job(raw_jd)

    cxx_matches = [m for m in assessment.match_results if "c++" in m.requirement.name.lower() or "rust" in m.requirement.name.lower()]
    for m in cxx_matches:
        assert m.classification.value in ["NO_EVIDENCE", "MATCH_POSITIONING_ONLY"]
        assert len(m.candidate_evidence_ids) == 0


from job_copilot.models.job import Job


def test_cover_letter_does_not_invent_excessive_years():
    """
    Invariant: CoverLetterEngine must not claim unsupported years of experience.
    """
    intelligence = JobIntelligenceService()
    profile = intelligence.load_master_profile()
    raw_jd = "Company: TechCorp\nTitle: Senior Backend Engineer\nRequirements: 8+ years Java experience"
    assessment = intelligence.evaluate_job(raw_jd)
    engine = CoverLetterEngine()
    cl = engine.generate_cover_letter(assessment, profile)
    assert "8+ years" not in cl.letter_text
    assert "8 years" not in cl.letter_text
    assert "5+ years" not in cl.letter_text
    assert "10+ years" not in cl.letter_text


def test_qa_engine_does_not_claim_unsupported_experience():
    """
    Invariant: Q&A engine routes unsupported experience / sensitive questions to user input.
    """
    intelligence = JobIntelligenceService()
    profile = intelligence.load_master_profile()
    assessment = intelligence.evaluate_job("Company: TechCorp\nTitle: Senior Engineer\nRequirements: Java")
    engine = ApplicationQAEngine()
    unsupported_q = ApplicationQuestion(
        id="q-exp-001",
        question_text="Do you have 8+ years of Java experience?",
        question_type=QuestionType.EXPERIENCE_DURATION,
    )
    ans = engine.answer_question(unsupported_q, profile=profile, assessment=assessment)
    assert ans.requires_user_input is True or "8+" not in (ans.answer or "")


def test_dashboard_explanation_grounding(db_session: Session):
    """
    Invariant: Dashboard job detail explanations separate facts, inferences, and recommendations.
    """
    service = DashboardService(db=db_session)
    job = Job(
        job_id="job-truth-001",
        title="Software Engineer II",
        company="AcmeFintech",
        description="Java, Spring Boot, GCP, Pub/Sub microservices. Requires 2-3 years experience.",
        source="user_submitted_url",
    )
    db_session.add(job)
    db_session.commit()

    detail = service.get_job_detail("job-truth-001")
    assert detail is not None
    assert detail.explanation is not None
    assert len(detail.explanation.facts) > 0
    for fact in detail.explanation.facts:
        assert "8+ years" not in fact
        assert "Target Company" not in fact


def test_candidate_truth_yaml_hashes_immutable():
    """
    Invariant: Candidate truth files in data/candidate must never be modified.
    """
    expected_hashes = {
        "master_profile.yaml": "b77c799a8494ead7e3b7b8ee6b5fcbb125f7f512313c8dad745b1127800af433",
        "evidence.yaml": "c0d249794a2976972693f6b2d06e74db130e7c5d5c61202658cce7ebf2756303",
        "preferences.yaml": "66b5ff3f6fa8117de378bc7cadd026e9d2230dcbd40e6f0b6587c2edc281380a",
        "review_required.yaml": "422625a4b4cbfb549058de9db4d56c2e4e6de4443d4e53fad4b66e80eb0304b1",
    }
    for filename, expected_hash in expected_hashes.items():
        filepath = Path("data/candidate") / filename
        assert filepath.exists(), f"{filename} missing"
        actual_hash = hashlib.sha256(filepath.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"Candidate truth file {filename} was mutated!"


def test_match_score_calculation_with_seniority_gap():
    """
    Verify complete score calculation breakdown for an 8+ years JD.
    Proves that role/seniority (15%) and professional experience (15%) are penalized
    and that JD facts are not converted into candidate facts.
    """
    raw_jd = """
    Company: GlobalBank
    Title: Senior Java Architect
    Requirements:
    - 8+ years of Java backend experience.
    - Deep knowledge of Spring Boot and GCP.
    """
    intelligence = JobIntelligenceService()
    assessment = intelligence.evaluate_job(raw_jd)
    sb = assessment.score_breakdown

    assert assessment.job.years_experience_required == 8.0
    # Role & Seniority score should be penalized for 8+ years gap
    assert sb.role_score <= 80.0
    # Experience score should reflect penalty for 8+ yrs requirement vs ~2 yrs candidate
    assert sb.experience_score <= 60.0
    # Candidate evidence should only be confirmed where actual evidence exists (Java, Spring Boot, GCP)
    for mr in assessment.match_results:
        if mr.candidate_evidence_ids:
            for eid in mr.candidate_evidence_ids:
                assert "EXP-" in eid or "SKL-" in eid or "PRJ-" in eid


def test_duplicate_risk_flags_prevented(db_session: Session):
    """
    Verify that identical risk flags (e.g. sponsorship unknown) are not emitted twice in queue items.
    """
    service = DashboardService(db=db_session)
    raw_jd = """
    Company: TestBank
    Title: Software Engineer
    Requirements:
    - Java and Spring Boot.
    """
    intelligence = JobIntelligenceService()
    assessment = intelligence.evaluate_job(raw_jd)
    explanation = ExplanationEngine.generate_explanation(assessment)

    # Check why_not_apply does not contain duplicated strings
    seen = set()
    for item in explanation.why_not_apply:
        assert item not in seen, f"Duplicate reason in why_not_apply: {item}"
        seen.add(item)


def test_pdf_content_disposition_canonical_filename(db_session: Session):
    """
    Verify get_application_resume_pdf returns a clean, canonical filename:
    Kulmeet_Singh_{Company}_{Role}.pdf
    """
    service = DashboardService(db=db_session)
    job = Job(
        job_id="job-mc-001",
        title="Software Engineer II",
        company="Mastercard",
        description="Java backend",
        source="user_submitted_url",
    )
    db_session.add(job)
    db_session.commit()

    app = Application(
        application_id="app-mc-001",
        job_id=job.id,
        job_id_str="job-mc-001",
        company="Mastercard",
        role="Software Engineer II",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    db_session.add(app)
    db_session.commit()

    data, content_type, filename = service.get_application_resume_pdf("app-mc-001")
    assert filename == "Kulmeet_Singh_Mastercard_Software_Engineer_II.pdf"
    assert "We" not in filename
    assert "Target_Company" not in filename


def test_cross_dashboard_lifecycle_consistency(db_session: Session):
    """
    Verify resolve_canonical_application_state produces consistent state across all dashboard views.
    Historical unverified Mastercard record must remain SUBMISSION_UNVERIFIED and not inflate SUBMITTED.
    """
    app = Application(
        application_id="app-usr-2a43a63d",
        job_id=1,
        job_id_str="mastercard-001",
        company="Mastercard",
        role="Software Engineer",
        status=ApplicationStatus.APPLIED,
    )
    task = BrowserTaskModel(
        task_id="task-001",
        application_id="app-usr-2a43a63d",
        job_id="mastercard-001",
        status=BrowserTaskStatus.SUBMISSION_UNVERIFIED,
    )
    state = resolve_canonical_application_state(app=app, browser_task=task)
    assert state == "SUBMISSION_UNVERIFIED"
    assert state != "SUBMITTED"


def test_locked_phase_4_scoring_contract():
    """
    Regression Test: Assert exact locked Phase 4 scoring weights, evidence multipliers, and thresholds.
    """
    from job_copilot.matching.config import default_matching_config
    cfg = default_matching_config

    # 1. Weights
    w = cfg.dimension_weights
    assert w.technical == 0.30, f"Expected 0.30 (30%), got {w.technical}"
    assert w.responsibilities == 0.25, f"Expected 0.25 (25%), got {w.responsibilities}"
    assert w.role_seniority == 0.15, f"Expected 0.15 (15%), got {w.role_seniority}"
    assert w.professional_evidence == 0.15, f"Expected 0.15 (15%), got {w.professional_evidence}"
    assert w.domain == 0.05, f"Expected 0.05 (5%), got {w.domain}"
    assert w.preferences == 0.05, f"Expected 0.05 (5%), got {w.preferences}"
    assert w.credentials == 0.05, f"Expected 0.05 (5%), got {w.credentials}"
    assert round(w.technical + w.responsibilities + w.role_seniority + w.professional_evidence + w.domain + w.preferences + w.credentials, 4) == 1.00

    # 2. Multipliers
    em = cfg.evidence_weights
    assert em.confirmed == 1.00
    assert em.project_only == 0.65
    assert em.exposure_only == 0.50
    assert em.partial == 0.40
    assert em.positioning_only == 0.20
    assert em.no_evidence == 0.00
    assert em.conflict == -0.50

    # 3. Thresholds
    th = cfg.thresholds
    assert th.strong_apply == 88.0
    assert th.apply == 75.0
    assert th.review == 60.0
    assert th.low_priority == 45.0


def test_dashboard_service_dimension_weights_match_phase_4_contract(db_session: Session):
    """
    Regression Test: Dashboard service dimension weights must be exactly 30/25/15/15/5/5/5.
    """
    service = DashboardService(db=db_session)
    job = Job(
        job_id="job-weight-check-001",
        title="Software Engineer",
        company="TestCorp",
        description="Java, Spring Boot, GCP backend",
        source="user_submitted_url",
    )
    db_session.add(job)
    db_session.commit()

    detail = service.get_job_detail("job-weight-check-001")
    assert detail is not None
    assert len(detail.dimension_scores) == 7

    weights_by_dim = {d.dimension_name: d.weight for d in detail.dimension_scores}
    assert weights_by_dim["Technical Skills"] == 0.30
    assert weights_by_dim["Core Responsibilities"] == 0.25
    assert weights_by_dim["Role & Seniority"] == 0.15
    assert weights_by_dim["Professional Evidence"] == 0.15
    assert weights_by_dim["Domain Expertise"] == 0.05
    assert weights_by_dim["Preferences"] == 0.05
    assert weights_by_dim["Credentials & Education"] == 0.05


def test_candidate_experience_derived_from_canonical_profile():
    """
    Regression Test: Candidate experience duration is derived dynamically from employment history.
    """
    intelligence = JobIntelligenceService()
    profile = intelligence.load_master_profile()
    years = profile.verified_experience_years
    assert years is not None
    assert isinstance(years, float)
    assert years > 0.0

    # Profile with no employment history returns None (never guesses a magic number)
    from job_copilot.schemas.candidate import CandidateProfile, PersonalInformation
    empty_profile = CandidateProfile(
        personal_info=PersonalInformation(
            full_name="Test Candidate",
            email="test@example.com",
            location="City, Country",
        ),
        employment=[],
    )
    assert empty_profile.verified_experience_years is None


def test_five_canonical_resume_strategies_unchanged():
    """
    Regression Test: Exactly five canonical resume strategies are supported and unchanged.
    """
    canonical_strategies = {
        ResumeStrategy.BACKEND_JAVA,
        ResumeStrategy.CLOUD_DEVOPS,
        ResumeStrategy.DATA_ENGINEERING,
        ResumeStrategy.FULL_STACK,
        ResumeStrategy.SRE_DEVOPS,
    }
    assert set(ResumeStrategy) == canonical_strategies
