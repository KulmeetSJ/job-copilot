"""Safe public HTTP URL job source adapter."""

from datetime import datetime
from typing import List, Optional
import urllib.error
import urllib.request
from job_copilot.ingestion.models import DiscoveryQuery, RawJob
from job_copilot.ingestion.sources.base import JobSource
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_USER_AGENT = "JobCopilot/1.0 (Public Job Ingestion; +https://github.com/Apply-Agent)"
DEFAULT_TIMEOUT_SECONDS = 10


class UrlJobSource(JobSource):
    """
    Fetches raw job content from permitted public URLs via standard HTTP GET.
    Adheres strictly to timeouts, error handling, and does not perform anti-bot evasion.
    """

    def __init__(
        self,
        name: str = "url_fetch",
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        super().__init__(name=name, source_type="url")
        self.user_agent = user_agent
        self.timeout = timeout

    def discover(self, query: DiscoveryQuery) -> List[RawJob]:
        """Direct URL source does not perform search discovery."""
        return []

    def fetch(self, identifier_or_url: str) -> Optional[RawJob]:
        """Fetch raw HTML/text from a single public job URL."""
        url = identifier_or_url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            logger.warning(f"Invalid HTTP/HTTPS URL: {url}")
            return None

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.7",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                charset = "utf-8"
                if "charset=" in content_type.lower():
                    charset = content_type.lower().split("charset=")[-1].split(";")[0].strip()

                raw_bytes = response.read()
                try:
                    raw_text = raw_bytes.decode(charset)
                except (UnicodeDecodeError, LookupError):
                    raw_text = raw_bytes.decode("utf-8", errors="replace")

                from job_copilot.ingestion.metadata_extractor import JobMetadataExtractor
                meta = JobMetadataExtractor.extract_from_html(raw_text, url=url)

                return RawJob(
                    source=self.name,
                    source_job_id=None,
                    source_url=url,
                    company=meta.company,
                    title=meta.title,
                    location=meta.location,
                    raw_description=raw_text,
                    discovered_at=datetime.utcnow(),
                    retrieved_at=datetime.utcnow(),
                    source_metadata={
                        "http_status": response.status,
                        "content_type": content_type,
                        "ats_name": meta.ats_name,
                        "source_type": meta.source_type,
                        "extracted_meta": meta.metadata,
                    },
                )
        except urllib.error.HTTPError as e:
            logger.warning(f"HTTP Error {e.code} fetching URL {url}: {e.reason}")
            return None
        except urllib.error.URLError as e:
            logger.warning(f"URL Error fetching {url}: {e.reason}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            return None
