"""
Tests for content compressor module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from openai import RateLimitError
import asyncio
from core.content_compressor import ContentCompressor


@pytest.mark.asyncio
class TestContentCompressor:
    """Test cases for ContentCompressor."""

    @pytest.fixture
    def mock_config(self):
        """Create mock compression config."""
        return {
            "compression": {
                "api": {
                    "model": "deepseek-chat",
                    "timeout": 30,
                    "max_retries": 2,
                },
                "thresholds": {
                    "single_article": 3000,
                    "total_content": 50000,
                    "final_output": 80000,
                },
            }
        }

    @pytest.fixture
    def compressor(self, mock_config):
        """Create ContentCompressor instance with mocked API."""
        with patch.dict("os.environ", {"APIKEY_DEEPSEEK": "test-key"}):
            with patch("core.content_compressor.AsyncOpenAI"):
                compressor = ContentCompressor(mock_config)
                compressor.client = MagicMock()
                return compressor

    async def test_compress_content_success(self, compressor):
        """Test successful content compression."""
        # Mock API response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Compressed content"
        compressor.client.chat.completions.create = AsyncMock(return_value=mock_response)

        content, status = await compressor.compress_content("Original long content", 2000)

        assert status == "compressed"
        assert content == "Compressed content"
        compressor.client.chat.completions.create.assert_called_once()

    async def test_compress_content_rate_limit(self, compressor):
        """Test compression with rate limit error."""
        # Mock rate limit error, then success
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Compressed after retry"

        # Create a proper RateLimitError
        mock_request = MagicMock()
        rate_limit_error = RateLimitError(
            message="Rate limit",
            response=MagicMock(request=mock_request),
            body=None,
        )

        compressor.client.chat.completions.create = AsyncMock(
            side_effect=[rate_limit_error, mock_response]
        )

        content, status = await compressor.compress_content("Original content", 2000)

        assert status == "compressed"
        assert compressor.client.chat.completions.create.call_count == 2  # Retried

    async def test_compress_content_timeout(self, compressor):
        """Test compression timeout."""
        compressor.client.chat.completions.create = AsyncMock(
            side_effect=asyncio.TimeoutError("Timeout")
        )

        original_content = "Original content" * 100  # Make it long enough to truncate
        content, status = await compressor.compress_content(original_content, 2000)

        # On timeout, should use truncation fallback to ensure content fits within token limit
        assert status == "truncated"
        assert len(content) <= len(original_content)  # Truncated content should be shorter or equal

    async def test_compress_content_error_fallback(self, compressor):
        """Test compression error fallback to truncation."""
        compressor.client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        content, status = await compressor.compress_content("Original long content", 10)

        assert status == "truncated"
        assert len(content) <= 10  # Truncated

    async def test_compress_article(self, compressor):
        """Test article compression."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Compressed article"
        compressor.client.chat.completions.create = AsyncMock(return_value=mock_response)

        article = {"title": "Test", "content": "Long article content"}
        result = await compressor.compress_article(article, 2000)

        assert result["content"] == "Compressed article"
        assert result["content_status"] == "compressed"

    async def test_compress_batch(self, compressor):
        """Test batch compression."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Batch compressed content"
        compressor.client.chat.completions.create = AsyncMock(return_value=mock_response)

        articles = [
            {"title": "Article 1", "content": "Content 1"},
            {"title": "Article 2", "content": "Content 2"},
        ]
        result = await compressor.compress_batch(articles, 5000)

        assert all(article["content_status"] == "batch_compressed" for article in result)

    @pytest.mark.asyncio
    async def test_truncate(self, compressor):
        """Test truncation fallback."""
        long_content = "A" * 100
        truncated = compressor._truncate(long_content, 50)

        assert len(truncated) <= 50
        assert truncated.endswith("...")

    @pytest.mark.asyncio
    async def test_truncate_short_content(self, compressor):
        """Test truncation with content shorter than limit."""
        short_content = "Short"
        truncated = compressor._truncate(short_content, 100)

        assert truncated == short_content  # No truncation needed
