"""
Unit tests for BasePlatformSearcher.

Tests cover:
- Abstract class interface
- Utility methods (sanitize_query, clean_text)
- Result parsing logic
"""

import pytest
from typing import List, Dict, Optional, Any
from core.base_searcher import BasePlatformSearcher
from core.browser_pool import BrowserPool
from playwright.async_api import ElementHandle


class MockPlatformSearcher(BasePlatformSearcher):
    """Mock implementation of BasePlatformSearcher for testing."""

    def _load_config(self) -> Dict[str, Any]:
        """Load mock configuration."""
        return {"base_url": "https://example.com", "selectors": {"article_list": [".result-item"]}}

    async def search(
        self, query: str, max_results: int = 10, **kwargs: Any
    ) -> List[Dict[str, str]]:
        """Mock search implementation."""
        return [
            {
                "title": "Test Article",
                "url": "https://example.com/article",
                "source": "Test Platform",
            }
        ]

    async def _extract_item(self, element: ElementHandle, index: int) -> Optional[Dict[str, str]]:
        """Mock extract implementation."""
        return {
            "title": f"Article {index}",
            "url": f"https://example.com/article{index}",
            "source": "Test Platform",
        }


class TestBasePlatformSearcher:
    """Test suite for BasePlatformSearcher."""

    def test_is_abstract_class(self) -> None:
        """Test that BasePlatformSearcher is an abstract class."""
        # Should not be able to instantiate directly
        with pytest.raises(TypeError):
            BasePlatformSearcher(BrowserPool())  # type: ignore

    def test_can_instantiate_subclass(self) -> None:
        """Test that subclasses can be instantiated."""
        pool = BrowserPool()
        searcher = MockPlatformSearcher(pool)
        assert searcher is not None
        assert searcher.browser_pool == pool
        assert isinstance(searcher.config, dict)

    def test_sanitize_query(self) -> None:
        """Test query sanitization."""
        pool = BrowserPool()
        searcher = MockPlatformSearcher(pool)

        # Test normal query
        assert searcher._sanitize_query("Python tutorial") == "Python tutorial"

        # Test with dangerous characters (removes < > " ' characters)
        query_with_xss = 'Python <script>alert("xss")</script>'
        expected = "Python scriptalert(xss)/script"
        assert searcher._sanitize_query(query_with_xss) == expected

        # Test with quotes
        assert searcher._sanitize_query('Python "tutorial"') == "Python tutorial"

        # Test empty query
        assert searcher._sanitize_query("") == ""

        # Test long query (should be truncated)
        long_query = "a" * 200
        result = searcher._sanitize_query(long_query)
        assert len(result) == 100

        # Test whitespace
        assert searcher._sanitize_query("  Python  tutorial  ") == "Python  tutorial"

    def test_clean_text(self) -> None:
        """Test text cleaning."""
        pool = BrowserPool()
        searcher = MockPlatformSearcher(pool)

        # Test normal text
        assert searcher._clean_text("Hello World") == "Hello World"

        # Test with HTML tags
        assert searcher._clean_text("<p>Hello <b>World</b></p>") == "Hello World"

        # Test with multiple spaces
        assert searcher._clean_text("Hello    World") == "Hello World"

        # Test empty text
        assert searcher._clean_text("") == ""

        # Test None (should return empty string)
        assert searcher._clean_text(None) == ""  # type: ignore

        # Test with newlines
        assert searcher._clean_text("Hello\n\nWorld") == "Hello World"

    @pytest.mark.asyncio
    async def test_parse_results_empty_selectors(self) -> None:
        """Test parse_results with empty selectors."""
        pool = BrowserPool()
        searcher = MockPlatformSearcher(pool)
        searcher.config = {"selectors": {"article_list": []}}

        # Mock page (we won't actually use it since selectors are empty)
        from unittest.mock import MagicMock

        page = MagicMock()

        results = await searcher._parse_results(page, max_results=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_parse_results_no_selectors_config(self) -> None:
        """Test parse_results with no selectors in config."""
        pool = BrowserPool()
        searcher = MockPlatformSearcher(pool)
        searcher.config = {}

        from unittest.mock import MagicMock

        page = MagicMock()

        results = await searcher._parse_results(page, max_results=10)
        assert results == []

    def test_abstract_methods_required(self) -> None:
        """Test that abstract methods must be implemented."""

        # Create a class that doesn't implement _load_config (required abstract method)
        class IncompleteSearcher1(BasePlatformSearcher):
            async def search(
                self, query: str, max_results: int = 10, **kwargs: Any
            ) -> List[Dict[str, str]]:
                return []

            # Missing _load_config implementation

        pool = BrowserPool()
        with pytest.raises(TypeError):
            IncompleteSearcher1(pool)  # type: ignore

        # Create a class that doesn't implement search (required abstract method)
        class IncompleteSearcher2(BasePlatformSearcher):
            def _load_config(self) -> Dict[str, Any]:
                return {}

            # Missing search implementation

        with pytest.raises(TypeError):
            IncompleteSearcher2(pool)  # type: ignore

        # _extract_item is now optional (has default implementation)
        # So a class implementing only _load_config and search should work
        class CompleteSearcher(BasePlatformSearcher):
            def _load_config(self) -> Dict[str, Any]:
                return {}

            async def search(
                self, query: str, max_results: int = 10, **kwargs: Any
            ) -> List[Dict[str, str]]:
                return []

            # _extract_item not implemented - should work (uses default)

        # Should not raise TypeError
        searcher = CompleteSearcher(pool)
        assert searcher is not None
