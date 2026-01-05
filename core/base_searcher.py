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
