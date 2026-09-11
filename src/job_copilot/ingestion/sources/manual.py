"""Manual job source adapter for local text files and direct string input."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional
from job_copilot.ingestion.models import DiscoveryQuery, RawJob
from job_copilot.ingestion.sources.base import JobSource
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class ManualJobSource(JobSource):
    """Handles manual job ingestion from local files or raw text."""

    def __init__(self, name: str = "manual"):
        super().__init__(name=name, source_type="manual")

    def discover(self, query: DiscoveryQuery) -> List[RawJob]:
        """Manual source does not perform search discovery."""
        return []

    def fetch(self, identifier_or_url: str) -> Optional[RawJob]:
        """Fetch job text from local file path."""
        path = Path(identifier_or_url)
        if not path.exists() or not path.is_file():
            logger.warning(f"File not found: {identifier_or_url}")
            return None

        try:
            content = path.read_text(encoding="utf-8")
            return RawJob(
                source=self.name,
                source_job_id=path.stem,
                source_url=None,
                raw_description=content,
                discovered_at=datetime.utcnow(),
                retrieved_at=datetime.utcnow(),
                source_metadata={"file_path": str(path.resolve())},
            )
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            return None

    def ingest_text(
        self,
        text: str,
        company: Optional[str] = None,
        title: Optional[str] = None,
        location: Optional[str] = None,
        source_url: Optional[str] = None,
        source_job_id: Optional[str] = None,
    ) -> RawJob:
        """Ingest raw job description directly from string."""
        return RawJob(
            source=self.name,
            source_job_id=source_job_id,
            source_url=source_url,
            company=company,
            title=title,
            location=location,
            raw_description=text,
            discovered_at=datetime.utcnow(),
            retrieved_at=datetime.utcnow(),
            source_metadata={"input_type": "text_string"},
        )
