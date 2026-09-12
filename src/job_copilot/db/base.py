"""Model registry for database metadata."""

from job_copilot.models import (
    Base,
    TimestampMixin,
    utc_now,
    Job,
    JobProvenance,
    RecommendationRecord,
    Application,
    ApplicationEventModel,
    ApplicationSnapshotModel,
    CopilotQueueRecord,
    SourceHealthRecord,
    ArtifactModel,
    BrowserTaskModel,
    DeviceRegistrationModel,
)

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
]
