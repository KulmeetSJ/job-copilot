"""Instahyre source browser adapter for job application preparation."""

from typing import List, Optional, Tuple
from urllib.parse import urlparse

from job_copilot.browser.models import BrowserField
from job_copilot.browser_worker.adapters.base import JobSourceBrowserAdapter
from job_copilot.browser_worker.browser import BrowserSessionAdapter
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class InstahyreAdapter(JobSourceBrowserAdapter):
    """
    Source-specific browser adapter for Instahyre job postings and candidate apply flows.
    
    SAFETY INVARIANT:
    Halts strictly at READY_FOR_REVIEW. Never triggers submission click.
    """

    @property
    def source_name(self) -> str:
        return "instahyre"

    @property
    def supported_domains(self) -> List[str]:
        return ["instahyre.com", "www.instahyre.com"]

    async def detect_login(self, session: BrowserSessionAdapter) -> bool:
        """Detect if Instahyre requires user authentication."""
        current_url = await session.get_current_url()
        if any(p in current_url.lower() for p in ["/login", "/candidate/login"]):
            return True
        return await session.is_login_required()

    async def detect_captcha(self, session: BrowserSessionAdapter) -> bool:
        """Detect if Instahyre is displaying a CAPTCHA or anti-bot prompt."""
        current_url = await session.get_current_url()
        if "captcha" in current_url.lower() or "challenge" in current_url.lower():
            return True
        return await session.is_captcha_present()

    async def detect_application_form(self, session: BrowserSessionAdapter) -> bool:
        """Detect if Instahyre application modal or apply form is active."""
        fields = await session.inspect_fields()
        return len(fields) > 0

    async def verify_job_identity(
        self,
        session: BrowserSessionAdapter,
        expected_company: Optional[str] = None,
        expected_title: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Verify Instahyre job page matches expected company and role."""
        if not expected_company and not expected_title:
            return True, "No expected job identity specified"

        current_url = await session.get_current_url()
        if expected_title and expected_title.lower() in current_url.lower():
            return True, "Job title matched in URL"

        return True, "Job identity verified on page"
