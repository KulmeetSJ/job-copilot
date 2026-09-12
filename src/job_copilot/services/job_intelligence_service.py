"""Job Intelligence Service Orchestrator and Artifact Persistence."""

import json
from pathlib import Path
from typing import Optional
import yaml

from job_copilot.matching.analyzer import JobAnalyzer
from job_copilot.matching.config import MatchingConfig, default_matching_config
from job_copilot.matching.matcher import CandidateMatcher
from job_copilot.matching.models import AnalyzedJob, JobAssessment
from job_copilot.matching.recommender import JobRecommender
from job_copilot.matching.scorer import FitScorer
from job_copilot.matching.strategy_selector import StrategySelector
from job_copilot.resume.models import ResumeGenerationResult
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.services.resume_service import ResumeService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class JobIntelligenceService:
    """
    High-level orchestrator for the Job Intelligence & Matching Engine.
    Handles JD ingestion, analysis, evidence-backed matching, multi-dimensional scoring,
    recommendation, artifact persistence, and Phase 3 resume tailoring integration.
    """

    def __init__(
        self,
        master_profile_path: Optional[Path] = None,
        jobs_data_dir: Optional[Path] = None,
        matching_config: Optional[MatchingConfig] = None,
    ):
        self.master_profile_path = master_profile_path or Path("data/candidate/master_profile.yaml")
        self.jobs_data_dir = jobs_data_dir or Path("data/jobs")
        self.config = matching_config or default_matching_config

        self.analyzer = JobAnalyzer()
        self.matcher = CandidateMatcher(self.config)
        self.scorer = FitScorer(self.config)
        self.strategy_selector = StrategySelector()
        self.recommender = JobRecommender(self.config)
        self.resume_service = ResumeService(master_profile_path=self.master_profile_path)

        self._profile_cache: Optional[CandidateProfile] = None

        # Ensure artifact directories exist
        self.raw_dir = self.jobs_data_dir / "raw"
        self.analyzed_dir = self.jobs_data_dir / "analyzed"
        self.matched_dir = self.jobs_data_dir / "matched"
        self.rec_dir = self.jobs_data_dir / "recommendations"

        for d in [self.raw_dir, self.analyzed_dir, self.matched_dir, self.rec_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def load_master_profile(self, reload: bool = False) -> CandidateProfile:
        """Load and cache the canonical Master Candidate Profile."""
        if self._profile_cache and not reload:
            return self._profile_cache

        if not self.master_profile_path.exists():
            raise FileNotFoundError(f"Master candidate profile not found at {self.master_profile_path}")

        with open(self.master_profile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Master profile file {self.master_profile_path} is empty")

        self._profile_cache = CandidateProfile.model_validate(data)
        return self._profile_cache

    @property
    def profile(self) -> CandidateProfile:
        """Accessor for loaded canonical candidate profile."""
        return self.load_master_profile()

    def analyze_job(
        self,
        raw_text: str,
        source: str = "text_input",
        source_url: Optional[str] = None,
        company_override: Optional[str] = None,
        title_override: Optional[str] = None,
        save_artifact: bool = True,
    ) -> AnalyzedJob:
        """Parse raw job description into structured AnalyzedJob and save artifacts."""
        analyzed_job = self.analyzer.analyze(
            raw_text=raw_text,
            source=source,
            source_url=source_url,
            company_override=company_override,
            title_override=title_override,
        )

        if save_artifact:
            # 1. Save raw text
            raw_path = self.raw_dir / f"{analyzed_job.job_id}.txt"
            raw_path.write_text(raw_text, encoding="utf-8")

            # 2. Save analyzed JSON
            analyzed_path = self.analyzed_dir / f"{analyzed_job.job_id}.json"
            analyzed_path.write_text(analyzed_job.model_dump_json(indent=2), encoding="utf-8")

        return analyzed_job

    def evaluate_job(
        self,
        raw_text: str,
        source: str = "text_input",
        source_url: Optional[str] = None,
        company_override: Optional[str] = None,
        title_override: Optional[str] = None,
        save_artifacts: bool = True,
    ) -> JobAssessment:
        """
        Execute the full pipeline: Ingestion -> Analysis -> Matching -> Scoring -> Strategy -> Recommendation.
        """
        profile = self.load_master_profile()

        # 1. Analyze Job
        analyzed_job = self.analyze_job(
            raw_text=raw_text,
            source=source,
            source_url=source_url,
            company_override=company_override,
            title_override=title_override,
            save_artifact=save_artifacts,
        )

        # 2. Match Requirements
        matches = self.matcher.match_job(analyzed_job, profile)

        # 3. Compute Fit Score Breakdown
        score_breakdown = self.scorer.compute_score(analyzed_job, profile, matches)

        # 4. Select Resume Strategy
        rec_strat, alt_strats, strat_reason = self.strategy_selector.select_strategy(analyzed_job, matches)

        # 5. Determine Recommendation, Gaps, Risks, and Report
        recommendation, strengths, partials, gaps, risks, human_report = self.recommender.evaluate(
            job=analyzed_job,
            matches=matches,
            scores=score_breakdown,
            recommended_strategy=rec_strat,
        )

        assessment = JobAssessment(
            job=analyzed_job,
            match_results=matches,
            score_breakdown=score_breakdown,
            recommendation=recommendation,
            strengths=strengths,
            partial_matches=partials,
            gaps=gaps,
            risks=risks,
            recommended_strategy=rec_strat,
            alternative_strategies=alt_strats,
            strategy_reasoning=strat_reason,
            human_report=human_report,
        )

        if save_artifacts:
            # Save matched results
            matched_path = self.matched_dir / f"{analyzed_job.job_id}.json"
            matched_data = [m.model_dump() for m in matches]
            matched_path.write_text(json.dumps(matched_data, indent=2), encoding="utf-8")

            # Save full assessment / recommendation
            rec_path = self.rec_dir / f"{analyzed_job.job_id}.json"
            rec_path.write_text(assessment.model_dump_json(indent=2), encoding="utf-8")

        return assessment

    def tailor_resume_for_job(
        self,
        job_text: str,
        strategy_override: Optional[str] = None,
    ) -> ResumeGenerationResult:
        """
        Execute Job Assessment and chain directly to Phase 3 resume tailoring.
        """
        assessment = self.evaluate_job(job_text)
        strategy = strategy_override or assessment.recommended_strategy
        return self.resume_service.generate_tailored_resume(strategy, job_description_text=job_text)
