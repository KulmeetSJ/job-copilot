"""Integration tests for Phase 6 Application Preparation Service and End-to-End Scenario."""

import hashlib
from pathlib import Path
import pytest

from job_copilot.application.models import (
    ApplicationPackageStatus,
    ApplicationQuestion,
    QuestionClassification,
    QuestionType,
)
from job_copilot.services.application_prep_service import ApplicationPrepService


@pytest.fixture
def prep_service(tmp_path):
    app_dir = tmp_path / "applications"
    jobs_dir = tmp_path / "jobs"
    return ApplicationPrepService(
        applications_data_dir=app_dir,
        jobs_data_dir=jobs_dir,
    )


def test_end_to_end_representative_scenario(prep_service):
    """
    Scenario from Phase 6 Spec Section 30:
    Backend/Payments Job with 7 diverse question types.
    """
    jd_text = """
    Company: Stripe
    Job Title: Senior Software Engineer - Backend
    Location: Remote
    Requirements:
    - 2+ years of Java and Spring Boot backend development.
    - Experience with GCP cloud infrastructure and PostgreSQL.
    - Distributed systems and payments/transaction processing.
    """

    questions = [
        ApplicationQuestion(id="q1", question_text="Why are you interested in this role?"),
        ApplicationQuestion(id="q2", question_text="Describe your Java experience."),
        ApplicationQuestion(id="q3", question_text="Describe your experience with GCP."),
        ApplicationQuestion(id="q4", question_text="Do you have production Kubernetes experience?", question_type=QuestionType.YES_NO),
        ApplicationQuestion(id="q5", question_text="How many years of AWS experience do you have?"),
        ApplicationQuestion(id="q6", question_text="Will you require sponsorship?", question_type=QuestionType.SPONSORSHIP),
        ApplicationQuestion(id="q7", question_text="What are your salary expectations?", question_type=QuestionType.SALARY),
    ]

    package = prep_service.prepare_application(
        job_id_or_text=jd_text,
        custom_questions=questions,
    )

    # 1. Verify Job & Strategy
    assert package.job_title == "Senior Software Engineer - Backend"
    assert package.company == "Stripe"
    assert package.selected_resume_strategy == "backend_java"
    assert Path(package.resume_pdf_path).exists()

    # 2. Verify Cover Letter
    assert package.cover_letter.company == "Stripe"
    assert package.cover_letter.validation.is_valid is True
    assert 200 <= package.cover_letter.word_count <= 450

    # 3. Verify Question Classifications
    answers_by_id = {a.question_id: a for a in package.answers}

    # q1, q2, q3 -> ANSWERABLE_FROM_EVIDENCE
    assert answers_by_id["q1"].classification == QuestionClassification.ANSWERABLE_FROM_EVIDENCE
    assert answers_by_id["q2"].classification == QuestionClassification.ANSWERABLE_FROM_EVIDENCE
    assert "HSBC" in answers_by_id["q2"].answer
    assert answers_by_id["q3"].classification == QuestionClassification.ANSWERABLE_FROM_EVIDENCE
    assert "GCP" in answers_by_id["q3"].answer

    # q4 -> ANSWER_REQUIRES_USER_INPUT (depth trap)
    assert answers_by_id["q4"].classification == QuestionClassification.ANSWER_REQUIRES_USER_INPUT

    # q5 -> DO_NOT_ANSWER or ANSWER_REQUIRES_USER_INPUT (unsupported AWS)
    assert answers_by_id["q5"].classification in (QuestionClassification.DO_NOT_ANSWER, QuestionClassification.ANSWER_REQUIRES_USER_INPUT)

    # q6, q7 -> ANSWER_REQUIRES_USER_INPUT (sponsorship, salary)
    assert answers_by_id["q6"].classification == QuestionClassification.ANSWER_REQUIRES_USER_INPUT
    assert answers_by_id["q7"].classification == QuestionClassification.ANSWER_REQUIRES_USER_INPUT

    # 4. Verify UserInputRequests
    assert len(package.user_inputs_required) >= 3
    input_q_ids = {u.question_id for u in package.user_inputs_required}
    assert "q6" in input_q_ids
    assert "q7" in input_q_ids

    # 5. Verify Package Status
    assert package.status == ApplicationPackageStatus.USER_INPUT_REQUIRED

    # 6. Verify Disk Persistence
    saved_pkg = prep_service.get_application_package(package.job_id)
    assert saved_pkg is not None
    assert saved_pkg.job_id == package.job_id


def test_candidate_truth_immutability(prep_service):
    master_path = Path("data/candidate/master_profile.yaml")
    orig_hash = hashlib.sha256(master_path.read_bytes()).hexdigest()

    # Prepare application with misleading/external inputs
    prep_service.prepare_application(
        job_id_or_text="""
        Company: FakeCo
        Role: Principal Architect
        Reqs: 20 years AWS, Azure, production Kubernetes.
        """
    )

    after_hash = hashlib.sha256(master_path.read_bytes()).hexdigest()
    assert orig_hash == after_hash
