"""Registry for discovering and resolving source-specific browser adapters."""

from typing import Dict, List, Optional
from urllib.parse import urlparse

from job_copilot.browser_worker.adapters.base import JobSourceBrowserAdapter
from job_copilot.browser_worker.adapters.generic import GenericPortalAdapter
from job_copilot.browser_worker.adapters.instahyre import InstahyreAdapter
from job_copilot.browser_worker.adapters.linkedin import LinkedInAdapter
from job_copilot.browser_worker.adapters.naukri import NaukriAdapter
from job_copilot.browser_worker.exceptions import DomainSecurityError
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class SourceAdapterRegistry:
    """
    Central registry mapping job portal sources and domains to secure browser adapters.
    
    SECURITY INVARIANTS:
    1. Prevents arbitrary caller-specified Python classes or dynamic module execution.
    2. Enforces explicit domain validation and mapping.
    3. Rejects unknown/untrusted domains.
    """

    def __init__(self):
        self._adapters_by_source: Dict[str, JobSourceBrowserAdapter] = {}
        self._generic_adapter = GenericPortalAdapter()
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in authenticated and generic source adapters."""
        self.register(LinkedInAdapter())
        self.register(NaukriAdapter())
        self.register(InstahyreAdapter())
        self.register(self._generic_adapter)

    def register(self, adapter: JobSourceBrowserAdapter) -> None:
        """Register a validated adapter instance."""
        self._adapters_by_source[adapter.source_name.lower()] = adapter
        logger.debug(f"Registered browser adapter for source: '{adapter.source_name}'")

    def get_adapter(
        self,
        source: Optional[str] = None,
        target_url: Optional[str] = None,
    ) -> JobSourceBrowserAdapter:
        """
        Resolve the appropriate source adapter by explicit source name or target URL domain.
        Raises DomainSecurityError if domain is not supported.
        """
        # 1. Match by explicit source name
        if source and source.lower() in self._adapters_by_source:
            return self._adapters_by_source[source.lower()]

        # 2. Match by target URL domain
        if target_url:
            parsed = urlparse(target_url)
            hostname = (parsed.hostname or "").lower()

            for adapter in self._adapters_by_source.values():
                if any(
                    hostname == d or hostname.endswith("." + d)
                    for d in adapter.supported_domains
                ):
                    return adapter

        # Fallback to generic if domain matches generic allowed list
        if target_url and self._generic_adapter.validate_url(target_url):
            return self._generic_adapter

        raise DomainSecurityError(f"No registered source adapter supports URL '{target_url}' (source='{source}')")

    def list_supported_sources(self) -> List[str]:
        """Return list of all registered source names."""
        return list(self._adapters_by_source.keys())
