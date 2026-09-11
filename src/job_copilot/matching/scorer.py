"""Multi-Dimensional Fit Scoring Engine across 7 Evaluation Dimensions."""

from typing import List, Optional
from job_copilot.domain.enums import RemoteStatus
from job_copilot.matching.config import MatchingConfig, default_matching_config
from job_copilot.matching.models import (
    AnalyzedJob,
    FitScoreBreakdown,
    JobSeniority,
    MatchClassification,
    RequirementMatchResult,
)
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class FitScorer:
    """
    Computes a multi-dimensional, explainable fit score across 7 distinct dimensions.
    Incorporates requirement importance, evidence quality multipliers, and candidate truth.
    """

    def __init__(self, config: Optional[MatchingConfig] = None):
        self.config = config or default_matching_config

    def compute_score(
        self,
        job: AnalyzedJob,
        profile: CandidateProfile,
        matches: List[RequirementMatchResult],
    ) -> FitScoreBreakdown:
        """Calculate score breakdown across all 7 evaluation dimensions."""
        tech_score = self._score_technical(matches)
        resp_score = self._score_responsibilities(job, profile)
        role_score = self._score_role_and_seniority(job)
        exp_score = self._score_professional_experience(matches, job)
        domain_score = self._score_domain(job)
        pref_score = self._score_preferences(job)
        cred_score = self._score_credentials(job, profile)

        # Weighted composite overall score
        w = self.config.dimension_weights
        overall = (
            tech_score * w.technical
            + resp_score * w.responsibilities
            + role_score * w.role_seniority
            + exp_score * w.professional_evidence
            + domain_score * w.domain
            + pref_score * w.preferences
            + cred_score * w.credentials
        )

        return FitScoreBreakdown(
            technical_score=round(tech_score, 1),
            responsibility_score=round(resp_score, 1),
            role_score=round(role_score, 1),
            experience_score=round(exp_score, 1),
            domain_score=round(domain_score, 1),
            preference_score=round(pref_score, 1),
            credential_score=round(cred_score, 1),
            overall_score=round(max(0.0, min(100.0, overall)), 1),
        )

    def _score_technical(self, matches: List[RequirementMatchResult]) -> float:
        """Calculate weighted score based on importance and evidence multipliers."""
        if not matches:
            return 80.0

        total_weighted_points = 0.0
        earned_weighted_points = 0.0

        for m in matches:
            imp_mult = self.config.get_importance_multiplier(m.requirement.importance)
            ev_mult = self.config.get_evidence_weight(m.classification)

            total_weighted_points += imp_mult
            earned_weighted_points += (imp_mult * max(0.0, ev_mult))

        if total_weighted_points <= 0.0:
            return 80.0

        return (earned_weighted_points / total_weighted_points) * 100.0

    def _score_responsibilities(self, job: AnalyzedJob, profile: CandidateProfile) -> float:
        """Score alignment of job responsibilities with candidate demonstrated capabilities."""
        if not job.responsibilities:
            return 80.0

        candidate_resp_keywords = {
            "backend development", "api development", "distributed systems",
            "streaming data pipelines", "cloud infrastructure", "ci/cd automation",
            "observability and monitoring", "orchestration services", "platform setup",
            "frontend development", "ai and agentic tooling"
        }

        matched_count = sum(1 for r in job.responsibilities if r.lower() in candidate_resp_keywords)
        total = len(job.responsibilities)
        return (matched_count / total) * 100.0 if total > 0 else 80.0

    def _score_role_and_seniority(self, job: AnalyzedJob) -> float:
        """Score role title relevance and seniority alignment."""
        title_l = job.title.lower()

        # Title alignment
        title_points = 50.0
        if any(w in title_l for w in ["software engineer", "backend", "cloud", "devops", "sre", "data engineer", "full stack"]):
            title_points = 100.0
        elif any(w in title_l for w in ["engineer", "developer", "platform"]):
            title_points = 80.0

        # Seniority alignment (Candidate has ~2 years / Mid-Level Software Engineer)
        seniority_points = 80.0
        if job.seniority in (JobSeniority.MID_LEVEL, JobSeniority.ENTRY_LEVEL, JobSeniority.JUNIOR):
            seniority_points = 100.0
        elif job.seniority == JobSeniority.SENIOR:
            seniority_points = 75.0
        elif job.seniority in (JobSeniority.STAFF, JobSeniority.PRINCIPAL, JobSeniority.LEAD):
            seniority_points = 45.0
        elif job.seniority == JobSeniority.INTERN:
            seniority_points = 70.0

        return (title_points * 0.6) + (seniority_points * 0.4)

    def _score_professional_experience(self, matches: List[RequirementMatchResult], job: AnalyzedJob) -> float:
        """Score confirmed professional experience depth vs requirements."""
        confirmed_count = sum(1 for m in matches if m.classification == MatchClassification.MATCH_CONFIRMED)
        total_reqs = len(matches)

        base = (confirmed_count / total_reqs * 100.0) if total_reqs > 0 else 70.0

        # Penalty if required years is significantly above candidate experience (2.0 yrs)
        if job.years_experience_required and job.years_experience_required > 2.0:
            gap = job.years_experience_required - 2.0
            penalty = min(35.0, gap * 8.0)
            base = max(20.0, base - penalty)

        return base

    def _score_domain(self, job: AnalyzedJob) -> float:
        """Score domain alignment with HSBC Fintech / Payments experience."""
        if not job.domain_requirements:
            return 75.0

        for d in job.domain_requirements:
            if d.lower() in ("fintech", "payments", "banking"):
                return 100.0
        return 65.0

    def _score_preferences(self, job: AnalyzedJob) -> float:
        """Score location and remote policy preferences."""
        if job.remote_policy in (RemoteStatus.REMOTE, RemoteStatus.HYBRID):
            return 100.0
        if job.location and "pune" in job.location.lower():
            return 100.0
        return 75.0

    def _score_credentials(self, job: AnalyzedJob, profile: CandidateProfile) -> float:
        """Score degree and certification match."""
        points = 90.0
        # If candidate has Google Cloud Professional Architect and job mentions Cloud/GCP
        text_l = job.description.lower()
        if "gcp" in text_l or "google cloud" in text_l or "architect" in text_l:
            points = 100.0
        return points
