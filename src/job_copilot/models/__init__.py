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
from job_copilot.models.browser_session import BrowserSessionModel
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.models.device import DeviceRegistrationModel, DeviceStatus

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
    "BrowserTaskModel",
    "DeviceRegistrationModel",
    "DeviceStatus",
]

