"""Integration tests for all 6 representative Job Intelligence scenarios (A through F)."""

import pytest
from job_copilot.matching.models import (
    JobRecommendation,
    MatchClassification,
)
from job_copilot.services.job_intelligence_service import JobIntelligenceService


@pytest.fixture
def service():
    return JobIntelligenceService()


# -----------------------------------------------------------------------------
# Fixture A: Strong Backend Java Match
# -----------------------------------------------------------------------------
def test_scenario_a_strong_backend_match(service):
    jd_text = """
    Job Title: Software Engineer - Java Backend
    Company: Stripe
    Location: Remote
    Requirements:
    - 2+ years experience in Java and Spring Boot.
    - Experience building REST APIs and microservices.
    - Experience with GCP cloud services, PostgreSQL, Redis, and Python.
    - Payments or fintech domain knowledge is a plus.
    """
    assessment = service.evaluate_job(jd_text)

    assert assessment.recommended_strategy == "backend_java"
    assert assessment.score_breakdown.overall_score >= 75.0
    assert assessment.recommendation in (JobRecommendation.STRONG_APPLY, JobRecommendation.APPLY)
    assert any("Java" in s for s in assessment.strengths)
    assert any("Spring Boot" in s for s in assessment.strengths)


# -----------------------------------------------------------------------------
# Fixture B: Cloud / DevOps
# -----------------------------------------------------------------------------
def test_scenario_b_cloud_devops(service):
    jd_text = """
    Job Title: Cloud & DevOps Engineer
    Company: Netflix
    Location: Remote
    Requirements:
    - GCP infrastructure management and Terraform IaC.
    - Jenkins CI/CD pipeline automation and Python scripting.
    - GCP Cloud Monitoring and observability alerting.
    - Hands-on exposure to GKE and Helm Charts.
    """
    assessment = service.evaluate_job(jd_text)

    assert assessment.recommended_strategy in ("cloud_devops", "sre_devops")
    assert assessment.score_breakdown.overall_score >= 75.0
    assert assessment.recommendation in (JobRecommendation.STRONG_APPLY, JobRecommendation.APPLY)

    # Check GKE and Helm are classified as exposure
    gke_match = next((m for m in assessment.match_results if "GKE" in m.requirement.normalized_name), None)
    assert gke_match is not None
    assert gke_match.classification == MatchClassification.MATCH_EXPOSURE_ONLY


# -----------------------------------------------------------------------------
# Fixture C: Data Engineering
# -----------------------------------------------------------------------------
def test_scenario_c_data_engineering(service):
    jd_text = """
    Job Title: Data Engineer - Streaming Platform
    Company: Databricks
    Location: Hybrid
    Requirements:
    - Experience in Python and SQL.
    - Apache Beam and GCP Dataflow streaming pipeline development.
    - GCP BigQuery data warehousing and Cloud Composer (Airflow) DAG orchestration.
    - Parquet data transformations.
    """
    assessment = service.evaluate_job(jd_text)

    assert assessment.recommended_strategy == "data_engineering"
    assert assessment.score_breakdown.overall_score >= 85.0
    assert assessment.recommendation in (JobRecommendation.STRONG_APPLY, JobRecommendation.APPLY)
    assert any("Apache Beam" in s for s in assessment.strengths)
    assert any("BigQuery" in s for s in assessment.strengths)


# -----------------------------------------------------------------------------
# Fixture D: Full Stack Payments
# -----------------------------------------------------------------------------
def test_scenario_d_full_stack_payments(service):
    jd_text = """
    Job Title: Full Stack Software Engineer
    Company: Adyen
    Location: Remote
    Requirements:
    - Experience with React, Next.js, and TypeScript for web UI.
    - Java (Spring Boot) and Python for backend payment services.
    - Building payments platform and orchestration services.
    - PostgreSQL and Supabase.
    """
    assessment = service.evaluate_job(jd_text)

    assert assessment.recommended_strategy == "full_stack"
    assert assessment.score_breakdown.overall_score >= 75.0
    assert assessment.recommendation in (JobRecommendation.STRONG_APPLY, JobRecommendation.APPLY)
    # Verify project evidence (React/TypeScript) and professional evidence (PaymentsAI/Java)
    has_project_match = any("PRJ-GG" in p or "React" in p or "TypeScript" in p for p in assessment.partial_matches)
    has_pro_match = any("EXP-HSBC" in s or "Java" in s or "Python" in s for s in assessment.strengths)
    assert has_project_match and has_pro_match


# -----------------------------------------------------------------------------
# Fixture E: Kubernetes-Heavy 5+ Yrs & AWS EKS (Depth Mismatch)
# -----------------------------------------------------------------------------
def test_scenario_e_kubernetes_heavy_depth_mismatch(service):
    jd_text = """
    Job Title: Senior Kubernetes Platform Engineer
    Company: Uber
    Location: Onsite - San Francisco
    Requirements:
    - 5+ years of production Kubernetes cluster administration.
    - Deep AWS EKS infrastructure management.
    - Must have US citizenship or security clearance. No visa sponsorship.
    """
    assessment = service.evaluate_job(jd_text)

    # Must NOT be a strong apply due to 5+ yrs requirement, AWS EKS gap, and sponsorship
    assert assessment.recommendation in (JobRecommendation.REVIEW, JobRecommendation.LOW_PRIORITY, JobRecommendation.SKIP)
    assert len(assessment.risks) > 0
    # Must explicitly surface depth/seniority gap and AWS unconfirmed gap
    assert any("Seniority" in r or "Experience Gap" in r or "Visa" in r or "Citizenship" in r for r in assessment.risks)


# -----------------------------------------------------------------------------
# Fixture F: Poor Match (Embedded C / Firmware)
# -----------------------------------------------------------------------------
def test_scenario_f_poor_match(service):
    jd_text = """
    Job Title: Embedded Firmware Engineer
    Company: Qualcomm
    Location: San Diego, CA
    Requirements:
    - 6+ years C/C++ embedded firmware development for ARM microcontrollers.
    - RTOS kernel development, I2C, SPI, UART hardware protocols.
    - Oscilloscope and logic analyzer debugging.
    - US work authorization required.
    """
    assessment = service.evaluate_job(jd_text)

    assert assessment.score_breakdown.overall_score < 60.0
    assert assessment.recommendation in (JobRecommendation.LOW_PRIORITY, JobRecommendation.SKIP)
    assert len(assessment.gaps) > 0
