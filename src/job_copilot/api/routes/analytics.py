"""REST API endpoints for Phase 8 Outcome and Pipeline Analytics."""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Query
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.models import (
    AnalyticsDashboard,
    CohortMetric,
    ConversionRates,
    FunnelMetrics,
    ResponseTimeMetrics,
)

router = APIRouter(prefix="/api/analytics", tags=["Outcome Analytics"])

_service: Optional[TrackingService] = None


def get_tracking_service() -> TrackingService:
    global _service
    if _service is None:
        _service = TrackingService()
    return _service


@router.get("/dashboard", response_model=AnalyticsDashboard)
def get_analytics_dashboard(
    from_date: Optional[datetime] = Query(None, description="Start date filter (ISO format)"),
    to_date: Optional[datetime] = Query(None, description="End date filter (ISO format)"),
):
    """Get complete analytics dashboard summary."""
    service = get_tracking_service()
    return service.get_analytics_dashboard(from_date=from_date, to_date=to_date)


@router.get("/funnel", response_model=FunnelMetrics)
def get_funnel_metrics(
    from_date: Optional[datetime] = Query(None, description="Start date filter"),
    to_date: Optional[datetime] = Query(None, description="End date filter"),
):
    """Get application pipeline funnel counts."""
    service = get_tracking_service()
    return service.get_funnel(from_date=from_date, to_date=to_date)


@router.get("/conversion", response_model=ConversionRates)
def get_conversion_rates(
    from_date: Optional[datetime] = Query(None, description="Start date filter"),
    to_date: Optional[datetime] = Query(None, description="End date filter"),
):
    """Get application stage conversion percentages."""
    service = get_tracking_service()
    return service.get_conversion(from_date=from_date, to_date=to_date)


@router.get("/strategies", response_model=List[CohortMetric])
def get_strategy_performance():
    """Get outcome performance grouped by resume strategy."""
    service = get_tracking_service()
    return service.get_strategy_metrics()


@router.get("/recommendations", response_model=List[CohortMetric])
def get_recommendation_performance():
    """Get outcome performance grouped by recommendation tier."""
    service = get_tracking_service()
    return service.get_recommendation_metrics()


@router.get("/sources", response_model=List[CohortMetric])
def get_source_performance():
    """Get outcome performance grouped by job discovery source."""
    service = get_tracking_service()
    return service.get_source_metrics()


@router.get("/response-times", response_model=List[ResponseTimeMetrics])
def get_response_times():
    """Get milestone response times across application stages."""
    service = get_tracking_service()
    return service.get_response_time_metrics()
