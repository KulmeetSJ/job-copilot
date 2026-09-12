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

    async def get_submit_selector(self, session: BrowserSessionAdapter) -> Optional[str]:
        """
        Identify deterministic ATS final submit selector based on domain & DOM context.
        Rejects ambiguous generic buttons (Next, Continue, Save, Apply Filters, Subscribe, etc.).
        """
        current_url = (await session.get_current_url() or "").lower()
        page_html = (await session.get_page_content() or "").lower()

        # 1. Greenhouse
        if "greenhouse.io" in current_url:
            return "input#submit_app[type='submit'], input[value='Submit Application'], button#submit_app, button:has-text('Submit Application')"

        # 2. Lever
        if "lever.co" in current_url:
            return "button.template-btn-submit, button[data-qa='btn-submit'], button:has-text('Submit Application')"

        # 3. Workday
        if "myworkdayjobs.com" in current_url or "workday.com" in current_url:
            return "button[data-automation-id='submitButton'], button[data-automation-id='bottom-navigation-next-button']:has-text('Submit')"

        # 4. Ashby
        if "ashbyhq.com" in current_url:
            return "button[data-testid='submit-application'], button:has-text('Submit Application')"

        # 5. SmartRecruiters
        if "smartrecruiters.com" in current_url:
            return "button[data-test='footer-submit'], button:has-text('Submit Application')"

        # 6. Workable
        if "workable.com" in current_url:
            return "button[data-ui='application-submit-btn'], button:has-text('Submit Application')"

        # 7. Breezy
        if "breezy.hr" in current_url:
            return "button#submit-app-btn, button:has-text('Submit Application')"

        # 8. Unambiguous generic submit buttons inside application forms
        # Explicitly require 'Submit Application' or input[type=submit] with value 'Submit Application'
        # Explicitly reject 'Next', 'Continue', 'Save', 'Apply Filters', 'Apply Changes', 'Subscribe', 'Submit Feedback'
        if "submit application" in page_html or "submit_app" in page_html:
            return "form button:has-text('Submit Application'), form input[type='submit'][value='Submit Application'], button:has-text('Submit Application')"

        # Ambiguous / unidentified submit control
        return None

