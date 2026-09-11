"""Unit tests for Phase 9.2 Job Sources Registry and Health Monitoring."""

import pytest
from job_copilot.copilot.sources import (
    DiscoveryMode,
    JobSourcesConfig,
    SourceHealthReport,
    SourceState,
    load_job_sources_config,
)


def test_job_sources_configuration_loading():
    """Verify that all configured job sources and periodic schedules load correctly."""
    cfg: JobSourcesConfig = load_job_sources_config()

    # Verify required sources exist
    src_ids = [s.id for s in cfg.sources]
    expected_sources = [
        "linkedin_pune",
        "naukri",
        "instahyre",
        "wellfound",
        "welcome_to_the_jungle",
        "we_work_remotely",
        "example_source",
    ]
    for exp_id in expected_sources:
        assert exp_id in src_ids, f"Expected source '{exp_id}' in sources registry"

    # Verify LinkedIn Pune configuration
    li = cfg.get_source("linkedin_pune")
    assert li is not None
    assert li.requires_login is True
    assert li.discovery_mode == DiscoveryMode.AUTHENTICATED_BROWSER
    assert li.priority == "critical"
    assert li.check_interval_minutes == 60
    assert "Pune" in li.search.get("locations", [])

    # Verify Instahyre configuration
    ih = cfg.get_source("instahyre")
    assert ih is not None
    assert ih.requires_login is True
    assert ih.discovery_mode == DiscoveryMode.AUTHENTICATED_BROWSER

    # Verify Wellfound & We Work Remotely public discovery
    wf = cfg.get_source("wellfound")
    assert wf is not None
    assert wf.discovery_mode == DiscoveryMode.PUBLIC
    assert wf.supports_public_discovery is True

    wwr = cfg.get_source("we_work_remotely")
    assert wwr is not None
    assert wwr.discovery_mode == DiscoveryMode.PUBLIC
    assert wwr.check_interval_minutes == 360

    # Verify schedules
    assert cfg.schedules.critical_interval_minutes == 60
    assert cfg.schedules.high_interval_minutes == 180
    assert cfg.schedules.medium_interval_minutes == 360
    assert cfg.schedules.low_interval_minutes == 720


def test_source_filtering_and_retrieval():
    """Verify listing all sources vs enabled sources only."""
    cfg = load_job_sources_config()

    all_sources = cfg.list_sources(enabled_only=False)
    enabled_sources = cfg.list_sources(enabled_only=True)

    assert len(all_sources) > len(enabled_sources)
    assert any(not s.enabled for s in all_sources)
    assert all(s.enabled for s in enabled_sources)


def test_source_health_reporting_and_safety_boundaries():
    """
    Verify health report generation and safety state transitions:
    - Public sources -> ACTIVE
    - Authenticated sources without session -> LOGIN_REQUIRED (non-fatal)
    - Disabled sources -> DISABLED
    - Blocked/CAPTCHA sources -> BLOCKED/PAUSED without crashing
    """
    cfg = load_job_sources_config()

    # 1. Default health report without active runtime overrides
    reports = cfg.get_health_reports()
    report_dict = {r.source_id: r for r in reports}

    assert report_dict["wellfound"].state == SourceState.ACTIVE
    assert report_dict["welcome_to_the_jungle"].state == SourceState.ACTIVE
    assert report_dict["we_work_remotely"].state == SourceState.ACTIVE
    assert report_dict["linkedin_pune"].state == SourceState.LOGIN_REQUIRED
    assert report_dict["naukri"].state == SourceState.LOGIN_REQUIRED
    assert report_dict["instahyre"].state == SourceState.LOGIN_REQUIRED
    assert report_dict["example_source"].state == SourceState.DISABLED

    # 2. Simulated runtime status with CAPTCHA or blocking on one source
    simulated_runtime = {
        "naukri": {
            "state": SourceState.BLOCKED,
            "message": "Cloudflare / Anti-bot verification detected. Manual human resolution required.",
        },
        "instahyre": {
            "state": SourceState.PAUSED,
            "message": "Rate limit backoff active.",
        },
    }

    runtime_reports = cfg.get_health_reports(runtime_states=simulated_runtime)
    runtime_dict = {r.source_id: r for r in runtime_reports}

    assert runtime_dict["naukri"].state == SourceState.BLOCKED
    assert runtime_dict["instahyre"].state == SourceState.PAUSED
    # Other sources remain healthy and untouched
    assert runtime_dict["wellfound"].state == SourceState.ACTIVE
    assert runtime_dict["we_work_remotely"].state == SourceState.ACTIVE
