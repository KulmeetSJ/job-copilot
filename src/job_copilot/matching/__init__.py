"""Job Intelligence & Matching Engine package."""

from job_copilot.matching.analyzer import JobAnalyzer
from job_copilot.matching.config import MatchingConfig, default_matching_config
from job_copilot.matching.matcher import CandidateMatcher
from job_copilot.matching.models import (
    AnalyzedJob,
    FitScoreBreakdown,
    JobAssessment,
    JobRecommendation,
    JobSeniority,
    MatchClassification,
    RequirementImportance,
    RequirementMatchResult,
    TechnicalRequirement,
    WorkAuthorizationRequirement,
)
from job_copilot.matching.recommender import JobRecommender
from job_copilot.matching.scorer import FitScorer
from job_copilot.matching.strategy_selector import StrategySelector

__all__ = [
    "JobAnalyzer",
    "CandidateMatcher",
    "FitScorer",
    "StrategySelector",
    "JobRecommender",
    "MatchingConfig",
    "default_matching_config",
    "AnalyzedJob",
    "TechnicalRequirement",
    "RequirementMatchResult",
    "FitScoreBreakdown",
    "JobAssessment",
    "MatchClassification",
    "RequirementImportance",
    "JobSeniority",
    "JobRecommendation",
    "WorkAuthorizationRequirement",
]
