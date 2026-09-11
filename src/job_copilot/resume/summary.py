"""Deterministic Professional Summary Generator."""

from typing import Optional
from job_copilot.resume.models import JobAnalysis
from job_copilot.resume.strategy import ResumeStrategyConfig
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class SummaryGenerator:
    """
    Generates a truthful, deterministic executive summary for resumes.
    Strictly follows facts in the Master Profile without unsupported AI fluff.
    """

    def generate(
        self,
        strategy: ResumeStrategyConfig,
        profile: CandidateProfile,
        analysis: Optional[JobAnalysis] = None,
    ) -> str:
        """
        Generate a tailored summary based on the strategy template and confirmed profile facts.
        """
        # Base template from strategy configuration
        template = strategy.summary_template.strip()

        # If a JD analysis is provided with specific matched keywords, we can lightly customize
        # while keeping the factual baseline intact.
        if analysis and analysis.company:
            # Optionally reference target role context if desired, or keep pure template
            pass

        return template
