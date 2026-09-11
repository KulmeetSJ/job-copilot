"""Resume generation, tailoring, and rendering package."""

from job_copilot.resume.analyzer import JobDescriptionAnalyzer
from job_copilot.resume.matcher import CandidateJobMatcher
from job_copilot.resume.models import (
    JobAnalysis,
    JobMatchResult,
    JobRequirement,
    ResumeBullet,
    ResumeExperience,
    ResumeGenerationResult,
    ResumeProject,
    ResumeSkillGroup,
    ResumeValidationResult,
    TailoredResume,
)
from job_copilot.resume.renderer import LaTeXResumeRenderer
from job_copilot.resume.selector import ResumeContentSelector
from job_copilot.resume.strategy import ResumeStrategyConfig, StrategyRegistry
from job_copilot.resume.summary import SummaryGenerator
from job_copilot.resume.validator import ResumeValidator

__all__ = [
    "JobDescriptionAnalyzer",
    "CandidateJobMatcher",
    "JobRequirement",
    "JobAnalysis",
    "JobMatchResult",
    "ResumeBullet",
    "ResumeExperience",
    "ResumeProject",
    "ResumeSkillGroup",
    "TailoredResume",
    "ResumeValidationResult",
    "ResumeGenerationResult",
    "LaTeXResumeRenderer",
    "ResumeContentSelector",
    "ResumeStrategyConfig",
    "StrategyRegistry",
    "SummaryGenerator",
    "ResumeValidator",
]
