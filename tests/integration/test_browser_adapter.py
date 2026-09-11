"""Integration tests for Playwright browser adapter."""

from pathlib import Path
import pytest
from job_copilot.browser.adapter import PlaywrightBrowserAdapter
from job_copilot.browser.models import BrowserElementType, BrowserField


@pytest.mark.asyncio
async def test_adapter_navigation_and_inspection():
    adapter = PlaywrightBrowserAdapter()
    try:
        await adapter.launch(headless=True)
        fixture_path = str(Path("tests/browser/fixtures/basic_form.html").resolve())
        url = await adapter.navigate(fixture_path)
        assert "basic_form.html" in url

        fields = await adapter.inspect_page()
        assert len(fields) >= 8

        fname = next((f for f in fields if f.name == "first_name"), None)
        assert fname is not None
        assert fname.element_type == BrowserElementType.INPUT_TEXT

        # Test filling field
        ok = await adapter.fill_field(fname, "Alex")
        assert ok is True

        # Test screenshot
        shot_path = "data/test_screenshots/test_basic.png"
        saved = await adapter.screenshot(shot_path)
        assert saved is not None
        assert Path(saved).exists()
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_adapter_detects_login_page():
    adapter = PlaywrightBrowserAdapter()
    try:
        await adapter.launch(headless=True)
        fixture_path = str(Path("tests/browser/fixtures/login_page.html").resolve())
        await adapter.navigate(fixture_path)
        is_login = await adapter.is_login_page()
        assert is_login is True
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_adapter_detects_captcha_page():
    adapter = PlaywrightBrowserAdapter()
    try:
        await adapter.launch(headless=True)
        fixture_path = str(Path("tests/browser/fixtures/captcha_page.html").resolve())
        await adapter.navigate(fixture_path)
        is_captcha = await adapter.is_captcha_present()
        assert is_captcha is True
    finally:
        await adapter.close()
