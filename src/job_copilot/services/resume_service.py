"""Resume Tailoring Service Orchestrator."""

import json
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from job_copilot.resume.analyzer import JobDescriptionAnalyzer
from job_copilot.resume.matcher import CandidateJobMatcher
from job_copilot.resume.llm import LLMResumeWriter
from job_copilot.resume.models import (
    JobAnalysis,
    JobMatchResult,
    ResumeGenerationResult,
    ResumeValidationResult,
    TailoredResume,
)
from job_copilot.resume.renderer import LaTeXResumeRenderer
from job_copilot.resume.selector import ResumeContentSelector
from job_copilot.resume.strategy import ResumeStrategyConfig, StrategyRegistry
from job_copilot.resume.summary import SummaryGenerator
from job_copilot.resume.validator import ResumeValidator
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class ResumeService:
    """
    Service layer orchestrating the Resume Tailoring Engine.
    Consumes canonical Master Candidate Profile and produces strategy-tailored resumes.
    """

    def __init__(
        self,
        master_profile_path: Optional[Path] = None,
        strategies_dir: Optional[Path] = None,
        generated_output_dir: Optional[Path] = None,
        llm_writer: Optional[LLMResumeWriter] = None,
    ):
        self.master_profile_path = master_profile_path or Path("data/candidate/master_profile.yaml")
        self.strategies_dir = strategies_dir or Path("data/resume_strategies")
        self.generated_output_dir = generated_output_dir or Path("data/generated")

        self.strategy_registry = StrategyRegistry(self.strategies_dir)
        self.analyzer = JobDescriptionAnalyzer()
        self.matcher = CandidateJobMatcher()
        self.summary_generator = SummaryGenerator()
        self.selector = ResumeContentSelector(self.summary_generator)
        self.llm_writer = llm_writer or LLMResumeWriter()
        self.renderer = LaTeXResumeRenderer()
        self.validator = ResumeValidator()

        self._profile_cache: Optional[CandidateProfile] = None

    def load_master_profile(self, reload: bool = False) -> CandidateProfile:
        """Load and parse the locked canonical Master Candidate Profile."""
        if self._profile_cache and not reload:
            return self._profile_cache

        if not self.master_profile_path.exists():
            raise FileNotFoundError(f"Master profile not found at {self.master_profile_path.resolve()}")

        with open(self.master_profile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Master profile file {self.master_profile_path} is empty")

        self._profile_cache = CandidateProfile.model_validate(data)
        return self._profile_cache

    def list_strategies(self) -> List[str]:
        """List all available strategy identifiers."""
        return self.strategy_registry.list_strategies()

    def get_strategy(self, name: str) -> ResumeStrategyConfig:
        """Get configuration for a specific strategy."""
        return self.strategy_registry.get_strategy(name)

    def analyze_job(
        self,
        job_description_text: str,
        title_override: Optional[str] = None,
        company_override: Optional[str] = None,
    ) -> JobAnalysis:
        """Analyze raw job description text into structured JobAnalysis."""
        return self.analyzer.analyze(
            job_description_text,
            title_override=title_override,
            company_override=company_override,
        )

    def match_job(
        self,
        analysis: JobAnalysis,
    ) -> JobMatchResult:
        """Match candidate profile against analyzed job requirements."""
        profile = self.load_master_profile()
        return self.matcher.match(analysis, profile)

    def generate_tailored_resume(
        self,
        strategy_name: str,
        job_description_text: Optional[str] = None,
        output_dir: Optional[Path] = None,
    ) -> ResumeGenerationResult:
        """
        Generate a complete tailored resume, render to LaTeX, compile to PDF, and validate.
        """
        profile = self.load_master_profile()
        strategy = self.get_strategy(strategy_name)

        analysis = None
        match_result = None
        if job_description_text:
            analysis = self.analyze_job(job_description_text)
            match_result = self.matcher.match(analysis, profile)

        # 1. Select Content (Attempt LLM tailored draft if JD provided and LLM available)
        tailored_resume = None
        if job_description_text and self.llm_writer and self.llm_writer.is_available():
            try:
                tailored_resume = self.llm_writer.generate_tailored_resume(
                    profile=profile,
                    strategy=strategy,
                    analysis=analysis,
                    match_result=match_result,
                )
            except Exception as e:
                logger.warning(f"LLM resume tailoring encountered error: {e}. Falling back to deterministic generator.")
                tailored_resume = None

        if not tailored_resume:
            tailored_resume = self.selector.select_content(
                profile=profile,
                strategy=strategy,
                analysis=analysis,
                match_result=match_result,
            )

        # 2. Render LaTeX
        tex_content = self.renderer.render_tex(tailored_resume)

        # 3. Determine Output Paths
        target_dir = output_dir or (self.generated_output_dir / strategy_name)
        target_dir.mkdir(parents=True, exist_ok=True)
        tex_path = target_dir / "latest.tex"
        self.renderer.write_tex(tex_content, tex_path)

        # 4. Compile PDF
        pdf_path, latex_error, page_count = self.renderer.compile_pdf(tex_path, target_dir)

        # 4b. Enforce 1-Page Constraint with Fallback
        # If an LLM-generated resume exceeded 1 page, fall back to deterministic selector
        if tailored_resume.metadata.get("llm_tailored") and (page_count and page_count > 1 or latex_error):
            logger.warning(
                f"LLM-generated resume exceeded 1 page (page_count={page_count}) or had latex error ({latex_error}). "
                f"Falling back to deterministic generator for guaranteed 1-page compliance."
            )
            tailored_resume = self.selector.select_content(
                profile=profile,
                strategy=strategy,
                analysis=analysis,
                match_result=match_result,
            )
            tex_content = self.renderer.render_tex(tailored_resume)
            self.renderer.write_tex(tex_content, tex_path)
            pdf_path, latex_error, page_count = self.renderer.compile_pdf(tex_path, target_dir)

        # 5. Validate Resume
        validation = self.validator.validate(
            resume=tailored_resume,
            profile=profile,
            pdf_path=pdf_path,
            latex_error=latex_error,
            page_count=page_count,
            analysis=analysis,
        )

        # 6. Save validation JSON
        val_json_path = target_dir / "validation.json"
        with open(val_json_path, "w", encoding="utf-8") as f:
            f.write(validation.model_dump_json(indent=2))

        return ResumeGenerationResult(
            strategy_name=strategy_name,
            tailored_resume=tailored_resume,
            tex_path=tex_path,
            pdf_path=pdf_path,
            validation=validation,
        )
