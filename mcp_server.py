#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vertical Search MCP Server.

This module implements a standard MCP (Model Context Protocol) server
that provides vertical search capabilities for multiple platforms.
"""

import asyncio
import json
import logging
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from core.logger import setup_logger, get_logger
from core.search_manager import UnifiedSearchManager
from core.task_manager import TaskManager, TaskStatus
from platforms.weixin_searcher import WeixinSearcher
# Zhihu searcher import disabled by default
# from platforms.zhihu_searcher import ZhihuSearcher


class MCPServer:
    """
    Standard MCP server implementation.

    This server implements JSON-RPC 2.0 protocol and provides
    vertical search tools for multiple platforms.
    """

    def __init__(self) -> None:
        """Initialize MCP server."""
        self.manager: Optional[UnifiedSearchManager] = None
        self.task_manager = TaskManager()
        self.request_id = 0
        self.logger = get_logger("vertical_search.mcp_server")

    async def start(self) -> None:
        """
        Start the server and initialize search manager.

        This method:
        1. Creates UnifiedSearchManager instance
        2. Registers available platforms (weixin by default, zhihu disabled due to anti-crawler issues)
        3. Initializes browser pool
        """
        self.manager = UnifiedSearchManager()

        # Register platforms
        self.manager.register_platform("weixin", WeixinSearcher(self.manager.browser_pool))
        # Zhihu platform disabled by default due to aggressive anti-crawler measures
        # Uncomment the line below to enable Zhihu search (may not work reliably)
        # self.manager.register_platform("zhihu", ZhihuSearcher(self.manager.browser_pool))

        self.logger.info("Vertical Search MCP Server started")
        self.logger.info(f"Registered platforms: {self.manager.get_registered_platforms()}")

    async def stop(self) -> None:
        """Stop the server and clean up resources."""
        if self.manager:
            await self.manager.close()
        self.logger.info("MCP Server stopped")

    def send_response(self, request_id: int, result: Any = None, error: Any = None) -> None:
        """
        Send JSON-RPC 2.0 response.

        Args:
            request_id: Request ID from the original request
            result: Response result (if successful)
            error: Error object (if failed)
        """
        response: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}

        if error:
            response["error"] = error
        else:
            response["result"] = result

        print(json.dumps(response, ensure_ascii=False))
        sys.stdout.flush()

    async def handle_initialize(self, request_id: int, params: Dict[str, Any]) -> None:
        """
        Handle initialize request.

        Args:
            request_id: Request ID
            params: Initialize parameters
        """
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": "vertical-search",
                "version": "1.0.0",
            },
        }
        self.send_response(request_id, result)

    async def handle_list_tools(self, request_id: int, params: Dict[str, Any]) -> None:
        """
        Handle tools/list request.

        Returns list of available search tools.

        Args:
            request_id: Request ID
            params: Request parameters
        """
        tools = [
            {
                "name": "start_vertical_search",
                "description": "Start an async vertical search task. Returns task_id immediately (< 1 second) in the response. IMPORTANT: Extract the task_id from the response (it's a UUID string like 'abc123-def456-...') and use it to call get_search_status repeatedly (every 10-15 seconds) until status is 'completed' or 'failed' to get the final results. The task_id is shown in both the 'task_id' field and in the 'content' text. If task completes quickly (< 1 second), results are returned directly with status='completed'.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "platform": {
                            "type": "string",
                            "description": "Platform to search (weixin). Note: zhihu is disabled by default due to anti-crawler measures.",
                            "enum": ["weixin"],
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query string",
                            "minLength": 1,
                            "maxLength": 100,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 30,
                        },
                        "include_content": {
                            "type": "boolean",
                            "description": "Whether to include full article content (default: true). Content is automatically compressed if it exceeds token limits.",
                            "default": True,
                        },
                    },
                    "required": ["platform", "query"],
                },
            },
            {
                "name": "get_search_status",
                "description": "Get the status and results of an async search task. IMPORTANT: You MUST call this repeatedly (every 10-15 seconds) with the EXACT task_id from start_vertical_search until status is 'completed' or 'failed'. Do not stop polling until you receive status='completed' (with results) or status='failed' (with error). The task_id is a UUID string (e.g., 'ee82cf71-d921-470c-8bee-6925c802301b') - use it exactly as returned. Returns: 'running' (with progress) if still executing, 'completed' (with results) if finished, 'failed' (with error) if error occurred, or 'not_found' if task expired.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "Task ID from start_vertical_search response. This is a UUID string (e.g., 'ee82cf71-d921-470c-8bee-6925c802301b'). Extract it from the 'task_id' field in the start_vertical_search response and use it exactly as-is.",
                        },
                    },
                    "required": ["task_id"],
                },
            },
            {
                "name": "cancel_search",
                "description": "Cancel a running search task.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "Task ID to cancel",
                        },
                    },
                    "required": ["task_id"],
                },
            },
        ]

        self.send_response(request_id, {"tools": tools})

    async def handle_call_tool(self, request_id: int, params: Dict[str, Any]) -> None:
        """
        Handle tools/call request.

        Executes the requested tool and returns formatted results.

        Args:
            request_id: Request ID
            params: Tool call parameters containing 'name' and 'arguments'
        """
        self.logger.debug(f"handle_call_tool called: request_id={request_id}, params={json.dumps(params, ensure_ascii=False)}")
        
        if not self.manager:
            self.logger.error("Manager not initialized")
            self.send_response(
                request_id,
                None,
                {"code": -32603, "message": "Server not initialized"},
            )
            return

        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        self.logger.info(f"Tool call: {tool_name}, arguments: {json.dumps(arguments, ensure_ascii=False)}")

        if tool_name == "start_vertical_search":
            await self._handle_start_vertical_search(request_id, arguments)
        elif tool_name == "get_search_status":
            await self._handle_get_search_status(request_id, arguments)
        elif tool_name == "cancel_search":
            await self._handle_cancel_search(request_id, arguments)
        else:
            self.send_response(
                request_id,
                None,
                {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            )

    async def _handle_start_vertical_search(
        self, request_id: int, arguments: Dict[str, Any]
    ) -> None:
        """
        Handle start_vertical_search tool call.

        Creates a new async search task and starts background execution.

        Args:
            request_id: Request ID
            arguments: Tool arguments containing platform, query, etc.
        """
        # Validate required parameters
        platform = arguments.get("platform")
        query = arguments.get("query", "")

        if not platform:
            self.send_response(
                request_id,
                None,
                {"code": -32602, "message": "Missing required parameter: platform"},
            )
            return

        if not query:
            self.send_response(
                request_id,
                None,
                {"code": -32602, "message": "Missing required parameter: query"},
            )
            return

        # Validate platform (manager is guaranteed to be initialized at this point)
        assert self.manager is not None
        if platform not in self.manager.get_registered_platforms():
            available = self.manager.get_registered_platforms()
            self.send_response(
                request_id,
                None,
                {
                    "code": -32602,
                    "message": f"Invalid platform '{platform}'. Available platforms: {available}",
                },
            )
            return

        # Get optional parameters
        max_results = arguments.get("max_results", 10)
        include_content = arguments.get("include_content", True)

        # Validate max_results
        if not isinstance(max_results, int) or max_results < 1 or max_results > 30:
            self.send_response(
                request_id,
                None,
                {
                    "code": -32602,
                    "message": "max_results must be an integer between 1 and 30",
                },
            )
            return

        try:
            # Create task
            task_id = await self.task_manager.create_task(
                query=query,
                platform=platform,
                max_results=max_results,
                include_content=include_content,
            )

            # Estimate time
            estimated_time = self._estimate_time(max_results, include_content)

            # Start background execution
            # Store the task reference to avoid garbage collection
            background_task = asyncio.create_task(
                self._execute_search_task(
                    task_id=task_id,
                    platform=platform,
                    query=query,
                    max_results=max_results,
                    include_content=include_content,
                )
            )
            # Add done callback to log if task fails silently
            def task_done_callback(task: asyncio.Task) -> None:
                try:
                    task.result()  # This will raise if task failed
                except Exception as e:
                    self.logger.error(f"Background task {task_id} failed silently: {e}", exc_info=True)
            background_task.add_done_callback(task_done_callback)

            # Fast completion detection: wait 1 second, check if task completed
            # Give the task a moment to start and potentially complete quickly
            await asyncio.sleep(1.0)
            task = await self.task_manager.get_task(task_id)

            if task and task.status == TaskStatus.COMPLETED:
                # Task completed quickly, return results directly
                self.logger.info(f"Task {task_id} completed quickly, returning results directly")
                result_text = self._format_search_results(platform, query, task.results or [])
                self.send_response(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": result_text,
                            }
                        ],
                        "task_id": task_id,
                        "status": "completed",
                    },
                )
            else:
                # Task still running, return task_id
                # Include task_id in both result fields and content text for clarity
                message_text = (
                    f"Search task started.\n\n"
                    f"TASK_ID: {task_id}\n\n"
                    f"IMPORTANT: You MUST call get_search_status with task_id='{task_id}' "
                    f"repeatedly (every 10-15 seconds) until status is 'completed' or 'failed' "
                    f"to get the final results.\n\n"
                    f"Estimated time: {estimated_time}"
                )
                self.send_response(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": message_text,
                            }
                        ],
                        "task_id": task_id,
                        "status": "started",
                        "estimated_time": estimated_time,
                        "message": message_text,
                    },
                )

        except Exception as e:
            self.logger.error(f"Error starting search task: {str(e)}", exc_info=True)
            self.send_response(
                request_id,
                None,
                {"code": -32603, "message": f"Failed to start search task: {str(e)}"},
            )

    async def _handle_get_search_status(
        self, request_id: int, arguments: Dict[str, Any]
    ) -> None:
        """
        Handle get_search_status tool call.

        Returns task status, progress, and results if available.

        Args:
            request_id: Request ID
            arguments: Tool arguments containing task_id
        """
        task_id = arguments.get("task_id")
        if not task_id:
            self.send_response(
                request_id,
                None,
                {"code": -32602, "message": "Missing required parameter: task_id"},
            )
            return

        task = await self.task_manager.get_task(task_id)

        if not task:
            error_text = (
                f"Task not found.\n"
                f"TASK_ID: {task_id}\n"
                f"Error: Task not found. It may have expired (tasks expire after 30 minutes).\n\n"
                f"Please check that you are using the correct task_id from start_vertical_search response."
            )
            self.send_response(
                request_id,
                {
                    "task_id": task_id,
                    "status": "not_found",
                    "content": [
                        {
                            "type": "text",
                            "text": error_text,
                        }
                    ],
                    "error": "Task not found. It may have expired (tasks expire after 30 minutes).",
                },
            )
            return

        elapsed = (datetime.now() - task.created_at).total_seconds()

        if task.status == TaskStatus.RUNNING:
            progress_dict = None
            if task.progress:
                progress_dict = {
                    "current": task.progress.current,
                    "total": task.progress.total,
                    "stage": task.progress.stage,
                    "message": task.progress.message,
                    "percentage": task.progress.percentage,
                }

            progress_text = ""
            if progress_dict:
                progress_text = (
                    f"\nProgress: {progress_dict['stage']} - "
                    f"{progress_dict['message']} "
                    f"({progress_dict['percentage']}%)"
                )

            message_text = (
                f"Task still running.{progress_text}\n\n"
                f"TASK_ID: {task_id}\n\n"
                f"IMPORTANT: You MUST call get_search_status with task_id='{task_id}' "
                f"again in 10-15 seconds. Continue polling until status is 'completed' or 'failed'.\n\n"
                f"Elapsed time: {int(elapsed)} seconds"
            )

            self.send_response(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": message_text,
                        }
                    ],
                    "task_id": task_id,
                    "status": "running",
                    "progress": progress_dict,
                    "elapsed_time": f"{int(elapsed)} seconds",
                    "message": message_text,
                },
            )

        elif task.status == TaskStatus.COMPLETED:
            result_text = self._format_search_results(
                task.platform, task.query, task.results or []
            )
            # Include task_id in the response for reference
            full_result_text = (
                f"Task completed successfully.\n"
                f"TASK_ID: {task_id}\n"
                f"Total results: {len(task.results) if task.results else 0}\n"
                f"Elapsed time: {int(elapsed)} seconds\n\n"
                f"{result_text}"
            )
            self.send_response(
                request_id,
                {
                    "task_id": task_id,
                    "status": "completed",
                    "content": [
                        {
                            "type": "text",
                            "text": full_result_text,
                        }
                    ],
                    "total_results": len(task.results) if task.results else 0,
                    "elapsed_time": f"{int(elapsed)} seconds",
                },
            )

        elif task.status == TaskStatus.FAILED:
            error_text = (
                f"Task failed.\n"
                f"TASK_ID: {task_id}\n"
                f"Error: {task.error or 'Unknown error'}\n"
                f"Elapsed time: {int(elapsed)} seconds"
            )
            self.send_response(
                request_id,
                {
                    "task_id": task_id,
                    "status": "failed",
                    "content": [
                        {
                            "type": "text",
                            "text": error_text,
                        }
                    ],
                    "error": task.error or "Unknown error",
                    "elapsed_time": f"{int(elapsed)} seconds",
                },
            )

        else:  # PENDING or CANCELLED
            self.send_response(
                request_id,
                {
                    "task_id": task_id,
                    "status": task.status.value,
                    "elapsed_time": f"{int(elapsed)} seconds",
                },
            )

    async def _handle_cancel_search(
        self, request_id: int, arguments: Dict[str, Any]
    ) -> None:
        """
        Handle cancel_search tool call.

        Cancels a running search task.

        Args:
            request_id: Request ID
            arguments: Tool arguments containing task_id
        """
        task_id = arguments.get("task_id")
        if not task_id:
            self.send_response(
                request_id,
                None,
                {"code": -32602, "message": "Missing required parameter: task_id"},
            )
            return

        cancelled = await self.task_manager.cancel_task(task_id)

        if cancelled:
            self.send_response(
                request_id,
                {
                    "task_id": task_id,
                    "status": "cancelled",
                    "message": "Task cancelled successfully",
                },
            )
        else:
            self.send_response(
                request_id,
                {
                    "task_id": task_id,
                    "status": "not_cancelled",
                    "message": "Task could not be cancelled. It may not be running or may have already completed.",
                },
            )

    def _format_search_results(
        self, platform: str, query: str, results: List[Dict[str, str]]
    ) -> str:
        """
        Format search results as text.

        Args:
            platform: Platform name
            query: Search query
            results: List of search result dictionaries

        Returns:
            Formatted text string
        """
        platform_name = {"weixin": "WeChat", "zhihu": "Zhihu"}.get(platform, platform)

        if not results:
            return f"No results found for '{query}' on {platform_name}."

        result_text = f"Found {len(results)} result(s) for '{query}' on {platform_name}:\n\n"

        for i, result in enumerate(results, 1):
            title = result.get("title", "Untitled")
            url = result.get("url", "")
            source = result.get("source", "")
            date = result.get("date", "")
            snippet = result.get("snippet", "")
            content = result.get("content", "")
            content_status = result.get("content_status", "")

            result_text += f"{i}. **{title}**\n"
            if source:
                result_text += f"   Source: {source}\n"
            if date:
                result_text += f"   Date: {date}\n"
            if snippet:
                # Truncate snippet to 150 characters
                snippet_text = snippet[:150] + "..." if len(snippet) > 150 else snippet
                result_text += f"   Summary: {snippet_text}\n"
            if url:
                result_text += f"   Link: {url}\n"
            if content:
                # Include full content if present
                content_status_text = ""
                if content_status:
                    status_map = {
                        "fetched": "",
                        "compressed": " (compressed)",
                        "batch_compressed": " (batch compressed)",
                        "truncated": " (truncated)",
                        "fetch_failed": " (content fetch failed)",
                    }
                    content_status_text = status_map.get(content_status, "")
                result_text += f"   Content{content_status_text}:\n"
                # Truncate very long content for display (keep first 2000 chars)
                if len(content) > 2000:
                    result_text += f"   {content[:2000]}...\n"
                    result_text += f"   [Content truncated for display, full length: {len(content)} characters]\n"
                else:
                    result_text += f"   {content}\n"
            result_text += "\n"

        return result_text

    def _estimate_time(self, max_results: int, include_content: bool) -> str:
        """
        Estimate task completion time.

        Args:
            max_results: Maximum number of results
            include_content: Whether to include content

        Returns:
            Estimated time string
        """
        if include_content:
            if max_results <= 10:
                return "30-60 seconds"
            elif max_results <= 20:
                return "1-2 minutes"
            else:
                return "2-3 minutes"
        else:
            if max_results <= 10:
                return "20-40 seconds"
            else:
                return "40-60 seconds"

    async def _execute_search_task(
        self,
        task_id: str,
        platform: str,
        query: str,
        max_results: int,
        include_content: bool,
    ) -> None:
        """
        Execute search task in background.

        This runs as an asyncio.create_task() and updates progress via TaskManager.

        Args:
            task_id: Task identifier
            platform: Platform name
            query: Search query
            max_results: Maximum number of results
            include_content: Whether to include content
        """
        logger = get_logger("vertical_search.mcp_server")

        try:
            # Update status to running
            await self.task_manager.update_task_status(task_id, TaskStatus.RUNNING)
            logger.info(
                f"Task {task_id} started execution: {platform}:{query}, "
                f"max_results={max_results}, include_content={include_content}"
            )

            # Define progress callback
            async def progress_callback(stage: str, message: str, current: int, total: int) -> None:
                await self.task_manager.update_task_progress(
                    task_id=task_id,
                    current=current,
                    total=total,
                    stage=stage,
                    message=message,
                )

            # Execute search with progress callback
            assert self.manager is not None
            logger.debug(f"Task {task_id}: Calling manager.search()")
            results = await self.manager.search(
                platform=platform,
                query=query,
                max_results=max_results,
                use_cache=True,
                include_content=include_content,
                progress_callback=progress_callback,
            )

            logger.info(f"Task {task_id}: Search returned {len(results)} results")
            if len(results) == 0:
                logger.warning(
                    f"Task {task_id}: Search returned 0 results. "
                    f"This may indicate: 1) No results found, 2) Anti-crawler detection, "
                    f"3) Selector mismatch, 4) Page loading issue"
                )

            # Update task with results
            await self.task_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                results=results,
            )

            logger.info(f"Task {task_id} completed: {len(results)} results")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)

            # Update task with error
            await self.task_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                error_traceback=traceback.format_exc(),
            )

    async def handle_list_resources(self, request_id: int, params: Dict[str, Any]) -> None:
        """
        Handle resources/list request.

        Args:
            request_id: Request ID
            params: Request parameters
        """
        self.send_response(request_id, {"resources": []})

    async def handle_list_prompts(self, request_id: int, params: Dict[str, Any]) -> None:
        """
        Handle prompts/list request.

        Args:
            request_id: Request ID
            params: Request parameters
        """
        self.send_response(request_id, {"prompts": []})

    async def handle_notifications_initialized(self) -> None:
        """Handle notifications/initialized notification."""
        # No response needed for notifications
        pass

    async def handle_request(self, message: Dict[str, Any]) -> None:
        """
        Handle incoming JSON-RPC request.

        Routes requests to appropriate handlers based on method name.

        Args:
            message: JSON-RPC message dictionary
        """
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params", {})

        # Handle notification messages (no response needed)
        if method == "notifications/initialized":
            await self.handle_notifications_initialized()
            return
        elif method and method.startswith("notifications/"):
            # Ignore other notification messages
            return

        # Handle request messages (response required)
        if request_id is None:
            # Request messages must have an ID
            return

        if method == "initialize":
            await self.handle_initialize(request_id, params)
        elif method == "tools/list":
            await self.handle_list_tools(request_id, params)
        elif method == "tools/call":
            await self.handle_call_tool(request_id, params)
        elif method == "resources/list":
            await self.handle_list_resources(request_id, params)
        elif method == "prompts/list":
            await self.handle_list_prompts(request_id, params)
        else:
            # Unknown method - respond with error
                self.send_response(
                    request_id,
                    None,
                    {"code": -32601, "message": f"Unknown method: {method}"},
                )


async def main() -> None:
    """Main entry point for MCP server."""
    # Initialize logger before creating server
    setup_logger(name="vertical_search", log_level=logging.INFO)
    logger = get_logger("vertical_search.mcp_server")
    
    server = MCPServer()

    try:
        await server.start()

        # Process stdin input
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )

                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    message = json.loads(line)
                    # Log incoming requests for debugging
                    if message.get("method") == "tools/call":
                        logger.debug(f"Received tool call: {json.dumps(message, ensure_ascii=False)}")
                    await server.handle_request(message)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parse error: {e}")

            except EOFError:
                break
            except Exception as e:
                logger.error(f"Request handling error: {e}", exc_info=True)

    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())

