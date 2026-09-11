"""Phase 8 Application Tracking and Outcome Analytics package."""

from job_copilot.tracking.analytics import AnalyticsEngine
from job_copilot.tracking.lifecycle import LifecycleValidator
from job_copilot.tracking.models import (
    AnalyticsDashboard,
    ApplicationEvent,
    ApplicationLifecycleStatus,
    ApplicationRecord,
    ApplicationSnapshot,
    CohortMetric,
    ConversionRates,
    EventSource,
    FunnelMetrics,
    ResponseTimeMetrics,
    utc_now,
)
from job_copilot.tracking.store import TrackingStore

__all__ = [
    "ApplicationLifecycleStatus",
    "EventSource",
    "ApplicationEvent",
    "ApplicationSnapshot",
    "ApplicationRecord",
    "FunnelMetrics",
    "ConversionRates",
    "CohortMetric",
    "ResponseTimeMetrics",
    "AnalyticsDashboard",
    "utc_now",
    "LifecycleValidator",
    "TrackingStore",
    "AnalyticsEngine",
]
