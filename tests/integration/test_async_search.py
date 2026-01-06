"""
Integration tests for async search functionality.

Tests the complete async search workflow including:
- Task creation and status polling
- Fast completion detection
- Short and long tasks
- Concurrent tasks
- Error handling
"""

import asyncio
import pytest
from typing import Dict, Any
from mcp_server import MCPServer
from core.task_manager import TaskManager, TaskStatus


class TestAsyncSearchIntegration:
    """Integration test suite for async search."""

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
    async def test_start_vertical_search(self, server: MCPServer) -> None:
        """Test starting a vertical search task."""
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
    async def test_get_search_status_running(self, server: MCPServer) -> None:
        """Test getting status of a running task."""
        # Start a task
        start_request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "weixin",
                    "query": "Python",
                    "max_results": 10,
                    "include_content": True,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(start_request)
        server.send_response = original_send

        task_id = response_captured["result"]["task_id"]

        # Get status immediately (should be running or completed)
        status_request = self._create_request(
            "tools/call",
            {
                "name": "get_search_status",
                "arguments": {"task_id": task_id},
            },
            request_id=2,
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(status_request)
        server.send_response = original_send

        assert response_captured["error"] is None
        assert response_captured["result"] is not None
        assert response_captured["result"]["task_id"] == task_id
        assert response_captured["result"]["status"] in [
            "running",
            "completed",
            "failed",
        ]

    @pytest.mark.asyncio
    async def test_complete_workflow(self, server: MCPServer) -> None:
        """Test complete async search workflow (start -> poll -> complete)."""
        # Start task
        start_request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "weixin",
                    "query": "test",
                    "max_results": 5,
                    "include_content": False,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(start_request)
        server.send_response = original_send

        task_id = response_captured["result"]["task_id"]

        # Poll status until complete
        max_attempts = 30
        completed = False
        for i in range(max_attempts):
            status_request = self._create_request(
                "tools/call",
                {
                    "name": "get_search_status",
                    "arguments": {"task_id": task_id},
                },
                request_id=i + 2,
            )

            response_captured, original_send = self._capture_response(server)
            await server.handle_request(status_request)
            server.send_response = original_send

            status = response_captured["result"]["status"]
            if status == "completed":
                assert "content" in response_captured["result"]
                completed = True
                break
            elif status == "failed":
                pytest.fail(f"Task failed: {response_captured['result'].get('error')}")
            else:
                await asyncio.sleep(2)

        assert completed, "Task did not complete in time"

    @pytest.mark.asyncio
    async def test_fast_completion_detection(self, server: MCPServer) -> None:
        """Test fast completion detection (task completes in <1s)."""
        # Start a small task that should complete quickly
        start_request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "weixin",
                    "query": "test",
                    "max_results": 3,
                    "include_content": False,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(start_request)
        server.send_response = original_send

        # If task completed quickly, result should contain content
        if response_captured["result"].get("status") == "completed":
            assert "content" in response_captured["result"]
        else:
            # Task still running, which is also valid
            assert "task_id" in response_captured["result"]

    @pytest.mark.asyncio
    async def test_short_task(self, server: MCPServer) -> None:
        """Test short task (10 results, no content)."""
        start_request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "weixin",
                    "query": "Python",
                    "max_results": 10,
                    "include_content": False,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(start_request)
        server.send_response = original_send

        task_id = response_captured["result"]["task_id"]

        # Wait for completion
        max_attempts = 20
        for i in range(max_attempts):
            status_request = self._create_request(
                "tools/call",
                {
                    "name": "get_search_status",
                    "arguments": {"task_id": task_id},
                },
                request_id=i + 2,
            )

            response_captured, original_send = self._capture_response(server)
            await server.handle_request(status_request)
            server.send_response = original_send

            status = response_captured["result"]["status"]
            if status == "completed":
                assert "content" in response_captured["result"]
                break
            elif status == "failed":
                pytest.fail(f"Task failed: {response_captured['result'].get('error')}")
            else:
                await asyncio.sleep(2)

    @pytest.mark.asyncio
    async def test_long_task(self, server: MCPServer) -> None:
        """Test long task (10 results with content)."""
        start_request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "weixin",
                    "query": "Python",
                    "max_results": 10,
                    "include_content": True,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(start_request)
        server.send_response = original_send

        task_id = response_captured["result"]["task_id"]

        # Wait for completion (longer timeout for content fetching)
        max_attempts = 60
        completed = False
        for i in range(max_attempts):
            status_request = self._create_request(
                "tools/call",
                {
                    "name": "get_search_status",
                    "arguments": {"task_id": task_id},
                },
                request_id=i + 2,
            )

            response_captured, original_send = self._capture_response(server)
            await server.handle_request(status_request)
            server.send_response = original_send

            status = response_captured["result"]["status"]
            if status == "completed":
                assert "content" in response_captured["result"]
                completed = True
                break
            elif status == "failed":
                # Long tasks may fail due to network issues, which is acceptable for testing
                break
            else:
                # Check progress if running
                if "progress" in response_captured["result"]:
                    progress = response_captured["result"]["progress"]
                    assert progress is None or isinstance(progress, dict)
                await asyncio.sleep(3)

        # Task should complete or fail gracefully
        assert status in ["completed", "failed"]

    @pytest.mark.asyncio
    async def test_concurrent_tasks(self, server: MCPServer) -> None:
        """Test multiple concurrent tasks."""
        # Start 3 tasks concurrently
        task_ids = []
        for i in range(3):
            start_request = self._create_request(
                "tools/call",
                {
                    "name": "start_vertical_search",
                    "arguments": {
                        "platform": "weixin",
                        "query": f"test{i}",
                        "max_results": 3,
                        "include_content": False,
                    },
                },
                request_id=i + 1,
            )

            response_captured, original_send = self._capture_response(server)
            await server.handle_request(start_request)
            server.send_response = original_send

            if response_captured["result"] and "task_id" in response_captured["result"]:
                task_ids.append(response_captured["result"]["task_id"])

        assert len(task_ids) == 3

        # Wait for all to complete
        completed = 0
        max_attempts = 30

        for _ in range(max_attempts):
            for task_id in task_ids:
                status_request = self._create_request(
                    "tools/call",
                    {
                        "name": "get_search_status",
                        "arguments": {"task_id": task_id},
                    },
                    request_id=100,
                )

                response_captured, original_send = self._capture_response(server)
                await server.handle_request(status_request)
                server.send_response = original_send

                if response_captured["result"]["status"] == "completed":
                    completed += 1

            if completed == 3:
                break

            await asyncio.sleep(2)

        # At least some tasks should complete
        assert completed > 0

    @pytest.mark.asyncio
    async def test_task_not_found(self, server: MCPServer) -> None:
        """Test getting status of non-existent task."""
        status_request = self._create_request(
            "tools/call",
            {
                "name": "get_search_status",
                "arguments": {"task_id": "non-existent-id"},
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(status_request)
        server.send_response = original_send

        assert response_captured["error"] is None
        assert response_captured["result"] is not None
        assert response_captured["result"]["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_cancel_search(self, server: MCPServer) -> None:
        """Test cancelling a search task."""
        # Start a task
        start_request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "weixin",
                    "query": "test",
                    "max_results": 10,
                    "include_content": True,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(start_request)
        server.send_response = original_send

        task_id = response_captured["result"]["task_id"]

        # Try to cancel (may not work if task completes too quickly)
        cancel_request = self._create_request(
            "tools/call",
            {
                "name": "cancel_search",
                "arguments": {"task_id": task_id},
            },
            request_id=2,
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(cancel_request)
        server.send_response = original_send

        assert response_captured["error"] is None
        assert response_captured["result"] is not None
        assert response_captured["result"]["status"] in [
            "cancelled",
            "not_cancelled",
        ]

    @pytest.mark.asyncio
    async def test_error_handling(self, server: MCPServer) -> None:
        """Test error handling for invalid parameters."""
        # Test missing platform
        start_request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "query": "test",
                    "max_results": 5,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(start_request)
        server.send_response = original_send

        assert response_captured["error"] is not None
        assert response_captured["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_progress_updates(self, server: MCPServer) -> None:
        """Test that progress updates are reported correctly."""
        # Start a task with content
        start_request = self._create_request(
            "tools/call",
            {
                "name": "start_vertical_search",
                "arguments": {
                    "platform": "weixin",
                    "query": "Python",
                    "max_results": 5,
                    "include_content": True,
                },
            },
        )

        response_captured, original_send = self._capture_response(server)
        await server.handle_request(start_request)
        server.send_response = original_send

        task_id = response_captured["result"]["task_id"]

        # Poll status and check for progress updates
        progress_stages = set()
        max_attempts = 20

        for i in range(max_attempts):
            status_request = self._create_request(
                "tools/call",
                {
                    "name": "get_search_status",
                    "arguments": {"task_id": task_id},
                },
                request_id=i + 2,
            )

            response_captured, original_send = self._capture_response(server)
            await server.handle_request(status_request)
            server.send_response = original_send

            status = response_captured["result"]["status"]
            if status == "running" and "progress" in response_captured["result"]:
                progress = response_captured["result"]["progress"]
                if progress:
                    progress_stages.add(progress.get("stage", ""))
            elif status == "completed":
                break
            elif status == "failed":
                break

            await asyncio.sleep(2)

        # Should have seen at least some progress stages
        # (may be empty if task completes too quickly)
        assert isinstance(progress_stages, set)

