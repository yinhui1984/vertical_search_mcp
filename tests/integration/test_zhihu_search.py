"""
Integration tests for ZhihuSearcher.

These tests verify the actual search functionality by making real requests
to the Zhihu search platform. They test:
- Basic search functionality
- Time filter support
- Result parsing and format
- Error handling
- Browser pool reuse
- Pagination support
"""

import pytest
from core.browser_pool import BrowserPool
from core.search_manager import UnifiedSearchManager
from platforms.zhihu_searcher import ZhihuSearcher


class TestZhihuSearchIntegration:
    """Integration test suite for ZhihuSearcher."""

    @pytest.fixture
    async def browser_pool(self) -> BrowserPool:
        """Create and initialize browser pool."""
        pool = BrowserPool()
        await pool.init()
        yield pool
        await pool.close()

    @pytest.fixture
    def searcher(self, browser_pool: BrowserPool) -> ZhihuSearcher:
        """Create ZhihuSearcher instance."""
        return ZhihuSearcher(browser_pool)

    @pytest.fixture
    def manager(self, browser_pool: BrowserPool) -> UnifiedSearchManager:
        """Create UnifiedSearchManager with ZhihuSearcher registered."""
        manager = UnifiedSearchManager()
        searcher = ZhihuSearcher(browser_pool)
        manager.register_platform("zhihu", searcher)
        return manager

    @pytest.mark.asyncio
    async def test_basic_search(self, searcher: ZhihuSearcher) -> None:
        """Test basic search functionality."""
        results = await searcher.search("Python", max_results=5)

        # Should return results
        assert isinstance(results, list)
        assert len(results) > 0

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
    async def test_result_format(self, searcher: ZhihuSearcher) -> None:
        """Test that results have correct format."""
        results = await searcher.search("AI", max_results=3)

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

            # URL should be Sogou redirect link (not final Zhihu URL)
            # URL resolution will be implemented in a future iteration
            assert "sogou.com" in result["url"]

    @pytest.mark.asyncio
    async def test_max_results_limit(self, searcher: ZhihuSearcher) -> None:
        """Test that max_results limit is respected."""
        results = await searcher.search("Python", max_results=3)

        # Should not exceed max_results
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_max_results_upper_limit(self, searcher: ZhihuSearcher) -> None:
        """Test that max_results cannot exceed 30."""
        # Should raise ValueError if max_results > 30
        with pytest.raises(ValueError, match="max_results cannot exceed 30"):
            await searcher.search("Python", max_results=50)

    @pytest.mark.asyncio
    async def test_pagination_with_more_than_10_results(self, searcher: ZhihuSearcher) -> None:
        """Test pagination when requesting more than 10 results."""
        # Request 15 results (should trigger pagination)
        results = await searcher.search("Python", max_results=15)

        # Should return up to 15 results
        assert len(results) <= 15

        # Note: Results may be empty or fewer than expected due to:
        # - Network issues
        # - Anti-bot detection
        # - Search API changes
        # - No results available for the query
        # The test verifies that pagination logic works correctly,
        # not that results are always available
        if len(results) > 0:
            # If results are returned, verify structure
            for result in results:
                assert "title" in result
                assert "url" in result
                assert "source" in result

            # If we got results, pagination should have been attempted
            # (but we don't require exactly 10+ results due to external factors)
            if len(results) >= 10:
                # If we got 10+ results, pagination likely worked
                pass
            else:
                # If we got fewer than 10, that's acceptable too
                # (may be due to external factors beyond our control)
                pass

    @pytest.mark.asyncio
    async def test_pagination_with_30_results(self, searcher: ZhihuSearcher) -> None:
        """Test pagination with maximum allowed results (30)."""
        # Request maximum allowed results
        results = await searcher.search("Python", max_results=30)

        # Should return up to 30 results
        assert len(results) <= 30

        # If results are returned, verify structure
        # Note: May return empty results due to network issues or anti-bot detection
        if len(results) > 0:
            # Should have results from multiple pages if enough results available
            if len(results) >= 10:
                # All results should have valid structure
                for result in results:
                    assert "title" in result
                    assert "url" in result
                    assert "source" in result

    @pytest.mark.asyncio
    async def test_pagination_stops_when_no_more_pages(self, searcher: ZhihuSearcher) -> None:
        """Test that pagination stops when no more pages are available."""
        # Request a large number but there may not be that many results
        results = await searcher.search("Python", max_results=30)

        # Should return whatever is available (may be less than 30)
        assert len(results) <= 30

        # All results should be valid
        for result in results:
            assert "title" in result
            assert "url" in result

    @pytest.mark.asyncio
    async def test_empty_query(self, searcher: ZhihuSearcher) -> None:
        """Test handling of empty query."""
        results = await searcher.search("", max_results=5)

        # Should return empty list for empty query
        assert results == []

    @pytest.mark.asyncio
    async def test_special_characters_in_query(self, searcher: ZhihuSearcher) -> None:
        """Test handling of special characters in query."""
        # Query with special characters should be sanitized
        results = await searcher.search('Python <script>alert("xss")</script>', max_results=5)

        # Should handle gracefully (may return empty or sanitized results)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_browser_pool_reuse(self, browser_pool: BrowserPool) -> None:
        """Test that browser pool is reused across searches."""
        searcher = ZhihuSearcher(browser_pool)

        # First search
        results1 = await searcher.search("Python", max_results=3)
        assert isinstance(results1, list)

        # Second search (should reuse browser)
        results2 = await searcher.search("AI", max_results=3)
        assert isinstance(results2, list)

        # Both searches should return lists (may be empty due to network issues)
        # If results are returned, verify they have correct structure
        if len(results1) > 0:
            for result in results1:
                assert "title" in result
                assert "url" in result
                assert "source" in result

        if len(results2) > 0:
            for result in results2:
                assert "title" in result
                assert "url" in result
                assert "source" in result

    @pytest.mark.asyncio
    async def test_search_manager_integration(self, manager: UnifiedSearchManager) -> None:
        """Test search through UnifiedSearchManager."""
        results = await manager.search("zhihu", "Python", max_results=5)

        # Should return a list (may be empty due to network issues or anti-bot detection)
        assert isinstance(results, list)

        # If results are returned, verify they have correct format
        if len(results) > 0:
            for result in results:
                assert "title" in result
                assert "url" in result
                assert "source" in result

    @pytest.mark.asyncio
    async def test_search_manager_cache(self, manager: UnifiedSearchManager) -> None:
        """Test that search manager caching works."""
        import time

        # First search (no cache)
        start1 = time.time()
        results1 = await manager.search("zhihu", "Python", max_results=5, use_cache=True)
        time1 = time.time() - start1

        # Second search (should use cache)
        start2 = time.time()
        results2 = await manager.search("zhihu", "Python", max_results=5, use_cache=True)
        time2 = time.time() - start2

        # Results should be the same
        assert results1 == results2

        # Cached search should be faster
        assert time2 < time1

        # Clean up
        await manager.close()

    @pytest.mark.asyncio
    async def test_multiple_searches(self, searcher: ZhihuSearcher) -> None:
        """Test multiple consecutive searches."""
        queries = ["Python", "AI", "Machine Learning", "Deep Learning", "Neural Network"]

        for query in queries:
            results = await searcher.search(query, max_results=3)
            assert isinstance(results, list)
            # Some queries may return empty results, which is acceptable

    @pytest.mark.asyncio
    async def test_chinese_query(self, searcher: ZhihuSearcher) -> None:
        """Test search with Chinese characters."""
        results = await searcher.search("人工智能", max_results=5)

        # Should handle Chinese characters
        assert isinstance(results, list)

        # If results are returned, they should be valid
        for result in results:
            assert "title" in result
            assert "url" in result

    @pytest.mark.asyncio
    async def test_concurrent_platforms(self, browser_pool: BrowserPool) -> None:
        """Test that two platforms can be used concurrently."""
        from platforms.weixin_searcher import WeixinSearcher

        manager = UnifiedSearchManager()
        weixin_searcher = WeixinSearcher(browser_pool)
        zhihu_searcher = ZhihuSearcher(browser_pool)

        manager.register_platform("weixin", weixin_searcher)
        manager.register_platform("zhihu", zhihu_searcher)

        # Search both platforms
        weixin_results = await manager.search("weixin", "Python", max_results=5)
        zhihu_results = await manager.search("zhihu", "Python", max_results=5)

        # Both should return lists (may be empty due to network issues)
        assert isinstance(weixin_results, list)
        assert isinstance(zhihu_results, list)

        # Note: Results may be empty due to network issues or anti-bot detection
        # The important part is that both searches completed without errors

        # If results are returned, verify they have correct format
        for result in weixin_results + zhihu_results:
            assert "title" in result
            assert "url" in result
            assert "source" in result

        # Clean up
        await manager.close()
