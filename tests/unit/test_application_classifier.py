"""Unit tests for Phase 6 Application Question Classifier."""

import pytest
from job_copilot.application.classifier import QuestionClassifier
from job_copilot.application.models import (
    ApplicationQuestion,
    QuestionClassification,
    QuestionType,
)


@pytest.fixture
def classifier():
    return QuestionClassifier()


def test_evidenced_technical_questions_classified_as_answerable(classifier):
    q_java = ApplicationQuestion(id="q1", question_text="Describe your experience with Java and Spring Boot.")
    assert classifier.classify(q_java) == QuestionClassification.ANSWERABLE_FROM_EVIDENCE

    q_gcp = ApplicationQuestion(id="q2", question_text="What is your background with GCP and BigQuery?")
    assert classifier.classify(q_gcp) == QuestionClassification.ANSWERABLE_FROM_EVIDENCE

    q_payments = ApplicationQuestion(id="q3", question_text="Have you worked on payment platforms or transaction processing?")
    assert classifier.classify(q_payments) == QuestionClassification.ANSWERABLE_FROM_EVIDENCE

    q_why = ApplicationQuestion(id="q4", question_text="Why are you interested in this position?")
    assert classifier.classify(q_why) == QuestionClassification.ANSWERABLE_FROM_EVIDENCE


def test_sensitive_user_input_questions_classified_properly(classifier):
    q_sal = ApplicationQuestion(id="q_sal", question_text="What are your salary expectations?", question_type=QuestionType.SALARY)
    assert classifier.classify(q_sal) == QuestionClassification.ANSWER_REQUIRES_USER_INPUT

    q_visa = ApplicationQuestion(id="q_visa", question_text="Will you now or in the future require sponsorship?", question_type=QuestionType.SPONSORSHIP)
    assert classifier.classify(q_visa) == QuestionClassification.ANSWER_REQUIRES_USER_INPUT

    q_auth = ApplicationQuestion(id="q_auth", question_text="Are you legally authorized to work in the United States?", question_type=QuestionType.WORK_AUTHORIZATION)
    assert classifier.classify(q_auth) == QuestionClassification.ANSWER_REQUIRES_USER_INPUT

    q_start = ApplicationQuestion(id="q_start", question_text="What is your notice period / earliest start date?", question_type=QuestionType.DATE)
    assert classifier.classify(q_start) == QuestionClassification.ANSWER_REQUIRES_USER_INPUT


def test_unsupported_and_depth_traps(classifier):
    # Production kubernetes depth question without multi-year production evidence -> user input required
    q_k8s = ApplicationQuestion(id="q_k8s", question_text="Do you have production Kubernetes cluster administration experience?", question_type=QuestionType.YES_NO)
    assert classifier.classify(q_k8s) == QuestionClassification.ANSWER_REQUIRES_USER_INPUT

    # Excessive unevidenced AWS claim -> DO_NOT_ANSWER
    q_aws = ApplicationQuestion(id="q_aws", question_text="Do you have 5+ years of AWS production experience?", question_type=QuestionType.YES_NO)
    assert classifier.classify(q_aws) == QuestionClassification.DO_NOT_ANSWER

    # Completely unevidenced embedded C hardware protocol -> DO_NOT_ANSWER
    q_embedded = ApplicationQuestion(id="q_emb", question_text="Describe your experience with embedded firmware RTOS and ARM microcontrollers.")
    assert classifier.classify(q_embedded) == QuestionClassification.DO_NOT_ANSWER
