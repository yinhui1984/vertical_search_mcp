"""
Base platform searcher abstract class.

This module defines the abstract base class that all platform searchers must inherit.
It provides a standard interface and common utility methods for platform-specific implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from core.browser_pool import BrowserPool
from core.url_resolver import URLResolver
from core.logger import get_logger
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
        self.logger = get_logger(f"vertical_search.{self.__class__.__name__.lower()}")

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
            **kwargs: Additional platform-specific parameters

        Returns:
            List of search result dictionaries, each containing:
            - title: Article title
            - url: Article URL
            - source: Source platform name
            - date: Publication date (optional)
            - snippet: Article snippet/description (optional)
        """
        pass

    async def _extract_item(self, element: ElementHandle, index: int) -> Optional[Dict[str, str]]:
        """
        Extract a single result item from DOM element.

        This method is used by browser-based searchers to extract results from DOM.
        API-based searchers can use the default implementation (returns None).

        Args:
            element: Playwright ElementHandle representing a search result
            index: Index of the element in the results list

        Returns:
            Dictionary containing result item data, or None if not applicable
        """
        return None

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
                js_patterns = [
                    r'window\.location\.replace\("([^"]+)"\)',
                    r'window\.location\s*=\s*"([^"]+)"',
                    r'location\.replace\("([^"]+)"\)',
                    r'location\.href\s*=\s*"([^"]+)"',
                ]
                for js_pattern in js_patterns:
                    js_match = re.search(js_pattern, html)
                    if js_match:
                        real_url = js_match.group(1)
                        # Decode URL if needed
                        if "\\u" in real_url:
                            real_url = real_url.encode().decode("unicode_escape")
                        # Validate it contains target domain
                        if any(domain in real_url for domain in target_domains):
                            self.logger.debug(f"Extracted final URL from JavaScript: {real_url}")
                            return real_url
                        else:
                            self.logger.debug(
                                f"Extracted URL doesn't match target domains: {real_url}"
                            )

                # Method 2: Extract from Meta Refresh tag
                meta_patterns = [
                    r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+url=["\']([^"\']+)["\']',
                    r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^;]+;\s*url=["\']([^"\']+)["\']',
                    r"URL=['\"]([^'\"]+)['\"]",
                ]
                for meta_pattern in meta_patterns:
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

                # Method 3: Try to find direct links in HTML
                link_patterns = [
                    r'<a[^>]+href=["\']([^"\']*mp\.weixin\.qq\.com[^"\']*)["\']',
                    r'<a[^>]+href=["\']([^"\']*zhihu\.com[^"\']*)["\']',
                ]
                for link_pattern in link_patterns:
                    link_match = re.search(link_pattern, html, re.IGNORECASE)
                    if link_match:
                        real_url = link_match.group(1)
                        if any(domain in real_url for domain in target_domains):
                            self.logger.debug(f"Extracted final URL from link: {real_url}")
                            return real_url

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
        Resolve final URLs from Sogou redirect links in batch using CDP.

        This method uses Chrome DevTools Protocol (CDP) to track network traffic
        and redirects, extracting the final target URLs from Sogou redirect links.

        If CDP resolution fails, it falls back to the HTTP-based method.

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

        # Try CDP-based resolution first
        try:
            resolver = URLResolver(target_domains=target_domains, redirect_timeout=5.0)
            page = await self.browser_pool.get_page()

            try:
                # Resolve URLs using CDP
                resolved_urls = await resolver.resolve_urls_batch(page, redirect_urls)

                # Check if resolution was successful
                success_count = sum(
                    1
                    for url in resolved_urls
                    if url and any(domain in url for domain in target_domains)
                )

                if success_count > 0:
                    # CDP resolution succeeded for at least some URLs
                    self.logger.info(
                        f"CDP resolution succeeded for {success_count}/{len(redirect_urls)} URLs"
                    )

                    # Update results with resolved URLs
                    for i, resolved_url in zip(redirect_indices, resolved_urls):
                        if resolved_url:
                            results[i]["url"] = resolved_url
                            self.logger.debug(f"Resolved URL {i}: {resolved_url}")
                        else:
                            # Try fallback for failed URLs
                            original_url = redirect_urls[redirect_indices.index(i)]
                            self.logger.debug(f"CDP failed for URL {i}, trying fallback")
                            fallback_url = self._extract_final_url_from_sogou_redirect(
                                original_url, target_domains
                            )
                            if fallback_url:
                                results[i]["url"] = fallback_url
                            else:
                                self.logger.warning(
                                    f"Both CDP and fallback failed for URL {i}, keeping original"
                                )

                    await page.close()
                    return results
                else:
                    # CDP resolution failed for all URLs, try fallback
                    self.logger.warning(
                        "CDP resolution failed for all URLs, falling back to HTTP method"
                    )
                    await page.close()
            except Exception as e:
                self.logger.warning(f"CDP resolution error: {e}, falling back to HTTP method")
                if page:
                    await page.close()

        except Exception as e:
            self.logger.warning(f"CDP resolver initialization error: {e}, using fallback")

        # Fallback to HTTP-based method
        self.logger.info("Using HTTP-based URL resolution fallback")
        for i, redirect_url in zip(redirect_indices, redirect_urls):
            try:
                fallback_url = self._extract_final_url_from_sogou_redirect(
                    redirect_url, target_domains
                )
                if fallback_url:
                    results[i]["url"] = fallback_url
                    self.logger.debug(f"Fallback resolved URL {i}: {fallback_url}")
                else:
                    self.logger.warning(f"Fallback failed for URL {i}, keeping original")
            except Exception as e:
                self.logger.warning(f"Fallback error for URL {i}: {e}")

        return results
