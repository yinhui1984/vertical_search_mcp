"""
Unit tests for BrowserPool.

Tests cover:
- Singleton pattern
- Browser initialization
- Page creation performance
- Concurrency safety
- Resource cleanup
"""

import pytest
import asyncio
import time
from core.browser_pool import BrowserPool


class TestBrowserPool:
    """Test suite for BrowserPool."""

    @pytest.mark.asyncio
    async def test_singleton_pattern(self) -> None:
        """Test that BrowserPool is a singleton."""
        # Reset singleton
        BrowserPool._instance = None

        pool1 = BrowserPool()
        pool2 = BrowserPool()

        # Both should be the same instance
        assert pool1 is pool2

        # Clean up
        await pool1.close()

    @pytest.mark.asyncio
    async def test_browser_initialization(self) -> None:
        """Test browser initialization."""
        BrowserPool._instance = None
        pool = BrowserPool()

        # Browser should not be initialized yet
        assert pool.browser is None

        # Initialize browser
        await pool.init()

        # Browser should be initialized
        assert pool.browser is not None
        assert pool.context is not None
        assert pool.playwright is not None

        # Clean up
        await pool.close()

    @pytest.mark.asyncio
    async def test_page_creation_time(self) -> None:
        """Test that page creation is fast (< 1 second) when browser exists."""
        BrowserPool._instance = None
        pool = BrowserPool()

        try:
            # Initialize browser (first time may be slower)
            await pool.init()

            # First page creation (may include some overhead)
            start1 = time.time()
            page1 = await pool.get_page()
            time1 = time.time() - start1
            await page1.close()

            # Second page creation should be fast
            start2 = time.time()
            page2 = await pool.get_page()
            time2 = time.time() - start2

            # Page creation should be < 1 second
            assert time2 < 1.0, f"Page creation took {time2:.2f}s, expected < 1.0s"

            await page2.close()
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_concurrent_initialization(self) -> None:
        """Test that concurrent initialization is safe."""
        BrowserPool._instance = None

        async def init_browser() -> BrowserPool:
            pool = BrowserPool()
            await pool.init()
            return pool

        # Create multiple pools concurrently
        pools = await asyncio.gather(*[init_browser() for _ in range(5)])

        # All should be the same instance
        assert all(pool is pools[0] for pool in pools)

        # Browser should be initialized only once
        assert pools[0].browser is not None

        # Clean up
        await pools[0].close()

    @pytest.mark.asyncio
    async def test_concurrent_page_creation(self) -> None:
        """Test concurrent page creation."""
        BrowserPool._instance = None
        pool = BrowserPool()

        try:
            await pool.init()

            async def create_page() -> None:
                page = await pool.get_page()
                # Simulate some work
                await asyncio.sleep(0.1)
                await page.close()

            # Create multiple pages concurrently
            start = time.time()
            await asyncio.gather(*[create_page() for _ in range(5)])
            elapsed = time.time() - start

            # Should complete in reasonable time
            assert elapsed < 5.0, f"Concurrent page creation took {elapsed:.2f}s"
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_get_page_auto_init(self) -> None:
        """Test that get_page() automatically initializes browser if needed."""
        BrowserPool._instance = None
        pool = BrowserPool()

        # Browser should not be initialized
        assert pool.browser is None

        # get_page() should auto-initialize
        page = await pool.get_page()
        assert pool.browser is not None
        assert pool.context is not None

        await page.close()
        await pool.close()

    @pytest.mark.asyncio
    async def test_close_cleanup(self) -> None:
        """Test that close() properly cleans up resources."""
        BrowserPool._instance = None
        pool = BrowserPool()

        await pool.init()
        assert pool.browser is not None
        assert pool.context is not None
        assert pool.playwright is not None

        await pool.close()

        # All resources should be cleaned up
        assert pool.browser is None
        assert pool.context is None
        assert pool.playwright is None

        # Singleton should be reset
        assert BrowserPool._instance is None

    @pytest.mark.asyncio
    async def test_multiple_pages(self) -> None:
        """Test creating and using multiple pages."""
        BrowserPool._instance = None
        pool = BrowserPool()

        try:
            await pool.init()

            # Create multiple pages
            pages = []
            for _ in range(3):
                page = await pool.get_page()
                pages.append(page)

            # All pages should be valid
            assert len(pages) == 3
            for page in pages:
                assert page is not None

            # Clean up pages
            for page in pages:
                await page.close()
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_reinitialize_after_close(self) -> None:
        """Test that browser can be reinitialized after close."""
        BrowserPool._instance = None
        pool = BrowserPool()

        # Initialize and close
        await pool.init()
        await pool.close()

        # Should be able to initialize again
        await pool.init()
        assert pool.browser is not None

        await pool.close()
