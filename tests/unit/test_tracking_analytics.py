"""Unit tests for Phase 8 Analytics and Funnel Computations."""

from datetime import datetime, timezone, timedelta
from job_copilot.tracking.analytics import AnalyticsEngine
from job_copilot.tracking.models import (
    ApplicationEvent,
    ApplicationLifecycleStatus,
    ApplicationRecord,
    ApplicationSnapshot,
    FunnelMetrics,
    utc_now,
)


def test_funnel_and_conversion_calculations():
    now = utc_now()
    apps = []
    events = []

    # Create 20 mock applications
    for i in range(20):
        app_id = f"app-{i}"
        t_sub = now - timedelta(days=20 - i)
        app_events = [
            ApplicationEvent(event_id=f"e-sub-{i}", application_id=app_id, job_id=f"j-{i}", event_type=ApplicationLifecycleStatus.SUBMITTED, timestamp=t_sub),
        ]
        # 8 receive recruiter responses
        if i < 8:
            t_resp = t_sub + timedelta(days=2)
            app_events.append(ApplicationEvent(event_id=f"e-resp-{i}", application_id=app_id, job_id=f"j-{i}", event_type=ApplicationLifecycleStatus.RECRUITER_RESPONSE, timestamp=t_resp))
        # 4 reach interviews
        if i < 4:
            t_intv = t_sub + timedelta(days=5)
            app_events.append(ApplicationEvent(event_id=f"e-intv-{i}", application_id=app_id, job_id=f"j-{i}", event_type=ApplicationLifecycleStatus.INTERVIEW, timestamp=t_intv))
        # 2 reach offers
        if i < 2:
            t_off = t_sub + timedelta(days=12)
            app_events.append(ApplicationEvent(event_id=f"e-off-{i}", application_id=app_id, job_id=f"j-{i}", event_type=ApplicationLifecycleStatus.OFFER, timestamp=t_off))

        record = ApplicationRecord(
            application_id=app_id,
            job_id=f"j-{i}",
            company=f"Company {i % 4}",
            role="Senior Engineer",
            source="manual" if i % 2 == 0 else "url",
            discovered_at=t_sub - timedelta(days=1),
            recommended_at=t_sub - timedelta(days=1),
            prepared_at=t_sub,
            submitted_at=t_sub,
            resume_strategy="backend_java" if i % 2 == 0 else "cloud_devops",
            match_score=85.0 if i % 2 == 0 else 72.0,
            recommendation="APPLY" if i % 2 == 0 else "REVIEW",
            events=app_events,
        )
        apps.append(record)
        events.extend(app_events)

    funnel = AnalyticsEngine.compute_funnel(apps, events)
    assert funnel.submitted == 20
    assert funnel.recruiter_responses == 8
    assert funnel.interviews == 4
    assert funnel.offers == 2

    conversion = AnalyticsEngine.compute_conversion(funnel)
    assert conversion.response_rate == 40.0
    assert conversion.interview_rate == 20.0
    assert conversion.offer_rate == 10.0
    assert conversion.is_statistically_reliable is True


def test_small_sample_size_warning():
    funnel = FunnelMetrics(
        discovered=2,
        recommended=2,
        prepared=2,
        submitted=2,
        recruiter_responses=1,
        interviews=1,
        offers=1,
    )
    conv = AnalyticsEngine.compute_conversion(funnel)
    assert conv.is_statistically_reliable is False
    assert conv.sample_size_warning is not None
    assert "N=2 < 10" in conv.sample_size_warning


def test_response_time_metrics():
    now = utc_now()
    apps = []

    # App 1: 3 days to response, 6 days to interview, 10 days to offer
    e1 = [
        ApplicationEvent(event_id="e1", application_id="a1", job_id="j1", event_type=ApplicationLifecycleStatus.SUBMITTED, timestamp=now),
        ApplicationEvent(event_id="e2", application_id="a1", job_id="j1", event_type=ApplicationLifecycleStatus.RECRUITER_RESPONSE, timestamp=now + timedelta(days=3)),
        ApplicationEvent(event_id="e3", application_id="a1", job_id="j1", event_type=ApplicationLifecycleStatus.INTERVIEW, timestamp=now + timedelta(days=6)),
        ApplicationEvent(event_id="e4", application_id="a1", job_id="j1", event_type=ApplicationLifecycleStatus.OFFER, timestamp=now + timedelta(days=10)),
    ]
    apps.append(ApplicationRecord(application_id="a1", job_id="j1", company="C1", role="SWE", submitted_at=now, events=e1))

    # App 2: 5 days to response, 8 days to interview, 14 days to offer
    e2 = [
        ApplicationEvent(event_id="e5", application_id="a2", job_id="j2", event_type=ApplicationLifecycleStatus.SUBMITTED, timestamp=now),
        ApplicationEvent(event_id="e6", application_id="a2", job_id="j2", event_type=ApplicationLifecycleStatus.RECRUITER_RESPONSE, timestamp=now + timedelta(days=5)),
        ApplicationEvent(event_id="e7", application_id="a2", job_id="j2", event_type=ApplicationLifecycleStatus.INTERVIEW, timestamp=now + timedelta(days=8)),
        ApplicationEvent(event_id="e8", application_id="a2", job_id="j2", event_type=ApplicationLifecycleStatus.OFFER, timestamp=now + timedelta(days=14)),
    ]
    apps.append(ApplicationRecord(application_id="a2", job_id="j2", company="C2", role="SWE", submitted_at=now, events=e2))

    rt = AnalyticsEngine.compute_response_times(apps)
    resp_metric = next(m for m in rt if m.metric_name == "submission_to_response")
    assert resp_metric.median_days == 4.0
    assert resp_metric.sample_count == 2
