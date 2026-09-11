"""Model registry for database metadata."""

from job_copilot.models.base import Base, TimestampMixin, utc_now
from job_copilot.models.job import Job, JobProvenance
from job_copilot.models.recommendation import RecommendationRecord
from job_copilot.models.application import (
    Application,
    ApplicationEventModel,
    ApplicationSnapshotModel,
)
from job_copilot.models.copilot import (
    CopilotQueueRecord,
    SourceHealthRecord,
)
from job_copilot.models.artifact import ArtifactModel

__all__ = [
    "Base",
    "TimestampMixin",
    "utc_now",
    "Job",
    "JobProvenance",
    "RecommendationRecord",
    "Application",
    "ApplicationEventModel",
    "ApplicationSnapshotModel",
    "CopilotQueueRecord",
    "SourceHealthRecord",
    "ArtifactModel",
]

