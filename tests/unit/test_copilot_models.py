"""Unit tests for Phase 9 Copilot data models and claim typing."""

from datetime import datetime, timezone
from job_copilot.copilot.models import (
    ClaimType,
    CopilotAction,
    CopilotDashboard,
    CopilotExplanation,
    CopilotJob,
    CopilotRecommendation,
    EvidenceReference,
    HistoricalInsight,
    PriorityBand,
    QueueStatus,
    utc_now,
)
from job_copilot.tracking.models import ApplicationLifecycleStatus


def test_copilot_models_instantiation():
    now = utc_now()
    ev_ref = EvidenceReference(
        claim_id="EXP-HSBC-PAYMENTS-AI-001",
        claim_type=ClaimType.PROFESSIONAL_EXPERIENCE,
        description="Lead Java developer on GCP Payments AI engine",
        source_ref="Work Experience: HSBC",
    )
    assert ev_ref.claim_type == ClaimType.PROFESSIONAL_EXPERIENCE

    explanation = CopilotExplanation(
        why_apply=["Strong Java and Spring alignment", "Relevant payment processing experience"],
        why_not_apply=["Kubernetes in production not confirmed"],
        uncertainties=["Visa sponsorship UNKNOWN"],
        historical_context="Backend Java historically 33% interview conversion",
        evidence_references=[ev_ref],
    )
    assert len(explanation.why_apply) == 2
    assert len(explanation.evidence_references) == 1

    recommendation = CopilotRecommendation(
        job_id="job-123",
        action=CopilotAction.REVIEW,
        priority_band=PriorityBand.HIGH,
        priority_score=82.5,
        reasons=explanation.why_apply,
        strengths=explanation.why_apply,
        risks=explanation.why_not_apply,
        missing_information=explanation.uncertainties,
        evidence_references=[ev_ref],
    )
    assert recommendation.action == CopilotAction.REVIEW
    assert recommendation.priority_band == PriorityBand.HIGH

    job = CopilotJob(
        job_id="job-123",
        title="Senior Backend Engineer",
        company="Stripe",
        source="greenhouse",
        match_score=88.0,
        recommendation_tier="APPLY",
        selected_strategy="backend_java",
        queue_status=QueueStatus.REVIEW,
        priority_score=82.5,
        priority_band=PriorityBand.HIGH,
        explanation=explanation,
        recommendation=recommendation,
    )
    assert job.company == "Stripe"
    assert job.queue_status == QueueStatus.REVIEW


def test_historical_insight_model():
    insight = HistoricalInsight(
        topic="Strategy Performance: Backend Java",
        fact_statements=["FACT: 24 applications submitted", "FACT: 7 interviews reached"],
        inference_statements=["INFERENCE: Strong interview conversion (29.2%)"],
        recommendation_statements=["RECOMMENDATION: Prioritize Backend Java roles"],
        sample_size=24,
        sample_threshold_met=True,
        is_statistically_reliable=True,
    )
    assert insight.sample_size == 24
    assert insight.sample_threshold_met is True
    assert insight.is_statistically_reliable is True
    assert "No configuration change made" in insight.action_required
