"""Recommendation, Gap Analysis, and Human-Readable Report Generator."""

from typing import List, Optional, Tuple
from job_copilot.matching.config import MatchingConfig, default_matching_config
from job_copilot.matching.models import (
    AnalyzedJob,
    FitScoreBreakdown,
    JobRecommendation,
    JobSeniority,
    MatchClassification,
    RequirementImportance,
    RequirementMatchResult,
    WorkAuthorizationRequirement,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class JobRecommender:
    """
    Evaluates fit score breakdown and match results to generate:
    - Strengths, partial matches, gaps, risks
    - Final recommendation tier (STRONG_APPLY, APPLY, REVIEW, LOW_PRIORITY, SKIP)
    - Formatted human-readable assessment report
    """

    def __init__(self, config: Optional[MatchingConfig] = None):
        self.config = config or default_matching_config

    def evaluate(
        self,
        job: AnalyzedJob,
        matches: List[RequirementMatchResult],
        scores: FitScoreBreakdown,
        recommended_strategy: str,
    ) -> Tuple[JobRecommendation, List[str], List[str], List[str], List[str], str]:
        """
        Returns (recommendation, strengths, partial_matches, gaps, risks, human_report).
        """
        strengths: List[str] = []
        partial_matches: List[str] = []
        gaps: List[str] = []
        risks: List[str] = []

        # 1. Categorize matches into Strengths, Partials, and Gaps
        for m in matches:
            req_name = m.requirement.normalized_name
            if m.classification == MatchClassification.MATCH_CONFIRMED:
                strengths.append(f"{req_name} — confirmed professional experience ({', '.join(m.candidate_evidence_ids)})")
            elif m.classification == MatchClassification.MATCH_PROJECT_ONLY:
                partial_matches.append(f"{req_name} — personal / portfolio project evidence ({', '.join(m.candidate_evidence_ids)})")
            elif m.classification == MatchClassification.MATCH_EXPOSURE_ONLY:
                partial_matches.append(f"{req_name} — confirmed hands-on / training exposure ({', '.join(m.candidate_evidence_ids)})")
            elif m.classification == MatchClassification.PARTIAL_MATCH:
                partial_matches.append(f"{req_name} — partial match: {m.reason}")
            elif m.classification == MatchClassification.MATCH_POSITIONING_ONLY:
                gaps.append(f"{req_name} — unverified positioning (NEEDS_REVIEW in candidate profile)")
            elif m.classification == MatchClassification.NO_EVIDENCE:
                if m.requirement.is_must_have:
                    gaps.append(f"{req_name} — mandatory requirement with no candidate evidence")
                else:
                    gaps.append(f"{req_name} — preferred skill not present in candidate background")

        # 2. Identify Systemic Risks
        # Seniority / Experience risk
        if job.years_experience_required and job.years_experience_required > 3.0:
            risks.append(
                f"Seniority / Experience Gap: JD requests {job.years_experience_required} yrs experience; "
                f"candidate has ~2 yrs confirmed professional experience."
            )
        elif job.seniority in (JobSeniority.STAFF, JobSeniority.PRINCIPAL, JobSeniority.LEAD):
            risks.append(f"Seniority Gap: Target role is '{job.seniority.value}' level; candidate is Software Engineer.")

        # Work authorization / Visa risk
        if job.work_authorization == WorkAuthorizationRequirement.REQUIRED:
            risks.append("Visa Sponsorship Constraint: JD explicitly states no visa sponsorship or work authorization required.")
        elif job.work_authorization == WorkAuthorizationRequirement.CITIZEN_ONLY:
            risks.append("Citizenship Constraint: JD requires domestic citizenship or security clearance.")
        elif job.work_authorization == WorkAuthorizationRequirement.SPONSORSHIP_UNKNOWN:
            risks.append("Sponsorship Status Unknown: International sponsorship availability not specified in JD.")

        # Unverified critical technology risk
        unverified_must_haves = [
            m.requirement.normalized_name for m in matches
            if m.requirement.is_must_have and m.classification in (MatchClassification.MATCH_POSITIONING_ONLY, MatchClassification.NO_EVIDENCE)
        ]
        if unverified_must_haves:
            risks.append(f"Mandatory Technical Gaps: Missing or unverified evidence for {', '.join(unverified_must_haves[:3])}.")

        # 3. Determine Recommendation Tier
        recommendation = self._calculate_recommendation(scores.overall_score, risks, unverified_must_haves, job)

        # 4. Generate Human Report
        report = self._format_human_report(
            job=job,
            scores=scores,
            recommendation=recommendation,
            recommended_strategy=recommended_strategy,
            strengths=strengths,
            partial_matches=partial_matches,
            gaps=gaps,
            risks=risks,
        )

        return recommendation, strengths, partial_matches, gaps, risks, report

    def _calculate_recommendation(
        self,
        overall_score: float,
        risks: List[str],
        unverified_must_haves: List[str],
        job: AnalyzedJob,
    ) -> JobRecommendation:
        """Apply score thresholds and risk overrides to determine recommendation."""
        th = self.config.thresholds

        # Hard Conflict check
        if job.work_authorization == WorkAuthorizationRequirement.CITIZEN_ONLY:
            return JobRecommendation.SKIP

        # Critical mandatory gaps penalty (e.g. 3+ must-have skills missing)
        if len(unverified_must_haves) >= 3 and overall_score < th.apply:
            return JobRecommendation.LOW_PRIORITY

        # Base scoring tiers
        has_hard_seniority_gap = bool(job.years_experience_required and job.years_experience_required > 4.0)
        has_visa_restriction = job.work_authorization == WorkAuthorizationRequirement.REQUIRED

        if overall_score >= th.strong_apply:
            if has_visa_restriction or has_hard_seniority_gap or len(unverified_must_haves) >= 1:
                return JobRecommendation.APPLY
            return JobRecommendation.STRONG_APPLY
        elif overall_score >= th.apply:
            if has_visa_restriction or has_hard_seniority_gap or len(unverified_must_haves) >= 2:
                return JobRecommendation.REVIEW
            return JobRecommendation.APPLY
        elif overall_score >= th.review:
            return JobRecommendation.REVIEW
        elif overall_score >= th.low_priority:
            return JobRecommendation.LOW_PRIORITY
        else:
            return JobRecommendation.SKIP

    def _format_human_report(
        self,
        job: AnalyzedJob,
        scores: FitScoreBreakdown,
        recommendation: JobRecommendation,
        recommended_strategy: str,
        strengths: List[str],
        partial_matches: List[str],
        gaps: List[str],
        risks: List[str],
    ) -> str:
        """Format an explainable assessment report."""
        lines = [
            "=" * 70,
            f"  JOB ASSESSMENT REPORT",
            "=" * 70,
            f"Role & Company      : {job.title} at {job.company}",
            f"Location / Mode     : {job.location or 'Unspecified'} ({job.remote_policy.value})",
            f"Seniority / Exp Req : {job.seniority.value} ({job.years_experience_required or 'Unspecified'} yrs)",
            "-" * 70,
            f"OVERALL FIT SCORE   : {scores.overall_score} / 100.0",
            f"RECOMMENDATION      : {recommendation.value}",
            f"RECOMMENDED RESUME  : {recommended_strategy}",
            "-" * 70,
            f"Score Breakdown:",
            f"  • Technical Skills       : {scores.technical_score}/100 (30% weight)",
            f"  • Responsibilities       : {scores.responsibility_score}/100 (25% weight)",
            f"  • Role & Seniority       : {scores.role_score}/100 (15% weight)",
            f"  • Professional Evidence  : {scores.experience_score}/100 (15% weight)",
            f"  • Domain Alignment       : {scores.domain_score}/100 (5% weight)",
            f"  • Preferences            : {scores.preference_score}/100 (5% weight)",
            f"  • Credentials            : {scores.credential_score}/100 (5% weight)",
            "-" * 70,
            f"STRONG MATCHES ({len(strengths)}):",
        ]
        for s in strengths[:8]:
            lines.append(f"  ✓ {s}")
        if not strengths:
            lines.append("  (None)")

        lines.append(f"\nPARTIAL & EXPOSURE MATCHES ({len(partial_matches)}):")
        for p in partial_matches[:8]:
            lines.append(f"  ~ {p}")
        if not partial_matches:
            lines.append("  (None)")

        lines.append(f"\nREQUIREMENT GAPS ({len(gaps)}):")
        for g in gaps[:8]:
            lines.append(f"  ✗ {g}")
        if not gaps:
            lines.append("  (None)")

        lines.append(f"\nRISKS & ADVISORIES ({len(risks)}):")
        for r in risks:
            lines.append(f"  ! {r}")
        if not risks:
            lines.append("  (None)")

        lines.append("=" * 70)
        return "\n".join(lines)
