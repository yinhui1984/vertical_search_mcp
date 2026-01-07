"""
Unit tests for GoogleSearcher.

Tests cover:
- API credential validation
- Query sanitization
- Pagination logic
- Result transformation
- Error handling (429, 400, 401, network errors)
- Retry mechanism with exponential backoff
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any
import httpx
from core.browser_pool import BrowserPool
from platforms.google_searcher import GoogleSearcher


class TestGoogleSearcher:
    """Test suite for GoogleSearcher."""

    @pytest.fixture
    def browser_pool(self) -> BrowserPool:
        """Create mock browser pool."""
        return MagicMock(spec=BrowserPool)

    @pytest.fixture
    def mock_config(self) -> Dict[str, Any]:
        """Create mock platform configuration."""
        return {
            "api": {
                "base_url": "https://www.googleapis.com/customsearch/v1",
                "max_results_per_request": 10,
                "max_total_results": 30,
            },
            "metadata": {
                "name": "Google",
                "display_name": "Google Custom Search",
                "description": "Search using Google Custom Search API",
            },
            "content_selectors": {
                "main_content": ["article", "main", "body"],
                "elements_to_remove": ["nav", "header", "footer"],
            },
        }

    @pytest.fixture
    def searcher(self, browser_pool: BrowserPool, mock_config: Dict[str, Any]) -> GoogleSearcher:
        """Create GoogleSearcher instance with mocked config."""
        with patch.object(GoogleSearcher, "_load_config", return_value=mock_config):
            searcher = GoogleSearcher(browser_pool)
            searcher.api_key = "test-api-key"
            searcher.search_engine_id = "test-search-engine-id"
            return searcher

    @pytest.fixture
    def searcher_no_credentials(
        self, browser_pool: BrowserPool, mock_config: Dict[str, Any]
    ) -> GoogleSearcher:
        """Create GoogleSearcher instance without credentials."""
        with patch.object(GoogleSearcher, "_load_config", return_value=mock_config):
            searcher = GoogleSearcher(browser_pool)
            searcher.api_key = None
            searcher.search_engine_id = None
            return searcher

    def test_initialization(self, searcher: GoogleSearcher) -> None:
        """Test GoogleSearcher initialization."""
        assert searcher is not None
        assert searcher.browser_pool is not None
        assert searcher.api_key == "test-api-key"
        assert searcher.search_engine_id == "test-search-engine-id"
        assert searcher.base_url == "https://www.googleapis.com/customsearch/v1"

    def test_initialization_without_credentials(
        self, searcher_no_credentials: GoogleSearcher
    ) -> None:
        """Test initialization when credentials are missing."""
        assert searcher_no_credentials.api_key is None
        assert searcher_no_credentials.search_engine_id is None

    @pytest.mark.asyncio
    async def test_search_without_credentials(
        self, searcher_no_credentials: GoogleSearcher
    ) -> None:
        """Test search returns empty results when credentials are missing."""
        results = await searcher_no_credentials.search("test query", max_results=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_basic_success(self, searcher: GoogleSearcher) -> None:
        """Test successful search with single API request."""
        mock_response = {
            "items": [
                {
                    "title": "Test Article 1",
                    "link": "https://example.com/article1",
                    "snippet": "This is a test snippet",
                    "pagemap": {"metatags": [{"article:published_time": "2024-01-01T00:00:00Z"}]},
                },
                {
                    "title": "Test Article 2",
                    "link": "https://example.com/article2",
                    "snippet": "Another test snippet",
                    "pagemap": {},
                },
            ]
        }

        async def mock_get(*args, **kwargs):
            response = MagicMock()
            response.json.return_value = mock_response
            response.raise_for_status = MagicMock()
            return response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get = AsyncMock(side_effect=mock_get)
            mock_client.return_value = mock_client_instance

            results = await searcher.search("test query", max_results=10)

            assert len(results) == 2
            assert results[0]["title"] == "Test Article 1"
            assert results[0]["url"] == "https://example.com/article1"
            assert results[0]["snippet"] == "This is a test snippet"
            assert results[0]["date"] == "2024-01-01T00:00:00Z"
            assert results[0]["source"] == "Google Custom Search"

            assert results[1]["title"] == "Test Article 2"
            assert results[1]["url"] == "https://example.com/article2"
            assert results[1]["snippet"] == "Another test snippet"
            assert results[1]["date"] == ""
            assert results[1]["source"] == "Google Custom Search"

    @pytest.mark.asyncio
    async def test_search_pagination(self, searcher: GoogleSearcher) -> None:
        """Test pagination with multiple API requests."""
        # Mock responses for 3 pages (30 results total)
        mock_responses = []
        for page in range(3):
            items = []
            for i in range(10):
                items.append(
                    {
                        "title": f"Article {page * 10 + i + 1}",
                        "link": f"https://example.com/article{page * 10 + i + 1}",
                        "snippet": f"Snippet {page * 10 + i + 1}",
                        "pagemap": {},
                    }
                )
            mock_responses.append({"items": items})

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            response = MagicMock()
            response.json.return_value = mock_responses[call_count]
            response.raise_for_status = MagicMock()
            call_count += 1
            return response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get = AsyncMock(side_effect=mock_get)
            mock_client.return_value = mock_client_instance

            results = await searcher.search("test query", max_results=30)

            assert len(results) == 30
            assert call_count == 3  # Should make 3 API requests

            # Verify pagination parameters
            calls = mock_client_instance.get.call_args_list
            assert calls[0][1]["params"]["start"] == 1
            assert calls[1][1]["params"]["start"] == 11
            assert calls[2][1]["params"]["start"] == 21

    @pytest.mark.asyncio
    async def test_search_rate_limit_retry(self, searcher: GoogleSearcher) -> None:
        """Test retry mechanism on rate limit (429) error."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: rate limit error
                error = httpx.HTTPStatusError(
                    "Rate limit exceeded",
                    request=MagicMock(),
                    response=MagicMock(status_code=429),
                )
                raise error
            else:
                # Retry: success
                response = MagicMock()
                response.json.return_value = {
                    "items": [
                        {
                            "title": "Test",
                            "link": "https://example.com",
                            "snippet": "Test",
                            "pagemap": {},
                        }
                    ]
                }
                response.raise_for_status = MagicMock()
                return response

        with (
            patch("httpx.AsyncClient") as mock_client,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get = AsyncMock(side_effect=mock_get)
            mock_client.return_value = mock_client_instance

            results = await searcher.search("test query", max_results=10)

            assert len(results) == 1
            assert call_count == 2  # Should retry once

    @pytest.mark.asyncio
    async def test_search_invalid_query_400(self, searcher: GoogleSearcher) -> None:
        """Test handling of invalid query (400 error)."""

        async def mock_get(*args, **kwargs):
            error = httpx.HTTPStatusError(
                "Invalid request",
                request=MagicMock(),
                response=MagicMock(
                    status_code=400, content=b'{"error":{"message":"Invalid query"}}'
                ),
            )
            error.response.json = MagicMock(return_value={"error": {"message": "Invalid query"}})
            raise error

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get = AsyncMock(side_effect=mock_get)
            mock_client.return_value = mock_client_instance

            results = await searcher.search("test query", max_results=10)

            assert results == []

    @pytest.mark.asyncio
    async def test_search_invalid_credentials_401(self, searcher: GoogleSearcher) -> None:
        """Test handling of invalid credentials (401 error)."""

        async def mock_get(*args, **kwargs):
            error = httpx.HTTPStatusError(
                "Invalid credentials",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )
            raise error

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get = AsyncMock(side_effect=mock_get)
            mock_client.return_value = mock_client_instance

            results = await searcher.search("test query", max_results=10)

            assert results == []

    @pytest.mark.asyncio
    async def test_search_network_error_retry(self, searcher: GoogleSearcher) -> None:
        """Test retry mechanism on network errors."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # First two calls: network error
                raise httpx.RequestError("Network error")
            else:
                # Third call: success
                response = MagicMock()
                response.json.return_value = {
                    "items": [
                        {
                            "title": "Test",
                            "link": "https://example.com",
                            "snippet": "Test",
                            "pagemap": {},
                        }
                    ]
                }
                response.raise_for_status = MagicMock()
                return response

        with (
            patch("httpx.AsyncClient") as mock_client,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get = AsyncMock(side_effect=mock_get)
            mock_client.return_value = mock_client_instance

            results = await searcher.search("test query", max_results=10)

            assert len(results) == 1
            assert call_count == 3  # Should retry twice

    @pytest.mark.asyncio
    async def test_search_max_results_limit(self, searcher: GoogleSearcher) -> None:
        """Test that max_results is capped at platform limit."""
        mock_response = {
            "items": [
                {"title": "Test", "link": "https://example.com", "snippet": "Test", "pagemap": {}}
            ]
            * 10
        }

        async def mock_get(*args, **kwargs):
            response = MagicMock()
            response.json.return_value = mock_response
            response.raise_for_status = MagicMock()
            return response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get = AsyncMock(side_effect=mock_get)
            mock_client.return_value = mock_client_instance

            # Request 50 results, but platform limit is 30
            results = await searcher.search("test query", max_results=50)

            # Should be capped at 30
            assert len(results) <= 30

    @pytest.mark.asyncio
    async def test_search_empty_query(self, searcher: GoogleSearcher) -> None:
        """Test handling of empty query."""
        results = await searcher.search("", max_results=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_query_sanitization(self, searcher: GoogleSearcher) -> None:
        """Test that query is sanitized before API call."""
        mock_response = {"items": []}

        async def mock_get(*args, **kwargs):
            response = MagicMock()
            response.json.return_value = mock_response
            response.raise_for_status = MagicMock()
            return response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get = AsyncMock(side_effect=mock_get)
            mock_client.return_value = mock_client_instance

            # Query with dangerous characters
            await searcher.search('test<script>alert("xss")</script>', max_results=10)

            # Verify query was sanitized in API call
            # _sanitize_query removes < > " ' characters but keeps keywords
            call_args = mock_client_instance.get.call_args
            assert call_args is not None
            params = call_args[1]["params"]
            sanitized_query = params["q"]

            # Verify dangerous characters are removed
            assert "<" not in sanitized_query
            assert ">" not in sanitized_query
            assert '"' not in sanitized_query
            assert "'" not in sanitized_query

            # Verify the query still contains the main content (keywords are kept)
            assert "test" in sanitized_query

    @pytest.mark.asyncio
    async def test_result_date_extraction(self, searcher: GoogleSearcher) -> None:
        """Test extraction of date from pagemap."""
        mock_response = {
            "items": [
                {
                    "title": "Article with date",
                    "link": "https://example.com/article",
                    "snippet": "Test",
                    "pagemap": {"metatags": [{"article:published_time": "2024-01-15T10:30:00Z"}]},
                },
                {
                    "title": "Article without date",
                    "link": "https://example.com/article2",
                    "snippet": "Test",
                    "pagemap": {},
                },
            ]
        }

        async def mock_get(*args, **kwargs):
            response = MagicMock()
            response.json.return_value = mock_response
            response.raise_for_status = MagicMock()
            return response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get = AsyncMock(side_effect=mock_get)
            mock_client.return_value = mock_client_instance

            results = await searcher.search("test query", max_results=10)

            assert results[0]["date"] == "2024-01-15T10:30:00Z"
            assert results[1]["date"] == ""
