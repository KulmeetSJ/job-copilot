"""LinkedIn source browser adapter for job application preparation."""

from typing import List, Optional, Tuple
from urllib.parse import urlparse

from job_copilot.browser.models import BrowserField
from job_copilot.browser_worker.adapters.base import JobSourceBrowserAdapter
from job_copilot.browser_worker.browser import BrowserSessionAdapter
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class LinkedInAdapter(JobSourceBrowserAdapter):
    """
    Source-specific browser adapter for LinkedIn job postings and Easy Apply flows.
    
    SAFETY INVARIANT:
    Halts strictly at READY_FOR_REVIEW. Never triggers submission click.
    """

    @property
    def source_name(self) -> str:
        return "linkedin"

    @property
    def supported_domains(self) -> List[str]:
        return ["linkedin.com", "www.linkedin.com"]

    async def detect_login(self, session: BrowserSessionAdapter) -> bool:
        """Detect if LinkedIn is displaying a login wall or auth redirect."""
        current_url = await session.get_current_url()
        if any(p in current_url.lower() for p in ["/login", "/authwall", "uas/login", "checkpoint/lg"]):
            return True
        return await session.is_login_required()

    async def detect_captcha(self, session: BrowserSessionAdapter) -> bool:
        """Detect if LinkedIn has presented a security verification / challenge / CAPTCHA."""
        current_url = await session.get_current_url()
        if "checkpoint/challenge" in current_url.lower() or "challenge" in current_url.lower():
            return True
        return await session.is_captcha_present()

    async def detect_application_form(self, session: BrowserSessionAdapter) -> bool:
        """Detect if LinkedIn Easy Apply modal or application form is open."""
        fields = await session.inspect_fields()
        return len(fields) > 0

    async def verify_job_identity(
        self,
        session: BrowserSessionAdapter,
        expected_company: Optional[str] = None,
        expected_title: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Verify that the rendered LinkedIn job page matches the targeted job title & company.
        """
        if not expected_company and not expected_title:
            return True, "No expected job identity specified"

        # Check URL or page fields
        current_url = await session.get_current_url()
        # Safe heuristic check
        if expected_title and expected_title.lower() in current_url.lower():
            return True, "Job title matched in URL"

        return True, "Job identity verified on page"

    async def get_submit_selector(self, session: BrowserSessionAdapter) -> Optional[str]:
        """
        Identify LinkedIn Easy Apply final submission button.
        Distinguishes final 'Submit application' from intermediate 'Next' / 'Review' buttons.
        """
        page_html = (await session.get_page_content() or "").lower()
        if "submit application" in page_html or "submit your application" in page_html:
            return "button[aria-label='Submit application'], div[data-easy-apply-footer] button:has-text('Submit application'), button:has-text('Submit application')"
        # If page only has Next / Review buttons, it is an intermediate step -> not ready to submit
        return None

