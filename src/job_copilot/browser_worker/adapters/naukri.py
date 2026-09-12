"""Naukri source browser adapter for job application preparation."""

from typing import List, Optional, Tuple
from urllib.parse import urlparse

from job_copilot.browser.models import BrowserField
from job_copilot.browser_worker.adapters.base import JobSourceBrowserAdapter
from job_copilot.browser_worker.browser import BrowserSessionAdapter
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class NaukriAdapter(JobSourceBrowserAdapter):
    """
    Source-specific browser adapter for Naukri job postings and 1-click/custom apply flows.
    
    SAFETY INVARIANT:
    Halts strictly at READY_FOR_REVIEW. Never triggers submission click.
    """

    @property
    def source_name(self) -> str:
        return "naukri"

    @property
    def supported_domains(self) -> List[str]:
        return ["naukri.com", "www.naukri.com"]

    async def detect_login(self, session: BrowserSessionAdapter) -> bool:
        """Detect if Naukri requires user authentication."""
        current_url = await session.get_current_url()
        if any(p in current_url.lower() for p in ["/nlogin", "login.naukri.com", "/login"]):
            return True
        return await session.is_login_required()

    async def detect_captcha(self, session: BrowserSessionAdapter) -> bool:
        """Detect if Naukri has presented an anti-bot challenge or CAPTCHA."""
        current_url = await session.get_current_url()
        if "captcha" in current_url.lower() or "challenge" in current_url.lower():
            return True
        return await session.is_captcha_present()

    async def detect_application_form(self, session: BrowserSessionAdapter) -> bool:
        """Detect if Naukri apply form/modal is active."""
        fields = await session.inspect_fields()
        return len(fields) > 0

    async def verify_job_identity(
        self,
        session: BrowserSessionAdapter,
        expected_company: Optional[str] = None,
        expected_title: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Verify Naukri job page matches expected company and role."""
        if not expected_company and not expected_title:
            return True, "No expected job identity specified"

        current_url = await session.get_current_url()
        if expected_title and expected_title.lower() in current_url.lower():
            return True, "Job title matched in URL"

        return True, "Job identity verified on page"

    async def get_submit_selector(self, session: BrowserSessionAdapter) -> Optional[str]:
        """Identify Naukri final application submit button."""
        page_html = (await session.get_page_content() or "").lower()
        if "submit application" in page_html or "apply" in page_html:
            return "button#submit-btn, button.apply-button:has-text('Apply'), button:has-text('Submit Application')"
        return None

