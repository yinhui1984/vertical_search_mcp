"""
Environment verification tests.

These tests verify that the development environment is properly set up.
"""

import pytest
from playwright.async_api import async_playwright


@pytest.mark.asyncio
async def test_playwright_can_launch_browser() -> None:
    """Verify that Playwright can launch a browser."""
    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(headless=True)
        assert browser is not None
        await browser.close()
    finally:
        await playwright.stop()


@pytest.mark.asyncio
async def test_playwright_can_create_page() -> None:
    """Verify that Playwright can create a page."""
    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        assert page is not None
        await page.close()
        await context.close()
        await browser.close()
    finally:
        await playwright.stop()
