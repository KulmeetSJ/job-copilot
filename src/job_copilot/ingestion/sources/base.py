"""Abstract Base Class for all Job Source Adapters."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from job_copilot.ingestion.models import DiscoveryQuery, RawJob


class JobSource(ABC):
    """
    Abstract contract for all job sources (Manual, URL, Feed, Career Page).
    Every source returns raw RawJob instances without performing downstream analysis or scoring.
    """

    def __init__(self, name: str, source_type: str):
        self.name = name
        self.source_type = source_type

    @abstractmethod
    def discover(self, query: DiscoveryQuery) -> List[RawJob]:
        """
        Discover jobs matching the query criteria.
        Returns list of RawJob items.
        """
        pass

    @abstractmethod
    def fetch(self, identifier_or_url: str) -> Optional[RawJob]:
        """
        Fetch a single job posting by URL, file path, or source ID.
        Returns RawJob if found, or None.
        """
        pass
