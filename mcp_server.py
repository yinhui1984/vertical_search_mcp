#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vertical Search MCP Server.

This module implements a standard MCP (Model Context Protocol) server
that provides vertical search capabilities for multiple platforms.
"""

import asyncio
import json
import sys
from typing import Any, Dict, List, Optional

from core.search_manager import UnifiedSearchManager
from platforms.weixin_searcher import WeixinSearcher
from platforms.zhihu_searcher import ZhihuSearcher


class MCPServer:
    """
    Standard MCP server implementation.

    This server implements JSON-RPC 2.0 protocol and provides
    vertical search tools for multiple platforms.
    """

    def __init__(self) -> None:
        """Initialize MCP server."""
        self.manager: Optional[UnifiedSearchManager] = None
        self.request_id = 0

    async def start(self) -> None:
        """
        Start the server and initialize search manager.

        This method:
        1. Creates UnifiedSearchManager instance
        2. Registers all available platforms (weixin, zhihu)
        3. Initializes browser pool
        """
        self.manager = UnifiedSearchManager()

        # Register platforms
        self.manager.register_platform("weixin", WeixinSearcher(self.manager.browser_pool))
        self.manager.register_platform("zhihu", ZhihuSearcher(self.manager.browser_pool))

        print("Vertical Search MCP Server started", file=sys.stderr)
        print(f"Registered platforms: {self.manager.get_registered_platforms()}", file=sys.stderr)

    async def stop(self) -> None:
        """Stop the server and clean up resources."""
        if self.manager:
            await self.manager.close()
        print("MCP Server stopped", file=sys.stderr)

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
            "protocolVersion": "2025-06-18",
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
                "name": "search_vertical",
                "description": "Search vertical platforms (WeChat, Zhihu, etc.) for articles and content",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "platform": {
                            "type": "string",
                            "description": "Platform to search (weixin, zhihu)",
                            "enum": ["weixin", "zhihu"],
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
                        "time_filter": {
                            "type": "string",
                            "description": "Time filter for results",
                            "enum": ["day", "week", "month", "year"],
                        },
                    },
                    "required": ["platform", "query"],
                },
            }
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
        print(f"handle_call_tool called: request_id={request_id}, params={json.dumps(params, ensure_ascii=False)}", file=sys.stderr)
        
        if not self.manager:
            print("ERROR: Manager not initialized", file=sys.stderr)
            self.send_response(
                request_id,
                None,
                {"code": -32603, "message": "Server not initialized"},
            )
            return

        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        print(f"Tool name: {tool_name}, arguments: {json.dumps(arguments, ensure_ascii=False)}", file=sys.stderr)

        if tool_name == "search_vertical":
            await self._handle_search_vertical(request_id, arguments)
        else:
            self.send_response(
                request_id,
                None,
                {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            )

    async def _handle_search_vertical(
        self, request_id: int, arguments: Dict[str, Any]
    ) -> None:
        """
        Handle search_vertical tool call.

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
        time_filter = arguments.get("time_filter")

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

        # Validate time_filter if provided
        if time_filter and time_filter not in ["day", "week", "month", "year"]:
            self.send_response(
                request_id,
                None,
                {
                    "code": -32602,
                    "message": "time_filter must be one of: day, week, month, year",
                },
            )
            return

        # Execute search
        try:
            print(f"Executing search: platform={platform}, query={query}, max_results={max_results}", file=sys.stderr)
            results = await self.manager.search(
                platform=platform,
                query=query,
                max_results=max_results,
                time_filter=time_filter,
                use_cache=True,
            )

            print(f"Search completed: {len(results)} results found", file=sys.stderr)

            # Format results
            result_text = self._format_search_results(platform, query, results)

            self.send_response(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": result_text,
                        }
                    ]
                },
            )

        except ValueError as e:
            # Parameter validation errors
            print(f"Parameter validation error: {str(e)}", file=sys.stderr)
            self.send_response(
                request_id,
                None,
                {"code": -32602, "message": f"Invalid parameter: {str(e)}"},
            )
        except RuntimeError as e:
            # Search execution errors
            print(f"Search error: {str(e)}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            self.send_response(
                request_id,
                None,
                {"code": -32603, "message": f"Search failed: {str(e)}"},
            )
        except Exception as e:
            # Unexpected errors
            print(f"Unexpected error: {str(e)}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            self.send_response(
                request_id,
                None,
                {"code": -32603, "message": f"Unexpected error: {str(e)}"},
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
            result_text += "\n"

        return result_text

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
                        print(f"Received tool call: {json.dumps(message, ensure_ascii=False)}", file=sys.stderr)
                    await server.handle_request(message)
                except json.JSONDecodeError as e:
                    print(f"JSON parse error: {e}", file=sys.stderr)

            except EOFError:
                break
            except Exception as e:
                print(f"Request handling error: {e}", file=sys.stderr)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())

