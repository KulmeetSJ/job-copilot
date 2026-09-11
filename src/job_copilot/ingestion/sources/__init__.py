"""Source adapter package for job discovery and ingestion."""

from job_copilot.ingestion.sources.base import JobSource
from job_copilot.ingestion.sources.manual import ManualJobSource
from job_copilot.ingestion.sources.url import UrlJobSource
from job_copilot.ingestion.sources.feed import FeedJobSource

__all__ = ["JobSource", "ManualJobSource", "UrlJobSource", "FeedJobSource"]
