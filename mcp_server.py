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
from typing import Any, Dict, List, Optional

from core.logger import setup_logger, get_logger
from core.search_manager import UnifiedSearchManager
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
        self.request_id = 0
        self.logger = get_logger("vertical_search.mcp_server")
        
        # Tool name aliases mapping
        # Maps alternative names to the canonical tool name
        self.tool_aliases: Dict[str, str] = {
            "垂直搜索": "search_vertical",
            "vertical_search": "search_vertical",
            "search_vertical": "search_vertical",
        }

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
                "description": "垂直搜索 (Vertical Search): Search vertical platforms (WeChat, Zhihu, etc.) for articles and content. Also known as: 垂直搜索, vertical_search",
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
                        "time_filter": {
                            "type": "string",
                            "description": "Time filter for results",
                            "enum": ["day", "week", "month", "year"],
                        },
                        "include_content": {
                            "type": "boolean",
                            "description": "Whether to include full article content (default: true). Content is automatically compressed if it exceeds token limits.",
                            "default": True,
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
        
        # Resolve tool name alias to canonical name
        canonical_name = self.tool_aliases.get(tool_name, tool_name)
        
        if canonical_name != tool_name:
            self.logger.debug(f"Tool name alias resolved: '{tool_name}' -> '{canonical_name}'")
        
        self.logger.info(f"Tool call: {canonical_name} (requested as: {tool_name}), arguments: {json.dumps(arguments, ensure_ascii=False)}")

        if canonical_name == "search_vertical":
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
            start_time = time.time()
            self.logger.info(f"Executing search: platform={platform}, query={query}, max_results={max_results}, time_filter={time_filter}")
            
            results = await self.manager.search(
                platform=platform,
                query=query,
                max_results=max_results,
                time_filter=time_filter,
                use_cache=True,
                include_content=include_content,
            )

            elapsed_time = time.time() - start_time
            self.logger.info(f"Search completed: {len(results)} results found in {elapsed_time:.2f}s (platform={platform}, query={query})")

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
            self.logger.warning(f"Parameter validation error: {str(e)} (platform={platform}, query={query})")
            self.send_response(
                request_id,
                None,
                {"code": -32602, "message": f"Invalid parameter: {str(e)}"},
            )
        except RuntimeError as e:
            # Search execution errors
            self.logger.error(f"Search error: {str(e)} (platform={platform}, query={query})", exc_info=True)
            self.send_response(
                request_id,
                None,
                {"code": -32603, "message": f"Search failed: {str(e)}"},
            )
        except Exception as e:
            # Unexpected errors
            self.logger.error(f"Unexpected error: {str(e)} (platform={platform}, query={query})", exc_info=True)
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

