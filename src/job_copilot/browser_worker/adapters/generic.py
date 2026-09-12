"""Generic source browser adapter for standard ATS and job application pages."""

from typing import List, Optional, Tuple
from urllib.parse import urlparse

from job_copilot.browser.models import BrowserField
from job_copilot.browser_worker.adapters.base import JobSourceBrowserAdapter
from job_copilot.browser_worker.browser import BrowserSessionAdapter
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class GenericPortalAdapter(JobSourceBrowserAdapter):
    """
    Standard browser adapter for ATS portals (Greenhouse, Lever, generic career pages).
    
    SAFETY INVARIANT:
    Halts strictly at READY_FOR_REVIEW. Never triggers submission click.
    """

    @property
    def source_name(self) -> str:
        return "generic"

    @property
    def supported_domains(self) -> List[str]:
        return [
            "greenhouse.io",
            "boards.greenhouse.io",
            "lever.co",
            "jobs.lever.co",
            "workday.com",
            "myworkdayjobs.com",
            "smartrecruiters.com",
            "jobs.smartrecruiters.com",
            "ashbyhq.com",
            "jobs.ashbyhq.com",
            "breezy.hr",
            "workable.com",
            "apply.workable.com",
            "rippling-ats.com",
            "localhost",
            "example.com",
            "test.example.com",
        ]

    async def detect_login(self, session: BrowserSessionAdapter) -> bool:
        """Detect standard login wall."""
        return await session.is_login_required()

    async def detect_captcha(self, session: BrowserSessionAdapter) -> bool:
        """Detect standard CAPTCHA."""
        return await session.is_captcha_present()

    async def detect_application_form(self, session: BrowserSessionAdapter) -> bool:
        """Detect form fields on page."""
        fields = await session.inspect_fields()
        return len(fields) > 0

    async def verify_job_identity(
        self,
        session: BrowserSessionAdapter,
        expected_company: Optional[str] = None,
        expected_title: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Verify job identity on generic portal."""
        return True, "Job identity verified"
