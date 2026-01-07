"""
Tests for content processor coordinator.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.content_processor import ContentProcessor
from core.browser_pool import BrowserPool
from core.cache import SearchCache


@pytest.mark.asyncio
class TestContentProcessor:
    """Test cases for ContentProcessor."""

    @pytest.fixture
    def mock_browser_pool(self):
        """Create mock browser pool."""
        pool = MagicMock(spec=BrowserPool)
        return pool

    @pytest.fixture
    def mock_cache(self):
        """Create mock cache."""
        return MagicMock(spec=SearchCache)

    @pytest.fixture
    def platform_config(self):
        """Create platform configuration."""
        return {
            "weixin": {
                "content_selectors": {
                    "main_content": ["#js_content"],
                    "elements_to_remove": [],
                }
            }
        }

    @pytest.fixture
    def compression_config(self):
        """Create compression configuration."""
        return {
            "compression": {
                "thresholds": {
                    "single_article": 3000,
                    "total_content": 50000,
                    "final_output": 80000,
                },
                "fetch": {"concurrency": 5, "timeout": 10},
                "cache": {"content_ttl": 3600, "compressed_ttl": 86400},
            }
        }

    @pytest.fixture
    def processor(self, mock_browser_pool, mock_cache, platform_config, compression_config):
        """Create ContentProcessor instance."""
        with (
            patch("core.content_processor.ContentFetcher") as mock_fetcher_class,
            patch("core.content_processor.ContentCompressor") as mock_compressor_class,
        ):
            mock_fetcher = MagicMock()

            # Return actual string content, not MagicMock
            async def fetch_content_side_effect(url, platform, timeout=10):
                return "Fetched content for " + url

            mock_fetcher.fetch_content = AsyncMock(side_effect=fetch_content_side_effect)
            mock_fetcher.get_url_hash = staticmethod(lambda url: "hash123")
            mock_fetcher_class.return_value = mock_fetcher

            mock_compressor = MagicMock()
            mock_compressor.compress_article = AsyncMock(
                side_effect=lambda article, max_tokens: {
                    **article,
                    "content": "Compressed",
                    "content_status": "compressed",
                }
            )
            mock_compressor.compress_batch = AsyncMock(
                side_effect=lambda articles, max_tokens: [
                    {**a, "content": "Batch compressed", "content_status": "batch_compressed"}
                    for a in articles
                ]
            )
            mock_compressor_class.return_value = mock_compressor

            processor = ContentProcessor(
                mock_browser_pool, mock_cache, platform_config, compression_config
            )
            processor.content_fetcher = mock_fetcher
            processor.content_compressor = mock_compressor
            return processor

    async def test_process_results_basic(self, processor):
        """Test basic result processing."""
        results = [
            {"title": "Article 1", "url": "https://example.com/1"},
            {"title": "Article 2", "url": "https://example.com/2"},
        ]

        processed = await processor.process_results(results, "weixin")

        assert len(processed) == 2
        assert all("content" in r for r in processed)
        assert all("content_status" in r for r in processed)

    async def test_process_results_cache_hit(self, processor, mock_cache):
        """Test processing with cache hit."""
        mock_cache.get_content.return_value = "Cached content"

        results = [{"title": "Article 1", "url": "https://example.com/1"}]

        processed = await processor.process_results(results, "weixin")

        # Should use cached content, not fetch
        assert processed[0]["content"] == "Cached content"
        processor.content_fetcher.fetch_content.assert_not_called()

    async def test_should_compress_single(self, processor):
        """Test single article compression decision."""
        article_large = {"content": "A" * 5000, "content_tokens": 4000}  # > 3000
        article_small = {"content": "Small", "content_tokens": 100}  # < 3000

        assert processor._should_compress_single(article_large) is True
        assert processor._should_compress_single(article_small) is False

    @pytest.mark.asyncio
    async def test_should_compress_batch(self, processor):
        """Test batch compression decision."""
        assert processor._should_compress_batch(60000) is True  # > 50000
        assert processor._should_compress_batch(30000) is False  # < 50000

    async def test_process_results_empty(self, processor):
        """Test processing empty results."""
        processed = await processor.process_results([], "weixin")
        assert processed == []
