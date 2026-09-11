"""Playwright browser management and session adapter isolation."""

import asyncio
from pathlib import Path
from typing import Any, List, Optional
from job_copilot.browser.adapter import BrowserAdapter, PlaywrightBrowserAdapter
from job_copilot.browser.detector import FormDetector
from job_copilot.browser.models import BrowserElementType, BrowserField
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class BrowserManager:
    """Manages the lifecycle of the isolated Playwright browser process."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._adapter: Optional[PlaywrightBrowserAdapter] = None

    async def get_adapter(self) -> PlaywrightBrowserAdapter:
        """Initialize and return active Playwright browser adapter."""
        if self._adapter is None:
            self._adapter = PlaywrightBrowserAdapter()
            await self._adapter.launch(headless=self.headless)
            logger.debug("BrowserManager launched Playwright browser instance.")
        return self._adapter

    async def close(self) -> None:
        """Safely shut down the browser instance."""
        if self._adapter is not None:
            try:
                await self._adapter.close()
                logger.debug("BrowserManager cleanly shut down browser instance.")
            except Exception as e:
                logger.warning(f"Notice while closing browser adapter: {e}")
            finally:
                self._adapter = None


class BrowserSessionAdapter:
    """Encapsulates page-level interactions with strict error handling and DOM safety."""

    def __init__(self, adapter: BrowserAdapter):
        self.adapter = adapter

    async def navigate(self, url: str) -> str:
        """Navigate to target application form URL."""
        return await self.adapter.navigate(url)

    async def get_current_url(self) -> str:
        """Retrieve current page URL."""
        return await self.adapter.get_current_url()

    async def inspect_fields(self) -> List[BrowserField]:
        """Inspect and return detected form fields."""
        return await self.adapter.inspect_page()

    async def fill_field(self, field: BrowserField, value: str) -> bool:
        """Fill an individual form field."""
        return await self.adapter.fill_field(field, value)

    async def upload_file(self, field: BrowserField, file_path: str) -> bool:
        """Upload a file to a file input field."""
        return await self.adapter.upload_file(field, file_path)

    async def click_element(self, selector: str) -> bool:
        """Click an element matching the selector."""
        return await self.adapter.click(selector)

    async def screenshot(self, output_path: str) -> Optional[str]:
        """Capture full page screenshot."""
        return await self.adapter.screenshot(output_path)

    async def is_captcha_present(self) -> bool:
        """Check for CAPTCHA / anti-bot challenges."""
        return await self.adapter.is_captcha_present()

    async def is_login_required(self) -> bool:
        """Check if page is behind an authentication wall."""
        return await self.adapter.is_login_page()

    async def wait_for_idle(self, timeout_ms: int = 1500) -> None:
        """Wait for network and DOM idle."""
        await self.adapter.wait_for_dom_idle(timeout_ms=timeout_ms)
