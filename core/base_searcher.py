"""
Base platform searcher abstract class.

This module defines the abstract base class that all platform searchers must inherit.
It provides a standard interface and common utility methods for platform-specific implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from core.browser_pool import BrowserPool
from playwright.async_api import Page, ElementHandle
import re


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
        It will navigate through pages until enough results are collected or no more pages are available.

        Args:
            page: Playwright Page instance
            max_results: Maximum number of results to collect
            results_per_page: Number of results per page (default: 10 for Sogou)

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
