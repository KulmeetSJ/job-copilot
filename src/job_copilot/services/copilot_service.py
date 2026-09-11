"""Service interface for Phase 9 Continuous Job Copilot."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from job_copilot.application.models import ApplicationPackage
from job_copilot.copilot.config import CopilotConfig, load_copilot_config
from job_copilot.copilot.models import (
    CopilotDashboard,
    CopilotJob,
    HistoricalInsight,
    PriorityBand,
    QueueStatus,
)
from job_copilot.copilot.orchestrator import CopilotOrchestrator
from job_copilot.copilot.queue import CopilotQueueStore
from job_copilot.ingestion.models import DiscoveryQuery
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.services.browser_workflow_service import BrowserWorkflowService
from job_copilot.services.discovery_service import DiscoveryService
from job_copilot.services.job_intelligence_service import JobIntelligenceService
from job_copilot.services.tracking_service import TrackingService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class CopilotService:
    """
    High-level service interface for the Continuous Job Copilot.
    Provides API, CLI, and integration layers with a clean, unified interface.
    """

    def __init__(
        self,
        config: Optional[CopilotConfig] = None,
        discovery_service: Optional[DiscoveryService] = None,
        intelligence_service: Optional[JobIntelligenceService] = None,
        prep_service: Optional[ApplicationPrepService] = None,
        browser_service: Optional[BrowserWorkflowService] = None,
        tracking_service: Optional[TrackingService] = None,
        queue_store: Optional[CopilotQueueStore] = None,
    ):
        self.orchestrator = CopilotOrchestrator(
            config=config,
            discovery_service=discovery_service,
            intelligence_service=intelligence_service,
            prep_service=prep_service,
            browser_service=browser_service,
            tracking_service=tracking_service,
            queue_store=queue_store,
        )

    def discover(self, query: Optional[DiscoveryQuery] = None) -> List[CopilotJob]:
        """Execute continuous discovery and process discovered opportunities."""
        return self.orchestrator.discover_opportunities(query=query)

    def process_job(self, job_id: str) -> Optional[CopilotJob]:
        """Process a single job opportunity through intelligence, prioritization, and queueing."""
        return self.orchestrator.process_job(job_id=job_id)

    def process_all_stored(self) -> List[CopilotJob]:
        """Process all stored canonical jobs that haven't been queued yet."""
        canonical_jobs = self.orchestrator.discovery_service.store.list_canonical_jobs(include_duplicates=False)
        results: List[CopilotJob] = []
        for job in canonical_jobs:
            processed = self.orchestrator.process_job(job.job_id)
            if processed:
                results.append(processed)
        return results

    def prepare(
        self,
        job_id: str,
        custom_questions: Optional[List[Any]] = None,
        strategy_override: Optional[str] = None,
    ) -> ApplicationPackage:
        """One-click application package preparation (Phase 6)."""
        return self.orchestrator.prepare_job(
            job_id=job_id,
            custom_questions=custom_questions,
            strategy_override=strategy_override,
        )

    def apply(
        self,
        job_id: str,
        confirmation_token: Optional[str] = None,
        headless: bool = True,
    ) -> Dict[str, Any]:
        """Browser application handoff with human confirmation check (Phase 7)."""
        return self.orchestrator.apply_job(
            job_id=job_id,
            confirmation_token=confirmation_token,
            headless=headless,
        )

    async def apply_async(
        self,
        job_id: str,
        confirmation_token: Optional[str] = None,
        headless: bool = True,
    ) -> Dict[str, Any]:
        """Asynchronous browser application handoff with human confirmation check."""
        return await self.orchestrator.apply_job_async(
            job_id=job_id,
            confirmation_token=confirmation_token,
            headless=headless,
        )

    def approve(self, job_id: str) -> Optional[CopilotJob]:
        """Approve an opportunity for preparation."""
        return self.orchestrator.queue_store.update_status(
            job_id=job_id,
            new_status=QueueStatus.APPROVED,
            notes="Candidate approved opportunity for application preparation.",
        )

    def skip(self, job_id: str, reason: Optional[str] = None) -> Optional[CopilotJob]:
        """Skip an opportunity."""
        return self.orchestrator.queue_store.update_status(
            job_id=job_id,
            new_status=QueueStatus.SKIPPED,
            notes=f"Candidate skipped opportunity. Reason: {reason or 'Not interested'}",
        )

    def archive(self, job_id: str) -> Optional[CopilotJob]:
        """Archive an opportunity."""
        return self.orchestrator.queue_store.update_status(
            job_id=job_id,
            new_status=QueueStatus.ARCHIVED,
            notes="Candidate archived opportunity.",
        )

    def get_dashboard(self) -> CopilotDashboard:
        """Get daily Copilot dashboard."""
        return self.orchestrator.get_dashboard()

    def get_queue(
        self,
        status: Optional[QueueStatus] = None,
        priority_band: Optional[PriorityBand] = None,
        min_priority_score: Optional[float] = None,
    ) -> List[CopilotJob]:
        """List opportunities from the prioritized queue."""
        return self.orchestrator.queue_store.list_jobs(
            queue_status=status,
            priority_band=priority_band,
            min_priority_score=min_priority_score,
        )

    def get_job(self, job_id: str) -> Optional[CopilotJob]:
        """Fetch a specific opportunity by job ID."""
        return self.orchestrator.queue_store.get(job_id=job_id)

    def get_insights(self) -> List[HistoricalInsight]:
        """Get conservative, sample-safe historical outcome insights."""
        return self.orchestrator.get_insights()

    def get_targets(self):
        """Get candidate target companies, job families, and preferences."""
        return self.orchestrator.get_targets()

    def get_sources(self, enabled_only: bool = False):
        """List configured career sources."""
        return self.orchestrator.get_sources(enabled_only=enabled_only)

    def get_sources_health(self):
        """Get operational health reports for all career sources."""
        return self.orchestrator.get_sources_health()
