"""
Content fetcher module.

This module handles fetching full article content from URLs using Playwright.
Supports platform-specific content extraction with multiple selector fallbacks.
"""

import asyncio
import hashlib
import re
from typing import Optional, Dict, Any
from core.browser_pool import BrowserPool
from core.logger import get_logger
from core.anti_crawler_detector import AntiCrawlerDetector, DetectionType
from core.config_loader import load_anti_crawler_config


class ContentFetcher:
    """
    Content fetcher for extracting article content from URLs.

    Uses platform-specific selectors to extract main content while removing
    interference elements (ads, QR codes, navigation, etc.).
    """

    def __init__(self, browser_pool: BrowserPool, config: Dict[str, Any]) -> None:
        """
        Initialize content fetcher.

        Args:
            browser_pool: BrowserPool instance for getting pages
            config: Platform configuration dictionary (from platforms.yaml)
        """
        self.browser_pool = browser_pool
        self.config = config
        self.logger = get_logger("vertical_search.content_fetcher")

        # Initialize anti-crawler detector
        try:
            anti_crawler_config = load_anti_crawler_config()
            self.detector = AntiCrawlerDetector(anti_crawler_config)
        except Exception as e:
            self.logger.warning(
                f"Failed to load anti-crawler config: {e}, continuing without detection"
            )
            self.detector = AntiCrawlerDetector({})

    async def fetch_content(self, url: str, platform: str, timeout: int = 10) -> Optional[str]:
        """
        Fetch article content from URL.

        Args:
            url: Article URL to fetch
            platform: Platform name (e.g., 'weixin', 'zhihu')
            timeout: Request timeout in seconds (default: 10)

        Returns:
            Extracted content string, or None if extraction fails
        """
        if not url or not url.strip():
            self.logger.warning(f"Empty or invalid URL provided for platform '{platform}'")
            return None

        if platform not in self.config:
            self.logger.warning(f"Platform '{platform}' not found in config")
            return None

        platform_config = self.config[platform]
        content_selectors = platform_config.get("content_selectors", {})

        if not content_selectors:
            self.logger.warning(f"No content_selectors configured for platform '{platform}'")
            return None

        page = await self.browser_pool.get_page()

        try:
            self.logger.debug(f"Fetching content from {url} (platform: {platform})")

            # Skip Sogou redirect URLs - they should have been resolved earlier
            if "sogou.com/link" in url:
                self.logger.warning(
                    f"Skipping Sogou redirect URL (should have been resolved): {url}"
                )
                return None

            # Navigate to URL
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

            # Wait a bit for page to stabilize before checking for anti-crawler
            await asyncio.sleep(0.5)

            # Check for anti-crawler responses before attempting content extraction
            try:
                detection = await self.detector.detect(page, platform=platform)
                if detection.detected:
                    self.logger.warning(
                        f"Anti-crawler detected on {url}: {detection.detection_type.value}, "
                        f"confidence: {detection.confidence}, details: {detection.details}"
                    )
                    if detection.detection_type in [
                        DetectionType.LOGIN_WALL,
                        DetectionType.CAPTCHA,
                        DetectionType.IP_BAN,
                    ]:
                        self.logger.warning(
                            f"Skipping content extraction due to {detection.detection_type.value}"
                        )
                        return None
            except Exception as e:
                # If detection fails (e.g., page still loading), log and continue
                self.logger.debug(f"Anti-crawler detection failed (may be transient): {e}")

            # Remove interference elements first
            elements_to_remove = content_selectors.get("elements_to_remove", [])
            for selector in elements_to_remove:
                try:
                    await page.evaluate(
                        f"""
                        document.querySelectorAll('{selector}').forEach(el => el.remove())
                        """
                    )
                except Exception as e:
                    self.logger.debug(f"Failed to remove element '{selector}': {e}")

            # Extract main content using fallback selectors
            main_content_selectors = content_selectors.get("main_content", [])
            content = None

            for selector in main_content_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        content = await element.inner_text()
                        if content and content.strip():
                            self.logger.debug(
                                f"Successfully extracted content using selector '{selector}'"
                            )
                            break
                except Exception as e:
                    self.logger.debug(f"Selector '{selector}' failed: {e}, trying next")
                    continue

            if not content or not content.strip():
                self.logger.warning(f"No content extracted from {url}")
                return None

            # Clean and return content
            return self._clean_content(content)

        except Exception as e:
            self.logger.error(f"Failed to fetch content from {url}: {e}", exc_info=True)
            return None
        finally:
            await page.close()

    def _clean_content(self, content: str) -> str:
        """
        Clean extracted content.

        Removes excessive whitespace and normalizes formatting.

        Args:
            content: Raw extracted content

        Returns:
            Cleaned content string
        """
        if not content:
            return ""

        # Remove excessive newlines (more than 2 consecutive)
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Remove excessive spaces (more than 2 consecutive)
        content = re.sub(r" {2,}", " ", content)

        return content.strip()

    @staticmethod
    def get_url_hash(url: str) -> str:
        """
        Generate hash for URL (for caching).

        Args:
            url: URL string

        Returns:
            MD5 hash of URL
        """
        return hashlib.md5(url.encode()).hexdigest()
