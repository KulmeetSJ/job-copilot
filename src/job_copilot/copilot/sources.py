"""Job sources registry and health monitoring for Phase 9.2."""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import yaml

from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class DiscoveryMode(str, Enum):
    """Execution mode for discovering jobs from a source."""
    PUBLIC = "PUBLIC"
    AUTHENTICATED_BROWSER = "AUTHENTICATED_BROWSER"
    USER_PROVIDED_SEARCH_URL = "USER_PROVIDED_SEARCH_URL"
    FEED = "FEED"
    MANUAL = "MANUAL"
    UNSUPPORTED = "UNSUPPORTED"


class SourceState(str, Enum):
    """Operational health/availability state of a source."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    UNSUPPORTED = "UNSUPPORTED"
    DISABLED = "DISABLED"


class JobSource(BaseModel):
    """Configuration for an individual career source or job board."""
    id: str
    name: str
    type: str = "job_board"
    enabled: bool = True
    priority: str = "medium"  # critical, high, medium, low
    discovery_mode: DiscoveryMode = DiscoveryMode.PUBLIC
    requires_login: bool = False
    supports_public_discovery: bool = True
    check_interval_minutes: int = 180
    urls: List[str] = Field(default_factory=list)
    reference_url: Optional[str] = None
    search_categories: List[str] = Field(default_factory=list)
    search: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class SourceHealthReport(BaseModel):
    """Operational health report for a job source."""
    source_id: str
    name: str
    state: SourceState
    enabled: bool
    discovery_mode: DiscoveryMode
    requires_login: bool
    check_interval_minutes: int
    last_checked_at: Optional[datetime] = None
    message: Optional[str] = None


class SourceScheduleConfig(BaseModel):
    """Periodic check intervals organized by priority tier."""
    critical_interval_minutes: int = 60
    high_interval_minutes: int = 180
    medium_interval_minutes: int = 360
    low_interval_minutes: int = 720


class JobSourcesConfig(BaseModel):
    """Consolidated job sources registry and schedules."""
    schedules: SourceScheduleConfig = Field(default_factory=SourceScheduleConfig)
    sources: List[JobSource] = Field(default_factory=list)

    def get_source(self, source_id: str) -> Optional[JobSource]:
        """Look up source configuration by ID."""
        for s in self.sources:
            if s.id.lower() == source_id.lower():
                return s
        return None

    def list_sources(self, enabled_only: bool = False) -> List[JobSource]:
        """List configured sources, optionally filtering for enabled ones."""
        if enabled_only:
            return [s for s in self.sources if s.enabled]
        return list(self.sources)

    def get_health_reports(self, runtime_states: Optional[Dict[str, Dict[str, Any]]] = None) -> List[SourceHealthReport]:
        """
        Produce a health summary for all sources.
        Respects safety boundaries: if requires_login without session, marks LOGIN_REQUIRED.
        """
        states = runtime_states or {}
        reports: List[SourceHealthReport] = []

        for s in self.sources:
            if not s.enabled:
                st = SourceState.DISABLED
                msg = "Source is currently disabled in configuration"
                last_chk = None
            elif s.id in states:
                runtime_info = states[s.id]
                st = runtime_info.get("state", SourceState.ACTIVE)
                msg = runtime_info.get("message")
                last_chk = runtime_info.get("last_checked_at")
            elif s.requires_login:
                st = SourceState.LOGIN_REQUIRED
                msg = "Authenticated browser session required for private portal search"
                last_chk = None
            else:
                st = SourceState.ACTIVE
                msg = "Available for scheduled public discovery"
                last_chk = None

            reports.append(
                SourceHealthReport(
                    source_id=s.id,
                    name=s.name,
                    state=st,
                    enabled=s.enabled,
                    discovery_mode=s.discovery_mode,
                    requires_login=s.requires_login,
                    check_interval_minutes=s.check_interval_minutes,
                    last_checked_at=last_chk,
                    message=msg,
                )
            )

        return reports


def _parse_discovery_mode(val: Any) -> DiscoveryMode:
    """Safely map string to DiscoveryMode enum."""
    if not val:
        return DiscoveryMode.PUBLIC
    val_upper = str(val).upper()
    try:
        return DiscoveryMode(val_upper)
    except ValueError:
        if "AUTH" in val_upper:
            return DiscoveryMode.AUTHENTICATED_BROWSER
        elif "FEED" in val_upper:
            return DiscoveryMode.FEED
        elif "MANUAL" in val_upper:
            return DiscoveryMode.MANUAL
        return DiscoveryMode.PUBLIC


def load_job_sources_config(config_path: Optional[Path] = None) -> JobSourcesConfig:
    """Load job sources registry from YAML file or return robust defaults."""
    target_path = config_path or Path("data/config/job_sources.yaml")
    if not target_path.exists():
        logger.info(f"Job sources config not found at {target_path}, using built-in defaults.")
        return JobSourcesConfig()

    try:
        raw_data = yaml.safe_load(target_path.read_text(encoding="utf-8")) or {}
        sched_data = raw_data.get("schedules", {})
        sched_cfg = SourceScheduleConfig(
            critical_interval_minutes=sched_data.get("critical", {}).get("interval_minutes", 60),
            high_interval_minutes=sched_data.get("high", {}).get("interval_minutes", 180),
            medium_interval_minutes=sched_data.get("medium", {}).get("interval_minutes", 360),
            low_interval_minutes=sched_data.get("low", {}).get("interval_minutes", 720),
        )

        sources_list: List[JobSource] = []
        for s in raw_data.get("sources", []):
            mode = _parse_discovery_mode(s.get("discovery_mode"))
            sources_list.append(
                JobSource(
                    id=s.get("id", "unknown"),
                    name=s.get("name", "Unknown Source"),
                    type=s.get("type", "job_board"),
                    enabled=s.get("enabled", True),
                    priority=s.get("priority", "medium"),
                    discovery_mode=mode,
                    requires_login=s.get("requires_login", False),
                    supports_public_discovery=s.get("supports_public_discovery", True),
                    check_interval_minutes=s.get("check_interval_minutes", 180),
                    urls=s.get("urls", []),
                    reference_url=s.get("reference_url"),
                    search_categories=s.get("search_categories", []),
                    search=s.get("search"),
                    notes=s.get("notes"),
                )
            )

        return JobSourcesConfig(
            schedules=sched_cfg,
            sources=sources_list,
        )
    except Exception as e:
        logger.warning(f"Error reading job_sources config: {e}. Falling back to default configuration.")
        return JobSourcesConfig()
