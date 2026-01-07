"""
Tests for MCP server content integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from mcp_server import MCPServer
from core.search_manager import UnifiedSearchManager


@pytest.mark.asyncio
class TestMCPContent:
    """Test cases for MCP content integration."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance."""
        server = MCPServer()
        server.manager = MagicMock(spec=UnifiedSearchManager)
        return server

    @pytest.fixture
    def mock_results(self):
        """Create mock search results."""
        return [
            {
                "title": "Test Article 1",
                "url": "https://example.com/1",
                "source": "WeChat",
                "snippet": "Test snippet",
            }
        ]

    async def test_include_content_false(self, server, mock_results):
        """Test include_content=False (no content fetched)."""
        server.manager.get_registered_platforms = MagicMock(return_value=["weixin", "zhihu"])
        server.manager.search = AsyncMock(return_value=mock_results)

        request_id = 1
        arguments = {
            "platform": "weixin",
            "query": "test",
            "include_content": False,
        }

        await server._handle_search_vertical(request_id, arguments)

        # Verify search was called without include_content
        server.manager.search.assert_called_once()
        call_kwargs = server.manager.search.call_args[1]
        assert call_kwargs.get("include_content") is False

    async def test_include_content_true(self, server, mock_results):
        """Test include_content=True (content fetched)."""
        results_with_content = [
            {
                **mock_results[0],
                "content": "Full article content here",
                "content_status": "fetched",
            }
        ]
        server.manager.get_registered_platforms = MagicMock(return_value=["weixin", "zhihu"])
        server.manager.search = AsyncMock(return_value=results_with_content)

        request_id = 1
        arguments = {
            "platform": "weixin",
            "query": "test",
            "include_content": True,
        }

        await server._handle_search_vertical(request_id, arguments)

        # Verify search was called with include_content=True
        server.manager.search.assert_called_once()
        call_kwargs = server.manager.search.call_args[1]
        assert call_kwargs.get("include_content") is True

    @pytest.mark.asyncio
    async def test_format_results_with_content(self, server):
        """Test formatting results with content."""
        results = [
            {
                "title": "Test Article",
                "url": "https://example.com",
                "content": "Full article content",
                "content_status": "compressed",
            }
        ]

        formatted = server._format_search_results("weixin", "test", results)

        assert "Content" in formatted
        assert "Full article content" in formatted
        assert "(compressed)" in formatted

    @pytest.mark.asyncio
    async def test_format_results_without_content(self, server):
        """Test formatting results without content."""
        results = [
            {
                "title": "Test Article",
                "url": "https://example.com",
            }
        ]

        formatted = server._format_search_results("weixin", "test", results)

        assert "Content" not in formatted

    @pytest.mark.asyncio
    async def test_tool_schema_includes_content_param(self, server):
        """Test that tool schema includes include_content parameter."""
        request_id = 1
        params = {}

        # Capture the response
        response_captured = None

        def capture_response(req_id, result, error=None):
            nonlocal response_captured
            response_captured = result

        server.send_response = capture_response

        # Call handle_list_tools (already in async context)
        await server.handle_list_tools(request_id, params)

        # Check tool schema
        tools = response_captured.get("tools", [])
        assert len(tools) > 0

        search_tool = tools[0]
        assert search_tool["name"] == "search_vertical"

        input_schema = search_tool.get("inputSchema", {})
        properties = input_schema.get("properties", {})

        assert "include_content" in properties
        assert properties["include_content"]["type"] == "boolean"
        # Default value is True (more user-friendly, users typically want content)
        assert properties["include_content"]["default"] is True
