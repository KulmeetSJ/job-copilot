"""Persistent Storage for Application Tracking and Event Logs."""

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Dict, List, Optional

from job_copilot.tracking.models import (
    ApplicationEvent,
    ApplicationRecord,
    ApplicationSnapshot,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class TrackingStore:
    """
    File-backed persistent storage for applications, immutable event logs,
    and submission snapshots.
    """

    def __init__(
        self,
        tracking_dir: Optional[Path] = None,
        applications_dir: Optional[Path] = None,
    ):
        self.tracking_dir = tracking_dir or Path("data/tracking")
        self.applications_dir = applications_dir or Path("data/applications")
        self._lock = threading.Lock()

        self.tracking_dir.mkdir(parents=True, exist_ok=True)
        self._init_files()

    def _init_files(self) -> None:
        apps_file = self.tracking_dir / "applications.json"
        if not apps_file.exists():
            apps_file.write_text("{}", encoding="utf-8")

        events_file = self.tracking_dir / "events.json"
        if not events_file.exists():
            events_file.write_text("[]", encoding="utf-8")

    def save_application(self, app_record: ApplicationRecord) -> None:
        """Persist or update an application record and its snapshot."""
        with self._lock:
            # 1. Update central applications registry
            apps_file = self.tracking_dir / "applications.json"
            registry = {}
            if apps_file.exists():
                try:
                    registry = json.loads(apps_file.read_text(encoding="utf-8"))
                except Exception:
                    registry = {}

            registry[app_record.application_id] = json.loads(app_record.model_dump_json())
            apps_file.write_text(json.dumps(registry, indent=2), encoding="utf-8")

            # 2. Persist in job specific directory data/applications/<job_id>/tracking/
            if app_record.job_id:
                job_track_dir = self.applications_dir / app_record.job_id / "tracking"
                job_track_dir.mkdir(parents=True, exist_ok=True)

                (job_track_dir / "application.json").write_text(
                    app_record.model_dump_json(indent=2), encoding="utf-8"
                )

                if app_record.snapshot:
                    (job_track_dir / "snapshot.json").write_text(
                        app_record.snapshot.model_dump_json(indent=2), encoding="utf-8"
                    )

                if app_record.events:
                    events_data = [e.model_dump(mode="json") for e in app_record.events]
                    (job_track_dir / "events.json").write_text(
                        json.dumps(events_data, indent=2), encoding="utf-8"
                    )

    def append_event(self, event: ApplicationEvent) -> None:
        """Append an event to the immutable global ledger and application log."""
        with self._lock:
            events_file = self.tracking_dir / "events.json"
            events: List[Dict] = []
            if events_file.exists():
                try:
                    events = json.loads(events_file.read_text(encoding="utf-8"))
                except Exception:
                    events = []

            # Deduplication check by event_id or exact (app_id, event_type, timestamp)
            event_dict = json.loads(event.model_dump_json())
            is_dup = any(
                e.get("event_id") == event.event_id
                or (
                    e.get("application_id") == event.application_id
                    and e.get("event_type") == event.event_type.value
                    and e.get("timestamp") == event_dict.get("timestamp")
                )
                for e in events
            )
            if not is_dup:
                events.append(event_dict)
                events_file.write_text(json.dumps(events, indent=2), encoding="utf-8")

            # Also update the application record's event list
            apps_file = self.tracking_dir / "applications.json"
            if apps_file.exists():
                try:
                    registry = json.loads(apps_file.read_text(encoding="utf-8"))
                    if event.application_id in registry:
                        app_data = registry[event.application_id]
                        app_events = app_data.get("events", [])
                        if not any(e.get("event_id") == event.event_id for e in app_events):
                            app_events.append(event_dict)
                            app_data["events"] = app_events
                            app_data["current_status"] = event.event_type.value
                            app_data["current_status_at"] = event_dict.get("timestamp")
                            app_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                            registry[event.application_id] = app_data
                            apps_file.write_text(json.dumps(registry, indent=2), encoding="utf-8")

                            # Update job specific tracking
                            job_id = app_data.get("job_id")
                            if job_id:
                                job_track_dir = self.applications_dir / job_id / "tracking"
                                if job_track_dir.exists():
                                    (job_track_dir / "application.json").write_text(
                                        json.dumps(app_data, indent=2), encoding="utf-8"
                                    )
                                    (job_track_dir / "events.json").write_text(
                                        json.dumps(app_events, indent=2), encoding="utf-8"
                                    )
                except Exception as e:
                    logger.error(f"Failed updating application with new event: {e}")

    def get_application(self, application_id: str) -> Optional[ApplicationRecord]:
        """Fetch application record by ID."""
        apps_file = self.tracking_dir / "applications.json"
        if not apps_file.exists():
            return None
        try:
            registry = json.loads(apps_file.read_text(encoding="utf-8"))
            if application_id in registry:
                return ApplicationRecord.model_validate(registry[application_id])
        except Exception as e:
            logger.error(f"Error loading application {application_id}: {e}")
        return None

    def get_application_by_job_id(self, job_id: str) -> Optional[ApplicationRecord]:
        """Fetch application record by associated job ID."""
        all_apps = self.list_applications()
        for app in all_apps:
            if app.job_id == job_id:
                return app
        return None

    def list_applications(self) -> List[ApplicationRecord]:
        """List all tracked applications."""
        apps_file = self.tracking_dir / "applications.json"
        if not apps_file.exists():
            return []
        try:
            registry = json.loads(apps_file.read_text(encoding="utf-8"))
            return [ApplicationRecord.model_validate(v) for v in registry.values()]
        except Exception as e:
            logger.error(f"Error listing applications: {e}")
            return []

    def get_events(self, application_id: Optional[str] = None) -> List[ApplicationEvent]:
        """Get event list, optionally filtered by application ID."""
        events_file = self.tracking_dir / "events.json"
        if not events_file.exists():
            return []
        try:
            data = json.loads(events_file.read_text(encoding="utf-8"))
            all_events = [ApplicationEvent.model_validate(e) for e in data]
            if application_id:
                return [e for e in all_events if e.application_id == application_id]
            return all_events
        except Exception as e:
            logger.error(f"Error loading events: {e}")
            return []
