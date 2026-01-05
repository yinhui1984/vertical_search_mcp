"""
Unit tests for UnifiedSearchManager.

Tests cover:
- Platform registration mechanism
- Search routing
- Cache integration
- Error handling
"""

import pytest
from typing import List, Dict, Optional, Any
from core.search_manager import UnifiedSearchManager
from core.base_searcher import BasePlatformSearcher
from core.browser_pool import BrowserPool
from playwright.async_api import ElementHandle


class MockSearcher(BasePlatformSearcher):
    """Mock searcher for testing."""

    def __init__(self, browser_pool: BrowserPool, platform_name: str) -> None:
        """Initialize mock searcher."""
        super().__init__(browser_pool)
        self.platform_name = platform_name
        self.config = {"name": platform_name}

    def _load_config(self) -> Dict[str, Any]:
        """Load mock configuration."""
        return {"name": self.platform_name}

    async def search(
        self, query: str, max_results: int = 10, **kwargs: Any
    ) -> List[Dict[str, str]]:
        """Mock search that returns platform-specific results."""
        return [
            {
                "title": f"{self.platform_name} Article",
                "url": f"https://{self.platform_name}.com/article",
                "source": self.platform_name,
            }
        ]

    async def _extract_item(self, element: ElementHandle, index: int) -> Optional[Dict[str, str]]:
        """Mock extract implementation."""
        return None


class TestUnifiedSearchManager:
    """Test suite for UnifiedSearchManager."""

    def test_init(self) -> None:
        """Test manager initialization."""
        manager = UnifiedSearchManager()
        assert manager.browser_pool is not None
        assert manager.cache is not None
        assert manager.searchers == {}
        assert manager.logger is not None

    def test_register_platform(self) -> None:
        """Test platform registration."""
        manager = UnifiedSearchManager()
        pool = manager.browser_pool
        searcher = MockSearcher(pool, "weixin")

        manager.register_platform("weixin", searcher)
        assert "weixin" in manager.searchers
        assert manager.searchers["weixin"] == searcher

    def test_register_platform_empty_name(self) -> None:
        """Test registration with empty platform name."""
        manager = UnifiedSearchManager()
        pool = manager.browser_pool
        searcher = MockSearcher(pool, "test")

        with pytest.raises(ValueError, match="Platform name cannot be empty"):
            manager.register_platform("", searcher)

    def test_register_platform_none_searcher(self) -> None:
        """Test registration with None searcher."""
        manager = UnifiedSearchManager()

        with pytest.raises(ValueError, match="Searcher cannot be None"):
            manager.register_platform("test", None)  # type: ignore

    def test_get_registered_platforms(self) -> None:
        """Test getting registered platforms list."""
        manager = UnifiedSearchManager()
        pool = manager.browser_pool

        assert manager.get_registered_platforms() == []

        searcher1 = MockSearcher(pool, "weixin")
        searcher2 = MockSearcher(pool, "zhihu")

        manager.register_platform("weixin", searcher1)
        manager.register_platform("zhihu", searcher2)

        platforms = manager.get_registered_platforms()
        assert len(platforms) == 2
        assert "weixin" in platforms
        assert "zhihu" in platforms

    @pytest.mark.asyncio
    async def test_search_unregistered_platform(self) -> None:
        """Test search with unregistered platform."""
        manager = UnifiedSearchManager()

        with pytest.raises(ValueError, match="Platform 'unknown' not registered"):
            await manager.search(platform="unknown", query="test query")

    @pytest.mark.asyncio
    async def test_search_basic(self) -> None:
        """Test basic search functionality."""
        manager = UnifiedSearchManager()
        pool = manager.browser_pool
        searcher = MockSearcher(pool, "weixin")

        manager.register_platform("weixin", searcher)

        results = await manager.search(platform="weixin", query="test query", use_cache=False)
        assert len(results) == 1
        assert results[0]["source"] == "weixin"
        assert results[0]["title"] == "weixin Article"

    @pytest.mark.asyncio
    async def test_search_with_cache(self) -> None:
        """Test search with cache enabled."""
        manager = UnifiedSearchManager()
        pool = manager.browser_pool
        searcher = MockSearcher(pool, "weixin")

        manager.register_platform("weixin", searcher)

        # First search (no cache)
        results1 = await manager.search(platform="weixin", query="test query", use_cache=True)
        assert len(results1) == 1

        # Second search (should hit cache)
        results2 = await manager.search(platform="weixin", query="test query", use_cache=True)
        assert len(results2) == 1
        assert results1 == results2

    @pytest.mark.asyncio
    async def test_search_without_cache(self) -> None:
        """Test search with cache disabled."""
        manager = UnifiedSearchManager()
        pool = manager.browser_pool
        searcher = MockSearcher(pool, "weixin")

        manager.register_platform("weixin", searcher)

        # Both searches should execute (no cache)
        results1 = await manager.search(platform="weixin", query="test query", use_cache=False)
        results2 = await manager.search(platform="weixin", query="test query", use_cache=False)

        assert len(results1) == 1
        assert len(results2) == 1

    @pytest.mark.asyncio
    async def test_search_with_time_filter(self) -> None:
        """Test search with time filter parameter."""
        manager = UnifiedSearchManager()
        pool = manager.browser_pool
        searcher = MockSearcher(pool, "weixin")

        manager.register_platform("weixin", searcher)

        results = await manager.search(
            platform="weixin", query="test query", time_filter="day", use_cache=False
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_error_handling(self) -> None:
        """Test error handling in search."""
        manager = UnifiedSearchManager()
        pool = manager.browser_pool

        # Create a searcher that raises an error
        class ErrorSearcher(BasePlatformSearcher):
            def _load_config(self) -> Dict[str, Any]:
                return {}

            async def search(
                self, query: str, max_results: int = 10, **kwargs: Any
            ) -> List[Dict[str, str]]:
                raise RuntimeError("Search failed")

            async def _extract_item(
                self, element: ElementHandle, index: int
            ) -> Optional[Dict[str, str]]:
                return None

        searcher = ErrorSearcher(pool)
        manager.register_platform("error", searcher)

        with pytest.raises(RuntimeError, match="Search failed for error:test query"):
            await manager.search(platform="error", query="test query", use_cache=False)

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """Test manager close method."""
        manager = UnifiedSearchManager()
        await manager.close()
        # Should not raise any errors
