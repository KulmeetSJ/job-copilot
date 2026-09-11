"""Structured Feed and Career Page adapter for job discovery."""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from job_copilot.ingestion.models import DiscoveryQuery, RawJob
from job_copilot.ingestion.sources.base import JobSource
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class FeedJobSource(JobSource):
    """
    Source adapter for querying structured career feeds or mock job endpoints.
    Allows registering in-memory feeds or provider callbacks for offline testing and extensible feeds.
    """

    def __init__(
        self,
        name: str = "structured_feed",
        feed_provider: Optional[Callable[[DiscoveryQuery], List[Dict[str, Any]]]] = None,
    ):
        super().__init__(name=name, source_type="feed")
        self.feed_provider = feed_provider
        self._static_jobs: List[Dict[str, Any]] = []

    def set_static_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        """Set static in-memory job records (ideal for testing & offline feeds)."""
        self._static_jobs = jobs

    def discover(self, query: DiscoveryQuery) -> List[RawJob]:
        """Discover jobs matching query from provider or static list."""
        raw_items: List[Dict[str, Any]] = []

        if self.feed_provider:
            try:
                raw_items = self.feed_provider(query)
            except Exception as e:
                logger.error(f"Feed provider '{self.name}' error during discover: {e}")
                raise e
        else:
            raw_items = self._static_jobs

        results: List[RawJob] = []
        for item in raw_items:
            # Filter by keywords if specified
            if query.keywords:
                title = item.get("title", "").lower()
                desc = item.get("description", "").lower()
                kw_match = any(kw.lower() in title or kw.lower() in desc for kw in query.keywords)
                if not kw_match:
                    continue

            # Filter by location if specified
            if query.locations:
                loc = item.get("location", "").lower()
                loc_match = any(l.lower() in loc for l in query.locations) or (query.remote_preferred and "remote" in loc)
                if not loc_match:
                    continue

            results.append(
                RawJob(
                    source=self.name,
                    source_job_id=item.get("id") or item.get("job_id"),
                    source_url=item.get("url"),
                    company=item.get("company"),
                    title=item.get("title"),
                    location=item.get("location"),
                    raw_description=item.get("description", ""),
                    discovered_at=datetime.utcnow(),
                    retrieved_at=datetime.utcnow(),
                    source_metadata=item.get("metadata", {}),
                )
            )

            if len(results) >= query.limit_per_source:
                break

        return results

    def fetch(self, identifier_or_url: str) -> Optional[RawJob]:
        """Lookup job by source_job_id or url in feed."""
        for item in self._static_jobs:
            if item.get("id") == identifier_or_url or item.get("url") == identifier_or_url:
                return RawJob(
                    source=self.name,
                    source_job_id=item.get("id"),
                    source_url=item.get("url"),
                    company=item.get("company"),
                    title=item.get("title"),
                    location=item.get("location"),
                    raw_description=item.get("description", ""),
                    discovered_at=datetime.utcnow(),
                    retrieved_at=datetime.utcnow(),
                    source_metadata=item.get("metadata", {}),
                )
        return None
