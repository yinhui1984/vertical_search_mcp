"""
Zhihu platform searcher.

This module implements the Zhihu search functionality using Sogou search.
It inherits from BasePlatformSearcher and implements platform-specific search logic.
"""

import os
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
                return await self._parse_results_with_pagination(
                    page, max_results, RESULTS_PER_PAGE
                )
            else:
                return await self._parse_results(page, max_results)

        except Exception:
            return []
        finally:
            await page.close()

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
            link = await title_elem.get_attribute("href")

            if not title or not link:
                return None

            # Clean title
            title = self._clean_text(title)

            # Resolve relative URLs to absolute URLs
            url = self._resolve_url(link)

            # Try to extract additional metadata from parent container
            snippet = ""
            date = ""

            try:
                # Find parent container (usually <li> or similar)
                parent_handle = await element.evaluate_handle("el => el.closest('li')")
                if parent_handle:
                    parent = parent_handle.as_element()
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

    def _resolve_url(self, link: str) -> str:
        """
        Resolve relative URL to absolute URL.

        Args:
            link: URL string (may be relative or absolute)

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
            domain = "https://zhihu.sogou.com"
            return domain + link

        # If relative path without leading slash, prepend base URL
        return f"{self.base_url}/{link}"
