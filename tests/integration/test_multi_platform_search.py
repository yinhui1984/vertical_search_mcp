"""
Integration tests for multi-platform search functionality.

Tests cover:
- Single platform search (backward compatibility)
- Multi-platform search
- Progress reporting
- Result aggregation and deduplication
- Error handling and platform failure isolation
"""

import asyncio
import pytest
from typing import Dict, Any
from mcp_server import MCPServer
from core.task_manager import TaskStatus


class TestMultiPlatformSearch:
    """Integration test suite for multi-platform search."""

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
        """Create a JSON-RPC request message."""
        message: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            message["params"] = params
        return message

    def _capture_response(self, server: MCPServer) -> Dict[str, Any]:
        """Capture server response."""
        response_captured: Dict[str, Any] = {}

        def capture(request_id: int, result: Any = None, error: Any = None) -> None:
            response_captured["id"] = request_id
            response_captured["result"] = result
            response_captured["error"] = error

        original_send = server.send_response
        server.send_response = capture  # type: ignore
        return response_captured, original_send

    @pytest.mark.asyncio
    async def test_single_platform_backward_compatibility(self, server: MCPServer) -> None:
        """Test single platform search works as before (backward compatibility)."""
        request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "weixin",
                    "query": "Python",
                    "max_results": 5,
                    "include_content": False,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(request)
        server.send_response = original_send

        assert response_captured["error"] is None
        assert response_captured["result"] is not None
        assert "task_id" in response_captured["result"]
        assert response_captured["result"]["status"] in ["started", "completed"]

    @pytest.mark.asyncio
    async def test_multi_platform_search_all(self, server: MCPServer) -> None:
        """Test multi-platform search with 'all' platform."""
        request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "all",
                    "query": "Python",
                    "max_results": 10,
                    "include_content": False,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(request)
        server.send_response = original_send

        assert response_captured["error"] is None
        assert response_captured["result"] is not None
        assert "task_id" in response_captured["result"]

        # Wait for task to complete
        task_id = response_captured["result"]["task_id"]
        max_wait = 30
        waited = 0
        while waited < max_wait:
            await asyncio.sleep(2)
            status_request = self._create_request(
                "tools/call",
                {
                    "name": "get_search_status",
                    "arguments": {"task_id": task_id},
                },
                request_id=2,
            )
            status_response, original_send = self._capture_response(server)
            await server.handle_request(status_request)
            server.send_response = original_send

            if status_response["result"] and status_response["result"].get("status") in [
                "completed",
                "failed",
            ]:
                break
            waited += 2

        # Verify task completed
        task = await server.task_manager.get_task(task_id)
        assert task is not None
        assert task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]

    @pytest.mark.asyncio
    async def test_multi_platform_search_specific(self, server: MCPServer) -> None:
        """Test multi-platform search with specific platforms."""
        # Get registered platforms
        registered = server.manager.get_registered_platforms()
        if len(registered) < 2:
            pytest.skip("Need at least 2 platforms registered for this test")

        platform_str = ",".join(registered[:2])
        request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": platform_str,
                    "query": "Python",
                    "max_results": 10,
                    "include_content": False,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(request)
        server.send_response = original_send

        assert response_captured["error"] is None
        assert response_captured["result"] is not None
        assert "task_id" in response_captured["result"]

    @pytest.mark.asyncio
    async def test_multi_platform_progress_reporting(self, server: MCPServer) -> None:
        """Test multi-platform progress reporting includes platform information."""
        registered = server.manager.get_registered_platforms()
        if len(registered) < 2:
            pytest.skip("Need at least 2 platforms registered for this test")

        request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": ",".join(registered[:2]),
                    "query": "test",
                    "max_results": 5,
                    "include_content": False,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(request)
        server.send_response = original_send

        task_id = response_captured["result"]["task_id"]

        # Wait a bit and check progress
        await asyncio.sleep(3)
        task = await server.task_manager.get_task(task_id)
        if task and task.progress:
            # Verify progress message contains platform information for multi-platform
            assert "Platform" in task.progress.message or task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_multi_platform_result_platform_field(self, server: MCPServer) -> None:
        """Test multi-platform results include platform field."""
        registered = server.manager.get_registered_platforms()
        if len(registered) < 2:
            pytest.skip("Need at least 2 platforms registered for this test")

        request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": ",".join(registered[:2]),
                    "query": "test",
                    "max_results": 10,
                    "include_content": False,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(request)
        server.send_response = original_send

        task_id = response_captured["result"]["task_id"]

        # Wait for completion
        max_wait = 30
        waited = 0
        while waited < max_wait:
            await asyncio.sleep(2)
            task = await server.task_manager.get_task(task_id)
            if task and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                break
            waited += 2

        task = await server.task_manager.get_task(task_id)
        if task and task.status == TaskStatus.COMPLETED and task.results:
            # Verify results have platform field
            for result in task.results:
                assert "platform" in result
                assert result["platform"] in registered

    @pytest.mark.asyncio
    async def test_platform_parameter_default_all(self, server: MCPServer) -> None:
        """Test that omitting platform parameter defaults to 'all'."""
        request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "query": "test",
                    "max_results": 5,
                    "include_content": False,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(request)
        server.send_response = original_send

        assert response_captured["error"] is None
        assert response_captured["result"] is not None

    @pytest.mark.asyncio
    async def test_invalid_platform_error(self, server: MCPServer) -> None:
        """Test that invalid platform returns error."""
        request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "invalid_platform",
                    "query": "test",
                    "max_results": 5,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(request)
        server.send_response = original_send

        assert response_captured["error"] is not None
        assert "Invalid platform" in response_captured["error"]["message"]

    @pytest.mark.asyncio
    async def test_max_results_sum_calculation(self, server: MCPServer) -> None:
        """Test that max_results sum is calculated correctly from all platforms."""
        max_sum = server._get_max_results_sum()
        registered = server.manager.get_registered_platforms()
        
        # Should be at least 100 per platform
        assert max_sum >= len(registered) * 100

    @pytest.mark.asyncio
    async def test_tools_list_max_results_dynamic(self, server: MCPServer) -> None:
        """Test that tools/list returns dynamic max_results based on registered platforms."""
        request = self._create_request("tools/list")
        response_captured, original_send = self._capture_response(server)
        await server.handle_request(request)
        server.send_response = original_send

        assert response_captured["error"] is None
        tools = response_captured["result"]["tools"]
        start_tool = next((t for t in tools if t["name"] == "start_vertical_search"), None)
        assert start_tool is not None
        
        max_results_prop = start_tool["inputSchema"]["properties"]["max_results"]
        assert "maximum" in max_results_prop
        # Maximum should be sum of all platform limits
        expected_max = server._get_max_results_sum()
        assert max_results_prop["maximum"] == expected_max

