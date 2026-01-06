"""
Base platform searcher abstract class.

This module defines the abstract base class that all platform searchers must inherit.
It provides a standard interface and common utility methods for platform-specific implementations.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from core.browser_pool import BrowserPool
from playwright.async_api import Page, ElementHandle
import re
import urllib.request
import urllib.error


class BasePlatformSearcher(ABC):
    """
    Base class for platform searchers.

    All platform searchers must inherit this class and implement the abstract methods.
    This class provides common functionality and defines the standard interface.

    Attributes:
        browser_pool: BrowserPool instance for getting pages
        config: Platform-specific configuration dictionary
    """

    def __init__(self, browser_pool: BrowserPool) -> None:
        """
        Initialize base searcher.

        Args:
            browser_pool: BrowserPool instance for managing browser pages
        """
        self.browser_pool = browser_pool
        self.config: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def _load_config(self) -> Dict[str, Any]:
        """
        Load platform configuration (from YAML or code).

        This method should load platform-specific configuration such as:
        - Base URL
        - CSS selectors
        - URL parameters
        - Time filter mappings

        Returns:
            Dictionary containing platform configuration
        """
        pass

    @abstractmethod
    async def search(
        self, query: str, max_results: int = 10, **kwargs: Any
    ) -> List[Dict[str, str]]:
        """
        Execute search on the platform.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            **kwargs: Additional platform-specific parameters (e.g., time_filter)

        Returns:
            List of search result dictionaries, each containing:
            - title: Article title
            - url: Article URL
            - source: Source platform name
            - date: Publication date (optional)
            - snippet: Article snippet/description (optional)
        """
        pass

    @abstractmethod
    async def _extract_item(self, element: ElementHandle, index: int) -> Optional[Dict[str, str]]:
        """
        Extract a single result item from DOM element.

        Args:
            element: Playwright ElementHandle representing a search result
            index: Index of the element in the results list

        Returns:
            Dictionary containing result item data, or None if extraction fails
        """
        pass

    def _sanitize_query(self, query: str) -> str:
        """
        Sanitize search query.

        Removes potentially dangerous characters and limits length.

        Args:
            query: Raw search query string

        Returns:
            Sanitized query string
        """
        if not query:
            return ""

        # Remove potentially dangerous characters
        query = re.sub(r'[<>"\']', "", query)

        # Strip whitespace and limit length
        query = query.strip()[:100]

        return query

    def _clean_text(self, text: str) -> str:
        """
        Clean text content.

        Removes HTML tags and normalizes whitespace.

        Args:
            text: Raw text content (may contain HTML)

        Returns:
            Cleaned text content
        """
        if not text:
            return ""

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    async def _parse_results(self, page: Page, max_results: int) -> List[Dict[str, str]]:
        """
        Generic result parsing method.

        This method implements the multiple selector strategy:
        - Tries selectors in order of priority
        - Uses the first selector that finds elements
        - Extracts results using platform-specific _extract_item method

        Args:
            page: Playwright Page instance
            max_results: Maximum number of results to extract

        Returns:
            List of extracted result dictionaries
        """
        results: List[Dict[str, str]] = []

        # Get selectors from config (multiple fallback selectors)
        selectors = self.config.get("selectors", {}).get("article_list", [])

        if not selectors:
            return results

        # Try each selector in order until we find elements
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                if elements:
                    # Extract results using platform-specific method
                    for i, element in enumerate(elements[:max_results]):
                        item = await self._extract_item(element, i)
                        if item:
                            results.append(item)
                    break
            except Exception:
                # If selector fails, try next one
                continue

        # Return limited results
        return results[:max_results]

    async def _parse_results_with_pagination(
        self, page: Page, max_results: int, results_per_page: int = 10
    ) -> List[Dict[str, str]]:
        """
        Parse results with pagination support.

        This method handles pagination automatically when max_results > results_per_page.
        It will navigate through pages until enough results are collected
        or no more pages are available.

        Args:
            page: Playwright Page instance
            max_results: Maximum number of results to collect
            results_per_page: Number of results per page (default: 10)

        Returns:
            List of extracted result dictionaries
        """
        all_results: List[Dict[str, str]] = []
        current_page_num = 1
        max_pages = (max_results + results_per_page - 1) // results_per_page  # Ceiling division

        while len(all_results) < max_results and current_page_num <= max_pages:
            # Parse current page
            page_results = await self._parse_results(page, results_per_page)
            all_results.extend(page_results)

            # Check if we have enough results
            if len(all_results) >= max_results:
                break

            # Try to find and click next page button
            next_page_selector = self.config.get("selectors", {}).get("next_page")
            if not next_page_selector:
                # No pagination configured, return what we have
                break

            try:
                # Find next page button
                next_button = await page.query_selector(next_page_selector)
                if not next_button:
                    # No next page available
                    break

                # Check if button is disabled or has specific disabled class
                is_disabled = await next_button.get_attribute("disabled")
                class_name = await next_button.get_attribute("class") or ""
                if is_disabled or "disabled" in class_name.lower() or "nop" in class_name.lower():
                    # Button is disabled, no more pages
                    break

                # Click next page
                await next_button.click()

                # Wait for new page to load
                await page.wait_for_load_state("domcontentloaded", timeout=5000)

                # Wait for results to load on new page
                selectors = self.config.get("selectors", {}).get("article_list", [])
                page_loaded = False
                for selector in selectors:
                    try:
                        await page.wait_for_selector(selector, timeout=2000, state="visible")
                        page_loaded = True
                        break
                    except Exception:
                        continue

                if not page_loaded:
                    # New page didn't load properly, return what we have
                    break

                current_page_num += 1

            except Exception:
                # Pagination failed (button not found, click failed, etc.)
                # Return what we have collected so far
                break

        # Return limited results
        return all_results[:max_results]

    def _resolve_url_base(self, link: str, base_url: str, domain: str) -> str:
        """
        Resolve relative URL to absolute URL (base implementation).

        Args:
            link: URL string (may be relative or absolute)
            base_url: Base URL for the platform
            domain: Domain name for the platform (e.g., "weixin.sogou.com")

        Returns:
            Absolute URL string
        """
        if not link:
            return ""

        # If already absolute URL, return as is
        if link.startswith("http://") or link.startswith("https://"):
            return link

        # If relative URL, make it absolute
        if link.startswith("/"):
            return f"https://{domain}{link}"

        # If relative path without leading slash, prepend base URL
        return f"{base_url}/{link}"

    def _extract_final_url_from_sogou_redirect(
        self, sogou_url: str, target_domains: List[str]
    ) -> Optional[str]:
        """
        Extract final URL from Sogou redirect link using HTTP request and HTML parsing.

        Sogou uses JavaScript redirects. The real URL is in the HTML response:
        - JavaScript: window.location.replace("真实URL")
        - Meta Refresh: <META http-equiv="refresh" content="0;URL='真实URL'">

        This method works for both Weixin and Zhihu platforms.

        Args:
            sogou_url: Sogou redirect URL (e.g., https://weixin.sogou.com/link?url=...)
            target_domains: List of target domain patterns to validate
                (e.g., ["mp.weixin.qq.com", "zhihu.com"])

        Returns:
            Final URL if extraction succeeds, None otherwise
        """
        if not sogou_url:
            return None

        # Validate it's a Sogou redirect link
        if "sogou.com/link" not in sogou_url:
            return None

        # Note: URLs ending with ".." are valid Sogou redirect links, not truncated
        # The ".." is part of Sogou's URL encoding scheme, not an indication of truncation

        try:
            # Create request with proper headers
            req = urllib.request.Request(
                sogou_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Referer": sogou_url.split("/link")[0] if "/link" in sogou_url else sogou_url,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
            )

            # Send HTTP GET request (do not follow redirects)
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status != 200:
                    self.logger.debug(f"Sogou redirect returned non-200 status: {response.status}")
                    return None

                # Read HTML content
                html = response.read().decode("utf-8", errors="ignore")

                # Check if we got redirected to Sogou homepage (indicates expired/invalid link)
                if "搜狗搜索引擎" in html or "sogou.com" in html and len(html) > 10000:
                    self.logger.debug(
                        f"Sogou redirect returned homepage "
                        f"(likely expired/invalid link): {sogou_url[:80]}..."
                    )
                    return None

                # Method 1: Extract from JavaScript window.location.replace
                js_pattern = r'window\.location\.replace\("([^"]+)"\)'
                js_match = re.search(js_pattern, html)
                if js_match:
                    real_url = js_match.group(1)
                    # Validate it contains target domain
                    if any(domain in real_url for domain in target_domains):
                        self.logger.debug(f"Extracted final URL from JavaScript: {real_url}")
                        return real_url
                    else:
                        self.logger.debug(f"Extracted URL doesn't match target domains: {real_url}")

                # Method 2: Extract from Meta Refresh tag
                meta_pattern = r"URL=['\"]([^'\"]+)['\"]"
                meta_match = re.search(meta_pattern, html, re.IGNORECASE)
                if meta_match:
                    real_url = meta_match.group(1)
                    # Validate it contains target domain
                    if any(domain in real_url for domain in target_domains):
                        self.logger.debug(f"Extracted final URL from Meta Refresh: {real_url}")
                        return real_url
                    else:
                        self.logger.debug(
                            f"Extracted URL (meta) doesn't match target domains: {real_url}"
                        )

                # Log HTML preview for debugging
                html_preview = html[:500] if len(html) < 500 else html[:500] + "..."
                self.logger.warning(
                    f"Could not extract target URL from Sogou redirect. "
                    f"HTML preview: {html_preview}"
                )
                return None

        except urllib.error.HTTPError as e:
            self.logger.debug(
                f"HTTP error when accessing Sogou redirect: {sogou_url}, status: {e.code}"
            )
            return None
        except urllib.error.URLError as e:
            self.logger.debug(
                f"URL error when accessing Sogou redirect: {sogou_url}, error: {e.reason}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Exception when extracting URL from Sogou redirect: {sogou_url}, error: {e}"
            )
            return None

    async def _resolve_final_urls_batch(
        self, results: List[Dict[str, str]], target_domains: List[str]
    ) -> List[Dict[str, str]]:
        """
        Resolve final URLs from Sogou redirect links in batch.

        This method processes all results in a single page to improve performance.
        It follows redirects to get the final article URLs.

        Args:
            results: List of result dictionaries with URLs
            target_domains: List of target domain patterns to check for
                (e.g., ["mp.weixin.qq.com", "zhihu.com"])

        Returns:
            List of result dictionaries with resolved final URLs
        """
        if not results:
            return results

        # Filter results that need URL resolution (Sogou redirect links)
        # Note: Sogou redirect links use www.sogou.com/link for both Weixin and Zhihu
        redirect_urls = []
        redirect_indices = []
        for i, result in enumerate(results):
            url = result.get("url", "")
            if url and "sogou.com/link" in url:
                redirect_urls.append(url)
                redirect_indices.append(i)
                self.logger.debug(f"Found redirect URL {i}: {url}")

        if not redirect_urls:
            # No redirect links to resolve
            self.logger.debug("No redirect URLs found, skipping resolution")
            return results

        self.logger.info(
            f"Resolving {len(redirect_urls)} redirect URLs to target domains: {target_domains}"
        )

        # Use a single page to resolve all redirects
        page = None
        try:
            page = await self.browser_pool.get_page()
            page.set_default_timeout(3000)  # Short timeout for redirects

            resolved_urls = []
            for idx, redirect_url in enumerate(redirect_urls):
                try:
                    self.logger.debug(
                        f"Processing redirect {idx+1}/{len(redirect_urls)}: {redirect_url}"
                    )

                    # Set platform-specific Referer based on URL
                    if "zhihu.sogou.com" in redirect_url:
                        referer_url = "https://zhihu.sogou.com/"
                    elif "weixin.sogou.com" in redirect_url:
                        referer_url = "https://weixin.sogou.com/"
                    else:
                        referer_url = (
                            redirect_url.split("/link")[0]
                            if "/link" in redirect_url
                            else redirect_url
                        )

                    self.logger.debug(f"  使用 Referer: {referer_url}")

                    # Set extra HTTP headers to simulate coming from search results page
                    await page.set_extra_http_headers(
                        {
                            "Referer": referer_url,
                            "User-Agent": (
                                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/120.0.0.0 Safari/537.36"
                            ),
                        }
                    )

                    # Access the redirect URL and wait for navigation
                    # Use networkidle to wait for JavaScript redirects
                    try:
                        response = await page.goto(
                            redirect_url, wait_until="networkidle", timeout=10000
                        )
                    except Exception as e:
                        self.logger.debug(
                            f"  Goto failed with networkidle, trying domcontentloaded: {e}"
                        )
                        # If networkidle fails, try with domcontentloaded
                        response = await page.goto(
                            redirect_url, wait_until="domcontentloaded", timeout=10000
                        )

                    initial_url = page.url
                    self.logger.debug(f"  Initial URL after goto: {initial_url}")
                    self.logger.debug(
                        f"  Response status: {response.status if response else 'None'}"
                    )

                    # Wait for redirect to complete
                    # For some platforms, we need to wait longer or click the link
                    max_wait = 5.0  # Maximum wait time in seconds (increased from 3)
                    wait_interval = 0.3  # Check every 0.3 seconds (more frequent checks)
                    waited = 0.0

                    while waited < max_wait:
                        await page.wait_for_timeout(int(wait_interval * 1000))
                        current_url = page.url

                        # Log progress every 1 second
                        if int(waited) % 1 == 0 and waited > 0:
                            current_preview = (
                                current_url[:80] + "..." if len(current_url) > 80 else current_url
                            )
                            self.logger.debug(
                                f"  等待跳转... {waited:.1f}s, 当前URL: {current_preview}"
                            )

                        if current_url != initial_url:
                            # URL changed, redirect happened
                            self.logger.debug(f"  URL changed during wait: {current_url}")
                            break
                        waited += wait_interval

                    # If still on Sogou page, try clicking the link
                    if "sogou.com" in page.url:
                        self.logger.debug(
                            "  Still on Sogou page, trying to find and click target link"
                        )
                        try:
                            # Try multiple strategies to find the target link
                            link_element = None

                            # Strategy 1: Direct href matching for target domains
                            domain_selectors = ", ".join(
                                [f"a[href*='{domain}']" for domain in target_domains]
                            )
                            link_element = await page.query_selector(domain_selectors)

                            # Strategy 2: If not found, try common link patterns
                            if not link_element:
                                common_selectors = [
                                    "a[href^='http']",  # Any absolute link
                                    ".link",  # Common class name
                                    "a.news-title",  # News title link
                                    "a.title",  # Title link
                                ]
                                for selector in common_selectors:
                                    link_element = await page.query_selector(selector)
                                    if link_element:
                                        href = await link_element.get_attribute("href")
                                        if href and any(
                                            domain in href for domain in target_domains
                                        ):
                                            break
                                        link_element = None

                            if link_element:
                                self.logger.debug("  Found target link element, clicking...")
                                # Click the link and wait for navigation
                                async with page.expect_navigation(
                                    timeout=5000, wait_until="networkidle"
                                ):
                                    await link_element.click()
                                await page.wait_for_timeout(1000)
                                self.logger.debug(f"  After click, URL: {page.url}")
                            else:
                                self.logger.debug("  No target link element found on page")
                        except Exception as e:
                            # Clicking failed, continue with current URL
                            self.logger.debug(f"  Clicking failed: {e}")

                    # Get the final URL after potential redirects
                    final_url = page.url
                    self.logger.debug(f"  Final URL: {final_url}")

                    # Check if we got redirected to any target domain
                    redirected = False
                    for target_domain in target_domains:
                        if target_domain in final_url and "sogou.com" not in final_url:
                            self.logger.info(
                                f"  ✓ Successfully resolved to {target_domain}: {final_url}"
                            )
                            resolved_urls.append(final_url)
                            redirected = True
                            break

                    if not redirected:
                        # Redirect didn't go to target, use original URL
                        self.logger.warning(
                            f"  ✗ Failed to resolve to target domain. "
                            f"Final URL: {final_url}, using original: {redirect_url}"
                        )
                        resolved_urls.append(redirect_url)

                except Exception as e:
                    # If redirect fails, use original URL
                    self.logger.warning(
                        f"  ✗ Exception during redirect resolution: {e}, "
                        f"using original: {redirect_url}"
                    )
                    resolved_urls.append(redirect_url)

            # Update results with resolved URLs
            for i, resolved_url in zip(redirect_indices, resolved_urls):
                results[i]["url"] = resolved_url

        except Exception:
            # If batch processing fails, return original results
            pass
        finally:
            if page:
                await page.close()

        return results
