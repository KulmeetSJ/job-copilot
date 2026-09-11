"""Tracking adapter connecting Phase 4, 5, 6, 7 pipeline events to Phase 8 Tracking."""

from datetime import datetime
from typing import Any, Optional

from job_copilot.application.models import ApplicationPackage
from job_copilot.browser.models import BrowserSession, SubmissionResult
from job_copilot.services.tracking_service import TrackingService
from job_copilot.tracking.models import ApplicationRecord
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class TrackingAdapter:
    """
    Clean, non-invasive adapter that translates events across pipeline phases
    (Phase 5 Discovery, Phase 4 Matching, Phase 6 Preparation, Phase 7 Browser Workflow)
    into deterministic Phase 8 Tracking records and events.
    """

    def __init__(self, tracking_service: Optional[TrackingService] = None):
        self.tracking_service = tracking_service or TrackingService()

    def on_job_discovered(
        self,
        job_id: str,
        company: str,
        role: str,
        source: str = "unknown",
        canonical_url: Optional[str] = None,
        discovered_at: Optional[datetime] = None,
    ) -> ApplicationRecord:
        """Handle Phase 5 job discovery event."""
        return self.tracking_service.register_discovered_job(
            job_id=job_id,
            company=company,
            role=role,
            source=source,
            canonical_url=canonical_url,
            discovered_at=discovered_at,
        )

    def on_recommendation(
        self,
        job_id: str,
        assessment: Any,
    ) -> ApplicationRecord:
        """Handle Phase 4 recommendation and scoring event."""
        return self.tracking_service.register_recommendation(
            job_id=job_id,
            assessment=assessment,
        )

    def on_application_prepared(
        self,
        package: ApplicationPackage,
    ) -> ApplicationRecord:
        """Handle Phase 6 application package preparation event."""
        return self.tracking_service.register_prepared_application(package=package)

    def on_ready_for_review(
        self,
        job_id: str,
        browser_session_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ApplicationRecord:
        """Handle Phase 7 ready for review / form filling completion event."""
        return self.tracking_service.register_ready_for_review(
            job_id=job_id,
            browser_session_id=browser_session_id,
            notes=notes,
        )

    def on_submission(
        self,
        job_id: str,
        package: Optional[ApplicationPackage] = None,
        browser_session: Optional[BrowserSession] = None,
        submission_result: Optional[SubmissionResult] = None,
    ) -> ApplicationRecord:
        """Handle Phase 7 submission completion event."""
        return self.tracking_service.register_submission(
            job_id=job_id,
            package=package,
            browser_session=browser_session,
            submission_result=submission_result,
        )
