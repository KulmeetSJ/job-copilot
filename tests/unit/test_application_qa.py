"""Unit tests for Phase 6 QA and Evidence Retrieval Engine."""

from pathlib import Path
import pytest
import yaml

from job_copilot.application.models import (
    ApplicationQuestion,
    QuestionClassification,
    QuestionType,
)
from job_copilot.application.qa_engine import ApplicationQAEngine
from job_copilot.schemas.candidate import CandidateProfile


@pytest.fixture
def profile():
    master_path = Path("data/candidate/master_profile.yaml")
    data = yaml.safe_load(master_path.read_text(encoding="utf-8"))
    return CandidateProfile.model_validate(data)


@pytest.fixture
def qa_engine():
    return ApplicationQAEngine()


def test_java_answer_uses_professional_evidence(qa_engine, profile):
    q = ApplicationQuestion(id="q1", question_text="Describe your experience with Java and backend services.")
    ans = qa_engine.answer_question(q, profile)
    assert ans.classification == QuestionClassification.ANSWERABLE_FROM_EVIDENCE
    assert ans.answer is not None
    assert "HSBC" in ans.answer
    assert any("EXP-HSBC" in p.source_ref for p in ans.provenance)
    assert any(p.source_type == "PROFESSIONAL" for p in ans.provenance)


def test_project_evidence_strictly_labeled_as_project(qa_engine, profile):
    q = ApplicationQuestion(id="q2", question_text="Describe a personal project you are proud of.")
    ans = qa_engine.answer_question(q, profile)
    assert ans.classification == QuestionClassification.ANSWERABLE_FROM_EVIDENCE
    assert ans.answer is not None
    assert "Rate Limiter" in ans.answer or "Redis" in ans.answer
    assert any(p.source_type == "PERSONAL_PROJECT" for p in ans.provenance)
    assert any(p.metric_type == "BENCHMARK" for p in ans.provenance)


def test_gke_helm_strictly_phrased_as_exposure(qa_engine, profile):
    q = ApplicationQuestion(id="q3", question_text="What experience do you have with GKE and Helm Charts?")
    ans = qa_engine.answer_question(q, profile)
    assert ans.classification == QuestionClassification.ANSWERABLE_FROM_EVIDENCE
    assert ans.answer is not None
    assert "hands-on" in ans.answer.lower() or "exposure" in ans.answer.lower()
    assert any(p.source_type == "TRAINING_EXPOSURE" for p in ans.provenance)


def test_salary_and_sponsorship_produce_user_input_request(qa_engine, profile):
    q_sal = ApplicationQuestion(id="q_sal", question_text="What is your target salary?", question_type=QuestionType.SALARY)
    ans_sal = qa_engine.answer_question(q_sal, profile)
    assert ans_sal.classification == QuestionClassification.ANSWER_REQUIRES_USER_INPUT
    assert ans_sal.answer is None
    assert ans_sal.requires_user_input is True

    req = qa_engine.extract_user_input_request(q_sal, ans_sal)
    assert req is not None
    assert req.question_id == "q_sal"
    assert req.expected_type == QuestionType.SALARY
