"""
Integration tests for GoogleSearcher.

These tests verify the actual search functionality by making real requests
to the Google Custom Search API. They test:
- Basic search functionality
- Pagination support
- Result format and structure
- Error handling
- Content fetching integration

Note: These tests require API credentials to be set:
    - APIKEY_GOOGLE_CUSTOM_SEARCH
    - APIKEY_GOOGLE_SEARCH_ID

If credentials are not available, tests will be skipped.
"""

import os
import pytest
from core.browser_pool import BrowserPool
from core.search_manager import UnifiedSearchManager
from platforms.google_searcher import GoogleSearcher


# Check if credentials are available
GOOGLE_API_KEY = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
GOOGLE_SEARCH_ID = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
HAS_CREDENTIALS = bool(GOOGLE_API_KEY and GOOGLE_SEARCH_ID)

# Skip all tests if credentials are not available
pytestmark = pytest.mark.skipif(
    not HAS_CREDENTIALS,
    reason="Google API credentials not set (APIKEY_GOOGLE_CUSTOM_SEARCH, APIKEY_GOOGLE_SEARCH_ID)",
)


class TestGoogleSearchIntegration:
    """Integration test suite for GoogleSearcher."""

    @pytest.fixture
    async def browser_pool(self) -> BrowserPool:
        """Create and initialize browser pool."""
        pool = BrowserPool()
        await pool.init()
        yield pool
        await pool.close()

    @pytest.fixture
    def searcher(self, browser_pool: BrowserPool) -> GoogleSearcher:
        """Create GoogleSearcher instance."""
        return GoogleSearcher(browser_pool)

    @pytest.fixture
    def manager(self, browser_pool: BrowserPool) -> UnifiedSearchManager:
        """Create UnifiedSearchManager with GoogleSearcher registered."""
        manager = UnifiedSearchManager()
        searcher = GoogleSearcher(browser_pool)
        manager.register_platform("google", searcher)
        return manager

    @pytest.mark.asyncio
    async def test_basic_search(self, searcher: GoogleSearcher) -> None:
        """Test basic search functionality."""
        results = await searcher.search("Python programming", max_results=5)

        # Should return results
        assert isinstance(results, list)
        assert len(results) > 0
        assert len(results) <= 5

        # Each result should have required fields
        for result in results:
            assert isinstance(result, dict)
            assert "title" in result
            assert "url" in result
            assert "source" in result
            assert isinstance(result["title"], str)
            assert isinstance(result["url"], str)
            assert isinstance(result["source"], str)
            assert len(result["title"]) > 0
            assert len(result["url"]) > 0

    @pytest.mark.asyncio
    async def test_result_format(self, searcher: GoogleSearcher) -> None:
        """Test that results have correct format."""
        results = await searcher.search("machine learning", max_results=3)

        assert len(results) > 0

        for result in results:
            # Required fields
            assert "title" in result
            assert "url" in result
            assert "source" in result

            # Optional fields (may be empty)
            assert "date" in result
            assert "snippet" in result

            # Type checks
            assert isinstance(result["title"], str)
            assert isinstance(result["url"], str)
            assert isinstance(result["source"], str)
            assert isinstance(result["date"], str)
            assert isinstance(result["snippet"], str)

            # URL should be absolute
            assert result["url"].startswith("http://") or result["url"].startswith("https://")

            # Source should be from config
            assert result["source"] == "Google Custom Search"

    @pytest.mark.asyncio
    async def test_max_results_limit(self, searcher: GoogleSearcher) -> None:
        """Test that max_results limit is respected."""
        results = await searcher.search("Python", max_results=3)

        # Should not exceed max_results
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_pagination_with_more_than_10_results(self, searcher: GoogleSearcher) -> None:
        """Test pagination when requesting more than 10 results."""
        # Request 15 results (should trigger pagination - 2 API requests)
        results = await searcher.search("Python", max_results=15)

        # Should return up to 15 results
        assert len(results) <= 15
        assert len(results) >= 10, "Should have at least 10 results from first page"

        # All results should have valid structure
        for result in results:
            assert "title" in result
            assert "url" in result
            assert "source" in result

    @pytest.mark.asyncio
    async def test_pagination_with_30_results(self, searcher: GoogleSearcher) -> None:
        """Test pagination with maximum allowed results (30)."""
        # Request maximum allowed results (should trigger 3 API requests)
        results = await searcher.search("Python", max_results=30)

        # Should return up to 30 results
        assert len(results) <= 30
        assert len(results) >= 10, "Should have results from multiple pages"

        # All results should have valid structure
        for result in results:
            assert "title" in result
            assert "url" in result
            assert "source" in result

    @pytest.mark.asyncio
    async def test_empty_query(self, searcher: GoogleSearcher) -> None:
        """Test handling of empty query."""
        results = await searcher.search("", max_results=5)

        # Should return empty list for empty query
        assert results == []

    @pytest.mark.asyncio
    async def test_special_characters_in_query(self, searcher: GoogleSearcher) -> None:
        """Test handling of special characters in query."""
        # Query with special characters should be sanitized
        results = await searcher.search('Python "tutorial" <script>', max_results=5)

        # Should not crash, may return results or empty list
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_via_manager(self, manager: UnifiedSearchManager) -> None:
        """Test search through UnifiedSearchManager."""
        results = await manager.search(
            platform="google",
            query="Python async programming",
            max_results=5,
            include_content=False,
        )

        assert isinstance(results, list)
        assert len(results) > 0

        for result in results:
            assert "title" in result
            assert "url" in result
            assert "source" in result

    @pytest.mark.asyncio
    async def test_search_with_content_fetching(self, manager: UnifiedSearchManager) -> None:
        """Test search with content fetching enabled."""
        results = await manager.search(
            platform="google",
            query="Python",
            max_results=3,
            include_content=True,
        )

        assert isinstance(results, list)
        assert len(results) > 0

        for result in results:
            assert "title" in result
            assert "url" in result
            assert "content" in result
            assert "content_status" in result

            # Content may be empty if fetch failed (due to captcha, etc.)
            # But snippet should still be available
            if not result.get("content"):
                assert result.get("snippet", ""), "Should have snippet even if content fetch failed"

    @pytest.mark.asyncio
    async def test_result_snippet_available(self, searcher: GoogleSearcher) -> None:
        """Test that snippet is available in results."""
        results = await searcher.search("Python", max_results=5)

        assert len(results) > 0

        # All results should have snippet (from Google API)
        for result in results:
            assert "snippet" in result
            assert isinstance(result["snippet"], str)
            # Snippet may be empty for some results, but field should exist

    @pytest.mark.asyncio
    async def test_result_date_extraction(self, searcher: GoogleSearcher) -> None:
        """Test that date is extracted when available."""
        results = await searcher.search("Python", max_results=10)

        assert len(results) > 0

        # Date field should exist (may be empty if not available)
        for result in results:
            assert "date" in result
            assert isinstance(result["date"], str)

    @pytest.mark.asyncio
    async def test_max_results_upper_limit(self, searcher: GoogleSearcher) -> None:
        """Test that max_results cannot exceed platform limit (30)."""
        # Request more than 30 results
        results = await searcher.search("Python", max_results=50)

        # Should be capped at 30
        assert len(results) <= 30
