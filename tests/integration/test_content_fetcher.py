"""
Tests for content fetcher module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.content_fetcher import ContentFetcher
from core.browser_pool import BrowserPool


class TestContentFetcher:
    """Test cases for ContentFetcher."""

    @pytest.fixture
    def mock_browser_pool(self):
        """Create a mock browser pool."""
        pool = MagicMock(spec=BrowserPool)
        page = AsyncMock()
        page.goto = AsyncMock()
        page.query_selector = AsyncMock()
        page.evaluate = AsyncMock()
        page.close = AsyncMock()
        pool.get_page = AsyncMock(return_value=page)
        return pool, page

    @pytest.fixture
    def platform_config(self):
        """Create platform configuration."""
        return {
            "weixin": {
                "content_selectors": {
                    "main_content": ["#js_content", ".rich_media_content"],
                    "elements_to_remove": [".qr_code_pc", "script"],
                }
            },
            "zhihu": {
                "content_selectors": {
                    "main_content": [".RichContent-inner", ".Post-RichText"],
                    "elements_to_remove": [".ContentItem-actions"],
                }
            },
        }

    @pytest.fixture
    def fetcher(self, mock_browser_pool, platform_config):
        """Create ContentFetcher instance."""
        pool, _ = mock_browser_pool
        return ContentFetcher(pool, platform_config)

    @pytest.mark.asyncio
    async def test_fetch_content_success(self, fetcher, mock_browser_pool, platform_config):
        """Test successful content fetching."""
        pool, page = mock_browser_pool

        # Mock element with content
        element = MagicMock()
        element.inner_text = AsyncMock(return_value="Test article content")
        page.query_selector.return_value = element

        content = await fetcher.fetch_content("https://example.com/article", "weixin")

        assert content is not None
        assert "Test article content" in content
        page.goto.assert_called_once()
        page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_content_selector_fallback(self, fetcher, mock_browser_pool):
        """Test selector fallback mechanism."""
        pool, page = mock_browser_pool

        # First selector returns None, second succeeds
        element = MagicMock()
        element.inner_text = AsyncMock(return_value="Content from fallback")
        page.query_selector.side_effect = [None, element]

        content = await fetcher.fetch_content("https://example.com/article", "weixin")

        assert content is not None
        assert page.query_selector.call_count >= 2  # Tried multiple selectors

    @pytest.mark.asyncio
    async def test_fetch_content_no_selectors(self, fetcher, mock_browser_pool):
        """Test fetching when no selectors configured."""
        pool, page = mock_browser_pool

        # Platform not in config
        content = await fetcher.fetch_content("https://example.com/article", "unknown")

        assert content is None

    @pytest.mark.asyncio
    async def test_fetch_content_timeout(self, fetcher, mock_browser_pool):
        """Test content fetching timeout."""
        pool, page = mock_browser_pool

        # Mock timeout
        page.goto.side_effect = TimeoutError("Page load timeout")

        content = await fetcher.fetch_content("https://example.com/article", "weixin", timeout=1)

        assert content is None
        page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_clean_content(self, fetcher):
        """Test content cleaning."""
        # Test excessive newlines
        dirty = "Line 1\n\n\n\nLine 2"
        clean = fetcher._clean_content(dirty)
        assert "\n\n\n" not in clean

        # Test excessive spaces
        dirty = "Word1    Word2"
        clean = fetcher._clean_content(dirty)
        assert "    " not in clean

    def test_get_url_hash(self):
        """Test URL hash generation."""
        url1 = "https://example.com/article"
        url2 = "https://example.com/article"
        url3 = "https://example.com/different"

        hash1 = ContentFetcher.get_url_hash(url1)
        hash2 = ContentFetcher.get_url_hash(url2)
        hash3 = ContentFetcher.get_url_hash(url3)

        assert hash1 == hash2  # Same URL should produce same hash
        assert hash1 != hash3  # Different URLs should produce different hashes
        assert len(hash1) == 32  # MD5 hash length

