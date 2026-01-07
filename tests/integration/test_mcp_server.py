"""
Integration tests for MCP Server.

These tests verify the MCP protocol implementation and tool calling functionality.
They test:
- MCP protocol handling (initialize, tools/list, tools/call)
- Tool execution and result formatting
- Parameter validation
- Error handling
"""

import pytest
from typing import Dict, Any
from mcp_server import MCPServer


class TestMCPServerIntegration:
    """Integration test suite for MCPServer."""

    @pytest.fixture
    async def server(self) -> MCPServer:
        """Create and initialize MCP server."""
        server = MCPServer()
        await server.start()
        yield server
        await server.stop()

    def _create_request(
        self, method: str, params: Dict[str, Any] = None, request_id: int = 1
    ) -> Dict[str, Any]:
        """
        Create a JSON-RPC request message.

        Args:
            method: Method name
            params: Request parameters
            request_id: Request ID

        Returns:
            JSON-RPC request dictionary
        """
        message: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            message["params"] = params
        return message

    @pytest.mark.asyncio
    async def test_initialize(self, server: MCPServer) -> None:
        """Test initialize request handling."""
        request = self._create_request("initialize", {"protocolVersion": "2024-11-05"})

        # Capture response by mocking send_response
        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        # Restore original method
        server.send_response = original_send

        # Verify response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is None
        assert response_captured["result"] is not None
        assert response_captured["result"]["protocolVersion"] == "2024-11-05"
        assert response_captured["result"]["serverInfo"]["name"] == "vertical-search"

    @pytest.mark.asyncio
    async def test_list_tools(self, server: MCPServer) -> None:
        """Test tools/list request handling."""
        request = self._create_request("tools/list")

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is None
        assert response_captured["result"] is not None
        assert "tools" in response_captured["result"]

        tools = response_captured["result"]["tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0

        # Verify tool schema
        tool = tools[0]
        assert tool["name"] == "search_vertical"
        assert "description" in tool
        assert "inputSchema" in tool

        # Verify input schema
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "platform" in schema["properties"]
        assert "query" in schema["properties"]

    @pytest.mark.asyncio
    async def test_tool_call_success(self, server: MCPServer) -> None:
        """Test successful tool call."""
        request = self._create_request(
            "tools/call",
            {
                "name": "search_vertical",
                "arguments": {
                    "platform": "weixin",
                    "query": "Python",
                    "max_results": 3,
                },
            },
        )

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is None
        assert response_captured["result"] is not None

        # Verify result format
        result = response_captured["result"]
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) > 0

        content = result["content"][0]
        assert content["type"] == "text"
        assert "text" in content
        assert isinstance(content["text"], str)
        assert len(content["text"]) > 0

    @pytest.mark.asyncio
    async def test_tool_call_missing_platform(self, server: MCPServer) -> None:
        """Test tool call with missing platform parameter."""
        request = self._create_request(
            "tools/call",
            {
                "name": "search_vertical",
                "arguments": {
                    "query": "Python",
                },
            },
        )

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify error response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is not None
        assert response_captured["error"]["code"] == -32602
        assert "platform" in response_captured["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_tool_call_missing_query(self, server: MCPServer) -> None:
        """Test tool call with missing query parameter."""
        request = self._create_request(
            "tools/call",
            {
                "name": "search_vertical",
                "arguments": {
                    "platform": "weixin",
                },
            },
        )

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify error response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is not None
        assert response_captured["error"]["code"] == -32602
        assert "query" in response_captured["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_tool_call_invalid_platform(self, server: MCPServer) -> None:
        """Test tool call with invalid platform."""
        request = self._create_request(
            "tools/call",
            {
                "name": "search_vertical",
                "arguments": {
                    "platform": "invalid_platform",
                    "query": "Python",
                },
            },
        )

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify error response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is not None
        assert response_captured["error"]["code"] == -32602
        assert "invalid" in response_captured["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_tool_call_invalid_max_results(self, server: MCPServer) -> None:
        """Test tool call with invalid max_results."""
        request = self._create_request(
            "tools/call",
            {
                "name": "search_vertical",
                "arguments": {
                    "platform": "weixin",
                    "query": "Python",
                    "max_results": 100,  # Exceeds limit of 30
                },
            },
        )

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify error response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is not None
        assert response_captured["error"]["code"] == -32602
        assert "max_results" in response_captured["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_tool_call_unknown_tool(self, server: MCPServer) -> None:
        """Test tool call with unknown tool name."""
        request = self._create_request(
            "tools/call",
            {
                "name": "unknown_tool",
                "arguments": {},
            },
        )

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify error response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is not None
        assert response_captured["error"]["code"] == -32601
        assert "unknown" in response_captured["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_tool_call_with_alias_chinese(self, server: MCPServer) -> None:
        """Test tool call using Chinese alias '垂直搜索'."""
        request = self._create_request(
            "tools/call",
            {
                "name": "垂直搜索",
                "arguments": {
                    "platform": "weixin",
                    "query": "Python",
                    "max_results": 3,
                },
            },
        )

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify response (should work same as search_vertical)
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is None
        assert response_captured["result"] is not None

    @pytest.mark.asyncio
    async def test_tool_call_with_alias_vertical_search(self, server: MCPServer) -> None:
        """Test tool call using alias 'vertical_search'."""
        request = self._create_request(
            "tools/call",
            {
                "name": "vertical_search",
                "arguments": {
                    "platform": "weixin",
                    "query": "Python",
                    "max_results": 3,
                },
            },
        )

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify response (should work same as search_vertical)
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is None
        assert response_captured["result"] is not None

    @pytest.mark.asyncio
    async def test_tool_description_includes_aliases(self, server: MCPServer) -> None:
        """Test that tool description includes alias information."""
        request = self._create_request("tools/list")

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify description includes alias information
        assert response_captured is not None
        tools = response_captured["result"]["tools"]
        tool = tools[0]
        description = tool["description"]

        # Check that description mentions aliases
        assert "垂直搜索" in description or "vertical_search" in description

    @pytest.mark.asyncio
    async def test_notification_initialized(self, server: MCPServer) -> None:
        """Test notifications/initialized notification handling."""
        request = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }

        # Should not raise exception
        await server.handle_request(request)

    @pytest.mark.asyncio
    async def test_unknown_method(self, server: MCPServer) -> None:
        """Test handling of unknown method."""
        request = self._create_request("unknown_method")

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify error response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is not None
        assert response_captured["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_format_search_results(self, server: MCPServer) -> None:
        """Test search result formatting."""
        results = [
            {
                "title": "Test Article 1",
                "url": "https://example.com/article1",
                "source": "Test Source",
                "date": "2024-01-01",
                "snippet": "This is a test snippet for article 1",
            },
            {
                "title": "Test Article 2",
                "url": "https://example.com/article2",
                "source": "Test Source 2",
                "date": "",
                "snippet": "",
            },
        ]

        formatted = server._format_search_results("weixin", "test query", results)

        assert isinstance(formatted, str)
        assert len(formatted) > 0
        assert "test query" in formatted
        assert "WeChat" in formatted
        assert "Test Article 1" in formatted
        assert "Test Article 2" in formatted
        assert "https://example.com/article1" in formatted

    @pytest.mark.asyncio
    async def test_format_search_results_empty(self, server: MCPServer) -> None:
        """Test formatting of empty search results."""
        formatted = server._format_search_results("weixin", "test query", [])

        assert isinstance(formatted, str)
        assert "No results found" in formatted
        assert "test query" in formatted

    @pytest.mark.asyncio
    async def test_zhihu_platform(self, server: MCPServer) -> None:
        """Test tool call with zhihu platform."""
        request = self._create_request(
            "tools/call",
            {
                "name": "search_vertical",
                "arguments": {
                    "platform": "zhihu",
                    "query": "Python",
                    "max_results": 3,
                },
            },
        )

        response_captured = None

        def capture_response(request_id: int, result: Any = None, error: Any = None) -> None:
            nonlocal response_captured
            response_captured = {"id": request_id, "result": result, "error": error}

        original_send = server.send_response
        server.send_response = capture_response  # type: ignore

        await server.handle_request(request)

        server.send_response = original_send

        # Verify response
        assert response_captured is not None
        assert response_captured["id"] == 1
        assert response_captured["error"] is None
        assert response_captured["result"] is not None

        # Verify result format
        result = response_captured["result"]
        assert "content" in result
        content = result["content"][0]
        assert content["type"] == "text"
        assert "Zhihu" in content["text"]
