"""
Unit tests for multi-platform search functionality in MCP server.

Tests cover:
- Platform parsing (_parse_platforms)
- Max results sum calculation (_get_max_results_sum)
- Result deduplication (_deduplicate_results_by_url)
"""

import pytest
from mcp_server import MCPServer
from core.search_manager import UnifiedSearchManager
from platforms.weixin_searcher import WeixinSearcher
from platforms.google_searcher import GoogleSearcher


class TestMCPMultiPlatform:
    """Test suite for multi-platform search functionality."""

    @pytest.fixture
    def server(self) -> MCPServer:
        """Create MCP server instance."""
        return MCPServer()

    @pytest.fixture
    async def server_with_manager(self) -> MCPServer:
        """Create and initialize MCP server with manager."""
        server = MCPServer()
        server.manager = UnifiedSearchManager()
        server.manager.register_platform("weixin", WeixinSearcher(server.manager.browser_pool))
        
        # Register Google if credentials available
        import os
        google_api_key = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
        google_search_id = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
        if google_api_key and google_search_id:
            server.manager.register_platform("google", GoogleSearcher(server.manager.browser_pool))
        
        yield server
        await server.manager.close()

    def test_parse_platforms_all(self, server_with_manager: MCPServer) -> None:
        """Test parsing 'all' returns all registered platforms."""
        platforms = server_with_manager._parse_platforms("all")
        registered = server_with_manager.manager.get_registered_platforms()
        assert set(platforms) == set(registered)
        assert len(platforms) == len(registered)

    def test_parse_platforms_single(self, server_with_manager: MCPServer) -> None:
        """Test parsing single platform."""
        platforms = server_with_manager._parse_platforms("weixin")
        assert platforms == ["weixin"]

    def test_parse_platforms_multiple(self, server_with_manager: MCPServer) -> None:
        """Test parsing multiple platforms."""
        platforms = server_with_manager._parse_platforms("weixin,google")
        assert "weixin" in platforms
        assert "google" in platforms
        assert len(platforms) == 2

    def test_parse_platforms_with_spaces(self, server_with_manager: MCPServer) -> None:
        """Test parsing with spaces around commas."""
        platforms = server_with_manager._parse_platforms("weixin, google")
        assert "weixin" in platforms
        assert "google" in platforms
        assert len(platforms) == 2

    def test_parse_platforms_empty_string(self, server_with_manager: MCPServer) -> None:
        """Test parsing empty string defaults to 'all'."""
        platforms = server_with_manager._parse_platforms("")
        registered = server_with_manager.manager.get_registered_platforms()
        assert set(platforms) == set(registered)

    def test_parse_platforms_whitespace(self, server_with_manager: MCPServer) -> None:
        """Test parsing whitespace-only string defaults to 'all'."""
        platforms = server_with_manager._parse_platforms("   ")
        registered = server_with_manager.manager.get_registered_platforms()
        assert set(platforms) == set(registered)

    def test_parse_platforms_invalid(self, server_with_manager: MCPServer) -> None:
        """Test parsing invalid platform raises ValueError."""
        with pytest.raises(ValueError, match="Invalid platform"):
            server_with_manager._parse_platforms("invalid_platform")

    def test_parse_platforms_case_insensitive(self, server_with_manager: MCPServer) -> None:
        """Test parsing is case insensitive."""
        platforms = server_with_manager._parse_platforms("WEIXIN")
        assert platforms == ["weixin"]

    def test_get_max_results_sum(self, server_with_manager: MCPServer) -> None:
        """Test calculating max results sum from all platforms."""
        max_sum = server_with_manager._get_max_results_sum()
        assert max_sum > 0
        # Should be sum of all platform max_results (default 100 each)
        registered_count = len(server_with_manager.manager.get_registered_platforms())
        assert max_sum >= registered_count * 100

    def test_get_max_results_sum_no_manager(self, server: MCPServer) -> None:
        """Test get_max_results_sum returns default when manager not initialized."""
        max_sum = server._get_max_results_sum()
        assert max_sum == 100  # Default fallback

    def test_deduplicate_results_by_url(self, server: MCPServer) -> None:
        """Test deduplication removes duplicate URLs."""
        results = [
            {"title": "Article 1", "url": "https://example.com/1"},
            {"title": "Article 2", "url": "https://example.com/2"},
            {"title": "Article 3", "url": "https://example.com/1"},  # Duplicate
            {"title": "Article 4", "url": "https://example.com/3"},
        ]
        
        deduplicated = server._deduplicate_results_by_url(results)
        assert len(deduplicated) == 3
        urls = [r["url"] for r in deduplicated]
        assert "https://example.com/1" in urls
        assert "https://example.com/2" in urls
        assert "https://example.com/3" in urls
        # First occurrence should be kept
        assert deduplicated[0]["title"] == "Article 1"

    def test_deduplicate_results_by_url_no_duplicates(self, server: MCPServer) -> None:
        """Test deduplication with no duplicates returns all results."""
        results = [
            {"title": "Article 1", "url": "https://example.com/1"},
            {"title": "Article 2", "url": "https://example.com/2"},
        ]
        
        deduplicated = server._deduplicate_results_by_url(results)
        assert len(deduplicated) == 2
        assert deduplicated == results

    def test_deduplicate_results_by_url_empty_url(self, server: MCPServer) -> None:
        """Test deduplication keeps results without URLs."""
        results = [
            {"title": "Article 1", "url": ""},
            {"title": "Article 2", "url": ""},
        ]
        
        deduplicated = server._deduplicate_results_by_url(results)
        assert len(deduplicated) == 2  # Both kept since no URL

    def test_deduplicate_results_by_url_empty_list(self, server: MCPServer) -> None:
        """Test deduplication with empty list."""
        deduplicated = server._deduplicate_results_by_url([])
        assert deduplicated == []

