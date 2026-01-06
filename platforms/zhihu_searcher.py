"""
Zhihu platform searcher.

This module implements the Zhihu search functionality using Sogou search.
It inherits from BasePlatformSearcher and implements platform-specific search logic.
"""

import os
import asyncio
import logging
import yaml
from typing import List, Dict, Optional, Any
from urllib.parse import urlencode
from core.base_searcher import BasePlatformSearcher
from core.browser_pool import BrowserPool
from playwright.async_api import ElementHandle


class ZhihuSearcher(BasePlatformSearcher):
    """
    Zhihu platform searcher.

    This searcher implements Zhihu search using Sogou search engine.
    It uses the browser pool for page management and loads configuration from YAML.
    """

    def __init__(self, browser_pool: BrowserPool) -> None:
        """
        Initialize Zhihu searcher.

        Args:
            browser_pool: BrowserPool instance for managing browser pages
        """
        super().__init__(browser_pool)
        self.config = self._load_config()
        self.base_url = self.config.get("base_url", "https://zhihu.sogou.com/zhihu")
        self.logger = logging.getLogger(__name__)

    def _load_config(self) -> Dict[str, Any]:
        """
        Load platform configuration from YAML file.

        Returns:
            Dictionary containing platform configuration

        Raises:
            FileNotFoundError: If config file doesn't exist
            KeyError: If 'zhihu' section is missing in config
        """
        # Get config file path relative to project root
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config", "platforms.yaml"
        )

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            configs: Dict[str, Any] = yaml.safe_load(f) or {}

        if "zhihu" not in configs:
            raise KeyError("'zhihu' section not found in config file")

        return configs["zhihu"]  # type: ignore[no-any-return]

    async def search(
        self, query: str, max_results: int = 10, time_filter: Optional[str] = None, **kwargs: Any
    ) -> List[Dict[str, str]]:
        """
        Execute Zhihu search.

        This method:
        1. Sanitizes the query
        2. Builds the search URL with parameters
        3. Navigates to the search page
        4. Waits for results to load
        5. Parses and extracts results (with pagination if needed)

        Args:
            query: Search query string
            max_results: Maximum number of results to return (max: 30)
            time_filter: Optional time filter ('day', 'week', 'month', 'year')
            **kwargs: Additional parameters (not used currently)

        Returns:
            List of search result dictionaries, each containing:
            - title: Article title
            - url: Article URL
            - source: Source platform name
            - date: Publication date (if available)
            - snippet: Article snippet/description (if available)

        Raises:
            ValueError: If max_results > 30
        """
        # Validate max_results limit
        MAX_RESULTS_LIMIT = 30
        if max_results > MAX_RESULTS_LIMIT:
            raise ValueError(f"max_results cannot exceed {MAX_RESULTS_LIMIT}")

        # Sanitize query
        query = self._sanitize_query(query)
        if not query:
            return []

        # Build search URL
        params: Dict[str, str] = {
            "query": query,
            "type": self.config.get("url_params", {}).get("type", "2"),
            "ie": self.config.get("url_params", {}).get("ie", "utf8"),
        }

        # Add time filter if specified
        if time_filter:
            time_filters = self.config.get("time_filters", {})
            time_code = time_filters.get(time_filter)
            if time_code:
                params["tsn"] = time_code

        url = f"{self.base_url}?{urlencode(params)}"

        # Get page from browser pool
        page = await self.browser_pool.get_page()

        try:
            # Navigate to search page
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Wait for search results to load
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
                try:
                    first_selector = selectors[0] if selectors else None
                    if first_selector:
                        await page.wait_for_selector(first_selector, timeout=3000, state="visible")
                        page_loaded = True
                except Exception:
                    return []

            # Parse and extract results
            RESULTS_PER_PAGE = 10
            if max_results > RESULTS_PER_PAGE:
                results = await self._parse_results_with_pagination(
                    page, max_results, RESULTS_PER_PAGE
                )
            else:
                results = await self._parse_results(page, max_results)

            # Resolve Sogou redirect links to real URLs by clicking links on search results page
            # This is more reliable than accessing links directly (which may expire)
            target_domains = ["zhihu.com"]
            redirect_count = sum(1 for r in results if "sogou.com/link" in r.get("url", ""))

            if redirect_count > 0:
                self.logger.info(
                    f"Resolving {redirect_count} Sogou redirect URLs by clicking links on search page"
                )

                # Get all redirect URLs and their indices
                redirect_urls = [r["url"] for r in results if "sogou.com/link" in r.get("url", "")]
                redirect_indices = [
                    i for i, r in enumerate(results) if "sogou.com/link" in r.get("url", "")
                ]

                # Get all link elements from search results page
                selectors = self.config.get("selectors", {}).get("article_list", [])
                all_link_elements = []
                for selector in selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        if elements:
                            for element in elements:
                                link_elem = await element.query_selector("a")
                                if link_elem:
                                    all_link_elements.append(link_elem)
                            break
                    except Exception:
                        continue

                # Resolve URLs by clicking links on the search results page
                resolved_urls: List[Optional[str]] = []
                for idx, result_idx in enumerate(redirect_indices):
                    try:
                        self.logger.debug(
                            f"Resolving URL {idx + 1}/{len(redirect_indices)}: {redirect_urls[idx][:80]}..."
                        )

                        # Use the link element at the same index as the result
                        if result_idx < len(all_link_elements):
                            link_element = all_link_elements[result_idx]

                            # Click the link and wait for new page/tab to open
                            try:
                                async with page.context.expect_page(timeout=8000) as new_page_info:
                                    await link_element.click(
                                        modifiers=["Meta"]
                                    )  # Cmd+Click to open in new tab

                                new_page = await new_page_info.value

                                # Wait for page to navigate away from about:blank
                                # Try multiple wait strategies to ensure we get the final URL
                                try:
                                    # Wait for navigation to complete
                                    await new_page.wait_for_load_state("networkidle", timeout=15000)
                                except Exception:
                                    # If networkidle times out, try domcontentloaded
                                    try:
                                        await new_page.wait_for_load_state(
                                            "domcontentloaded", timeout=10000
                                        )
                                    except Exception:
                                        # If that also fails, wait a bit and check URL
                                        await asyncio.sleep(2)

                                # Wait for URL to change from about:blank
                                max_wait_attempts = 10
                                wait_interval = 0.5
                                new_page_url = new_page.url
                                for attempt in range(max_wait_attempts):
                                    if new_page_url != "about:blank" and new_page_url:
                                        break
                                    await asyncio.sleep(wait_interval)
                                    new_page_url = new_page.url

                                self.logger.info(f"New page opened with URL: {new_page_url}")

                                # Check if it's a target domain
                                if (
                                    any(domain in new_page_url for domain in target_domains)
                                    and "sogou.com" not in new_page_url
                                ):
                                    resolved_urls.append(new_page_url)
                                    self.logger.info(
                                        f"Successfully resolved URL {idx + 1}: {new_page_url}"
                                    )
                                    await new_page.close()
                                else:
                                    self.logger.warning(
                                        f"New page URL doesn't match target domain. URL: {new_page_url}, target domains: {target_domains}"
                                    )
                                    resolved_urls.append(None)
                                    await new_page.close()
                            except Exception as e:
                                self.logger.debug(f"Error clicking link {idx + 1}: {e}")
                                resolved_urls.append(None)
                        else:
                            self.logger.debug(
                                f"Could not find link element for result index {result_idx}"
                            )
                            resolved_urls.append(None)

                        # Small delay between clicks
                        if idx < len(redirect_urls) - 1:
                            await asyncio.sleep(0.5)

                    except Exception as e:
                        self.logger.warning(f"Error resolving URL {idx + 1}: {e}")
                        resolved_urls.append(None)

                # Update results with resolved URLs
                for i, resolved_url in zip(redirect_indices, resolved_urls):
                    if resolved_url:
                        results[i]["url"] = resolved_url
                        self.logger.debug(f"Updated result {i} with resolved URL")

            # Close the search page
            await page.close()

            return results

        except Exception as e:
            self.logger.error(f"Search error: {e}")
            return []
        finally:
            # Ensure page is closed (may already be closed in try block)
            try:
                if not page.is_closed():
                    await page.close()
            except Exception:
                pass

    async def _extract_item(self, element: ElementHandle, index: int) -> Optional[Dict[str, str]]:
        """
        Extract a single result item from DOM element.

        This method extracts:
        - Title and URL from the link element
        - Additional metadata from parent container (if available)

        Args:
            element: Playwright ElementHandle representing a search result
            index: Index of the element in the results list

        Returns:
            Dictionary containing result item data, or None if extraction fails
        """
        try:
            # Find the link element (usually an <a> tag)
            title_elem = await element.query_selector("a")
            if not title_elem:
                return None

            # Extract title and URL
            title = await title_elem.inner_text()

            # Try to get href using JavaScript to ensure we get the complete URL
            # Sometimes href attribute might be truncated
            link = await title_elem.evaluate("(el) => el.getAttribute('href')")
            if not link:
                # Fallback to get_attribute
                link = await title_elem.get_attribute("href")

            if not title or not link:
                return None

            # Clean title
            title = self._clean_text(title)

            # Resolve relative URLs to absolute URLs
            # Note: Sogou redirect links use www.sogou.com, not zhihu.sogou.com
            url = self._resolve_url_base(link, self.base_url, "www.sogou.com")

            # Try to extract additional metadata from parent container
            snippet = ""
            date = ""

            try:
                # Find parent container (usually <li> or similar)
                parent_handle = await element.evaluate_handle("el => el.closest('li')")
                if parent_handle:
                    parent = parent_handle.as_element()
                    if parent:
                        # Try to find snippet/description
                        snippet_elem = await parent.query_selector(
                            ".news-text, .text, .desc, .summary"
                        )
                        if snippet_elem is not None:
                            snippet_text = await snippet_elem.inner_text()
                            snippet = self._clean_text(snippet_text)

                        # Try to find date
                        date_elem = await parent.query_selector(
                            ".news-time, .time, .date, .pub-time"
                        )
                        if date_elem is not None:
                            date_text = await date_elem.inner_text()
                            date = self._clean_text(date_text)
            except Exception:
                pass

            return {
                "title": title,
                "url": url,
                "source": self.config.get("metadata", {}).get("display_name", "知乎"),
                "date": date,
                "snippet": snippet,
            }

        except Exception:
            return None
