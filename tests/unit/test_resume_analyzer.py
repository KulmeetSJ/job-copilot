"""Unit tests for Job Description Analyzer."""

import pytest
from job_copilot.resume.analyzer import JobDescriptionAnalyzer


@pytest.fixture
def analyzer():
    return JobDescriptionAnalyzer()


def test_analyzer_extracts_metadata(analyzer):
    jd = """
    Job Title: Senior Cloud Engineer
    Company: Acme Corp
    Location: Hybrid

    Requirements:
    - 4+ years experience with GCP, Terraform, and Docker.
    - Experience in Python and Java.

    Nice to have:
    - Experience with Apache Airflow and BigQuery.
    """
    analysis = analyzer.analyze(jd)
    assert analysis.job_title == "Senior Cloud Engineer"
    assert analysis.company == "Acme Corp"
    assert analysis.location == "Hybrid"
    assert analysis.seniority_level == "Senior"
    assert analysis.years_experience_requirement == 4.0

    req_names = {s.normalized_name for s in analysis.required_skills}
    assert "GCP" in req_names
    assert "Terraform" in req_names
    assert "Docker" in req_names
    assert "Python" in req_names
    assert "Java" in req_names

    pref_names = {s.normalized_name for s in analysis.preferred_skills}
    assert "Apache Airflow" in pref_names
    assert "GCP BigQuery" in pref_names


def test_analyzer_synonym_normalization(analyzer):
    jd = """
    We need an engineer experienced with Google Cloud Platform, SpringBoot, k8s, and react.js.
    """
    analysis = analyzer.analyze(jd)
    all_skills = {s.normalized_name for s in analysis.required_skills + analysis.preferred_skills}
    assert "GCP" in all_skills
    assert "Spring Boot" in all_skills
    assert "Kubernetes" in all_skills
    assert "React" in all_skills
