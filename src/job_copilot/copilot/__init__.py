"""Phase 9 Continuous Job Copilot Package."""

from job_copilot.copilot.config import CopilotConfig, load_copilot_config
from job_copilot.copilot.explanations import ExplanationEngine
from job_copilot.copilot.learning import HistoricalLearningEngine
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
)
from job_copilot.copilot.orchestrator import CopilotOrchestrator
from job_copilot.copilot.prioritizer import OpportunityPrioritizer
from job_copilot.copilot.queue import CopilotQueueStore

__all__ = [
    "CopilotConfig",
    "load_copilot_config",
    "CopilotJob",
    "PriorityBand",
    "QueueStatus",
    "CopilotAction",
    "ClaimType",
    "EvidenceReference",
    "CopilotExplanation",
    "CopilotRecommendation",
    "HistoricalInsight",
    "CopilotDashboard",
    "OpportunityPrioritizer",
    "ExplanationEngine",
    "HistoricalLearningEngine",
    "CopilotQueueStore",
    "CopilotOrchestrator",
]
