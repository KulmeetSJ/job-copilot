"""Source adapters package for Phase 10C Authenticated Job Portals."""

from job_copilot.browser_worker.adapters.base import JobSourceBrowserAdapter
from job_copilot.browser_worker.adapters.generic import GenericPortalAdapter
from job_copilot.browser_worker.adapters.instahyre import InstahyreAdapter
from job_copilot.browser_worker.adapters.linkedin import LinkedInAdapter
from job_copilot.browser_worker.adapters.naukri import NaukriAdapter
from job_copilot.browser_worker.adapters.registry import SourceAdapterRegistry

__all__ = [
    "JobSourceBrowserAdapter",
    "GenericPortalAdapter",
    "LinkedInAdapter",
    "NaukriAdapter",
    "InstahyreAdapter",
    "SourceAdapterRegistry",
]
