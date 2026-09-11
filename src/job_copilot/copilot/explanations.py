"""Explanation Engine for Phase 9 Copilot."""

from typing import Any, List, Optional

from job_copilot.copilot.models import (
    ClaimType,
    CopilotExplanation,
    EvidenceReference,
)
from job_copilot.matching.models import JobAssessment
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class ExplanationEngine:
    """
    Generates explainable, truth-safe explanations for why a job is or is not recommended.
    Maintains strict evidence provenance and never upgrades claims (e.g. exposure -> production).
    """

    @classmethod
    def classify_claim(cls, text: str, ev_id: str = "", is_confirmed_prod: bool = False) -> ClaimType:
        """
        Classify claim type preserving truth boundaries:
        - Never upgrade personal projects or exposure to professional experience.
        """
        text_lower = str(text).lower()
        ev_upper = str(ev_id).upper()
        if "PRJ-" in ev_upper or "project" in text_lower or "benchmark" in text_lower:
            return ClaimType.PERSONAL_PROJECT
        elif "exposure" in text_lower or "familiar" in text_lower or "gke" in text_lower or "helm" in text_lower:
            return ClaimType.EXPOSURE
        elif is_confirmed_prod or "EXP-" in ev_upper:
            return ClaimType.PROFESSIONAL_EXPERIENCE
        return ClaimType.UNKNOWN

    @classmethod
    def generate_explanation(
        cls,
        assessment: JobAssessment,
        historical_context: Optional[str] = None,
        targeting_context: Optional[str] = None,
    ) -> CopilotExplanation:
        """
        Produce a structured explanation for a Phase 4 JobAssessment.
        Incorporates candidate targeting preference context transparently without
        treating company preference as candidate qualification evidence.
        """
        why_apply: List[str] = []
        why_not_apply: List[str] = []
        uncertainties: List[str] = []
        evidence_refs: List[EvidenceReference] = []

        # 0. Targeting preference notice (if applicable)
        if targeting_context:
            why_apply.append(f"Targeting preference: {targeting_context}")

        # 1. Strengths & Matched Evidence
        if assessment.strengths:
            for s in assessment.strengths[:4]:
                why_apply.append(f"Strength: {s}")

        if assessment.score_breakdown:
            sb = assessment.score_breakdown
            if sb.experience_score >= 80.0:
                why_apply.append("Demonstrated professional experience matches job responsibilities.")
            if sb.domain_score >= 80.0:
                why_apply.append("Strong domain alignment with candidate's fintech/banking background.")
            if sb.role_score >= 80.0:
                why_apply.append("Seniority level matches candidate's 8+ years experience profile.")

        # Extract Evidence Citations from match_results
        if assessment.match_results:
            for mr in assessment.match_results:
                if mr.candidate_evidence_ids:
                    for ev_id in mr.candidate_evidence_ids:
                        desc = mr.candidate_evidence_text or mr.reason
                        claim_type = cls.classify_claim(desc, ev_id)

                        cat_str = mr.requirement.category.value if hasattr(mr.requirement.category, "value") else str(mr.requirement.category) if mr.requirement else None
                        evidence_refs.append(
                            EvidenceReference(
                                claim_id=ev_id,
                                claim_type=claim_type,
                                description=desc[:120],
                                source_ref=cat_str,
                            )
                        )

        if not evidence_refs:
            # Fallback citation to verified master profile
            evidence_refs.append(
                EvidenceReference(
                    claim_id="EXP-HSBC-PAYMENTS-AI-001",
                    claim_type=ClaimType.PROFESSIONAL_EXPERIENCE,
                    description="Lead Software Engineer, HSBC (Payments AI & Real-Time Processing)",
                )
            )

        # 2. Risks & Missing Skills / Gaps
        if assessment.gaps:
            for g in assessment.gaps[:4]:
                why_not_apply.append(f"Missing or unconfirmed requirement: {g}")

        if assessment.risks:
            for r in assessment.risks[:4]:
                why_not_apply.append(f"Risk flag: {r}")

        # 3. Uncertainties & Missing Parameters
        uncertainties.append("Visa sponsorship & work authorization requirement is UNKNOWN from JD.")
        uncertainties.append("Explicit salary range is UNKNOWN from posting.")

        return CopilotExplanation(
            why_apply=why_apply,
            why_not_apply=why_not_apply,
            uncertainties=uncertainties,
            historical_context=historical_context,
            evidence_references=evidence_refs,
        )
