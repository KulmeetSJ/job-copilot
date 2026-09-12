"""Browser Automation Adapter Interface and Playwright Implementation."""

import asyncio
from pathlib import Path
import re
from typing import List, Optional
from job_copilot.browser.detector import FormDetector
from job_copilot.browser.models import BrowserElementType, BrowserField
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class BrowserAdapter:
    """Abstract interface for browser automation."""

    async def launch(self, headless: bool = True) -> None:
        raise NotImplementedError

    async def navigate(self, url: str) -> str:
        raise NotImplementedError

    async def get_current_url(self) -> str:
        raise NotImplementedError

    async def get_page_content(self) -> str:
        raise NotImplementedError

    async def inspect_page(self) -> List[BrowserField]:
        raise NotImplementedError

    async def fill_field(self, field: BrowserField, value: str) -> bool:
        raise NotImplementedError

    async def upload_file(self, field: BrowserField, file_path: str) -> bool:
        raise NotImplementedError

    async def click(self, selector_or_id: str) -> bool:
        raise NotImplementedError

    async def screenshot(self, output_path: str) -> Optional[str]:
        raise NotImplementedError

    async def wait_for_dom_idle(self, timeout_ms: int = 2000) -> None:
        raise NotImplementedError

    async def is_captcha_present(self) -> bool:
        raise NotImplementedError

    async def is_login_page(self) -> bool:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


class PlaywrightBrowserAdapter(BrowserAdapter):
    """Concrete Playwright browser controller."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def launch(self, headless: bool = True, storage_state_path: Optional[str] = None) -> None:
        """Launch Playwright browser instance, optionally restoring authenticated session state."""
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        context_kwargs = {
            "viewport": {"width": 1280, "height": 900},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 JobCopilot/1.0",
        }
        if storage_state_path and Path(storage_state_path).exists():
            context_kwargs["storage_state"] = str(storage_state_path)

        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()

    async def navigate(self, url: str) -> str:
        """Navigate to target URL or local fixture."""
        if not self._page:
            await self.launch()

        # Handle local file paths
        if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("file://"):
            url_path = Path(url).resolve()
            if url_path.exists():
                url = f"file://{url_path}"

        await self._page.goto(url, wait_until="load", timeout=30000)
        await self.wait_for_dom_idle(timeout_ms=500)
        return self._page.url

    async def get_current_url(self) -> str:
        if not self._page:
            return ""
        return self._page.url

    async def get_page_content(self) -> str:
        if not self._page:
            return ""
        return await self._page.content()

    async def inspect_page(self) -> List[BrowserField]:
        """Inspect page and extract form fields."""
        html = await self.get_page_content()
        fields = FormDetector.detect_fields_from_html(html)

        # Enhance selectors if locator exists
        for field in fields:
            if field.id_attr:
                field.selector = f"#{field.id_attr}"
            elif field.name:
                field.selector = f"[name='{field.name}']"

        return fields

    async def fill_field(self, field: BrowserField, value: str) -> bool:
        """Fill an input, textarea, select, radio, or checkbox."""
        if not self._page:
            return False

        try:
            loc = None
            if field.id_attr:
                loc = self._page.locator(f"#{field.id_attr}")
            elif field.name:
                loc = self._page.locator(f"[name='{field.name}']")
            elif field.selector:
                loc = self._page.locator(field.selector)

            if not loc or (await loc.count() == 0):
                logger.warning(f"Locator not found for field {field.field_id}")
                return False

            first_loc = loc.first

            if field.element_type == BrowserElementType.SELECT:
                await first_loc.select_option(label=value)
            elif field.element_type == BrowserElementType.INPUT_CHECKBOX:
                if str(value).lower() in ["true", "1", "yes", "checked"]:
                    await first_loc.check()
                else:
                    await first_loc.uncheck()
            elif field.element_type == BrowserElementType.INPUT_RADIO:
                # Find matching radio option
                radio_loc = self._page.locator(f"input[type='radio'][name='{field.name}'][value='{value}']")
                if await radio_loc.count() > 0:
                    await radio_loc.first.check()
                else:
                    await first_loc.check()
            else:
                await first_loc.fill(value)

            return True
        except Exception as e:
            logger.error(f"Error filling field {field.field_id} with value '{value}': {e}")
            return False

    async def upload_file(self, field: BrowserField, file_path: str) -> bool:
        """Upload file to input[type=file]."""
        if not self._page:
            return False

        try:
            path_obj = Path(file_path).resolve()
            if not path_obj.exists():
                logger.error(f"Upload file not found: {file_path}")
                return False

            loc = None
            if field.id_attr:
                loc = self._page.locator(f"#{field.id_attr}")
            elif field.name:
                loc = self._page.locator(f"[name='{field.name}']")
            elif field.selector:
                loc = self._page.locator(field.selector)

            if not loc or (await loc.count() == 0):
                # Fallback to general input[type=file]
                loc = self._page.locator("input[type='file']")

            if await loc.count() > 0:
                await loc.first.set_input_files(str(path_obj))
                return True
            return False
        except Exception as e:
            logger.error(f"Error uploading file {file_path} for field {field.field_id}: {e}")
            return False

    async def click(self, selector_or_id: str) -> bool:
        """Click an element by selector or ID."""
        if not self._page:
            return False
        try:
            loc = self._page.locator(selector_or_id)
            if await loc.count() > 0:
                await loc.first.click()
                await self.wait_for_dom_idle(500)
                return True
            return False
        except Exception as e:
            logger.error(f"Error clicking {selector_or_id}: {e}")
            return False

    async def screenshot(self, output_path: str) -> Optional[str]:
        """Capture page screenshot."""
        if not self._page:
            return None
        try:
            out_file = Path(output_path).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            await self._page.screenshot(path=str(out_file), full_page=True)
            return str(out_file)
        except Exception as e:
            logger.warning(f"Failed to capture screenshot: {e}")
            return None

    async def wait_for_dom_idle(self, timeout_ms: int = 2000) -> None:
        """Wait briefly for network and DOM stability."""
        if not self._page:
            return
        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            # Fallback timeout sleep
            await asyncio.sleep(timeout_ms / 1000.0)

    async def is_captcha_present(self) -> bool:
        """Detect CAPTCHA or bot verification challenges."""
        html = await self.get_page_content()
        captcha_indicators = [
            r"\bg-recaptcha\b",
            r"\bhcaptcha\b",
            r"\bcf-turnstile\b",
            r"\bchallenge-form\b",
            r"\bgeetest\b",
            r"\bverify\s+you\s+are\s+human\b",
            r"\bsecurity\s+check\b",
            r"\bbot\s+verification\b",
        ]
        for pattern in captcha_indicators:
            if re.search(pattern, html, re.IGNORECASE):
                return True
        return False

    async def is_login_page(self) -> bool:
        """Detect login / authentication requirement."""
        html = await self.get_page_content()
        login_indicators = [
            r"\bsign\s*in\s*to\s*apply\b",
            r"\blogin\s*to\s*apply\b",
            r"\bcreate\s*an\s*account\s*to\s*continue\b",
            r"\benter\s*your\s*password\b",
            r'<input[^>]+type=["\']password["\']',
        ]
        for pattern in login_indicators:
            if re.search(pattern, html, re.IGNORECASE):
                return True
        return False

    async def close(self) -> None:
        """Close browser context and driver."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
