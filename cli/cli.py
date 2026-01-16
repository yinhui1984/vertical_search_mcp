"""
Command-line interface for vertical search.

Main entry point for the CLI tool.
"""

import asyncio
import argparse
import sys
import logging
from pathlib import Path
from typing import List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import logger setup first
from core.logger import setup_logger, get_logger, RollingConsoleHandler

# Import other modules
from core.search_manager import UnifiedSearchManager
from core.initializer import register_platforms
from core.content_compressor import ContentCompressor
from cli.output import TextFormatter, ProgressDisplay


def _close_rolling_console_handler() -> None:
    """
    Close the RollingConsoleHandler and ensure clean output.
    
    This function finds and removes the RollingConsoleHandler from the logger,
    allowing normal print() statements to work without interference.
    Calling this multiple times is safe (idempotent).
    """
    logger = logging.getLogger("vertical_search")
    handlers_removed = False
    for handler in logger.handlers[:]:
        if isinstance(handler, RollingConsoleHandler):
            handler.close()
            logger.removeHandler(handler)
            handlers_removed = True
    
    # Add a newline to ensure cursor is at a clean position (only if handlers were removed)
    if handlers_removed:
        sys.stderr.write("\n")
        sys.stderr.flush()


class VerticalSearchCLI:
    """
    Command-line interface for vertical search.
    
    Provides a user-friendly CLI that wraps UnifiedSearchManager.
    """
    
    def __init__(self) -> None:
        """Initialize CLI."""
        self.manager: Optional[UnifiedSearchManager] = None
        self.logger = get_logger("vertical_search.cli")
        self.content_compressor: Optional[ContentCompressor] = None
    
    async def initialize(self) -> None:
        """
        Initialize search manager and register platforms.
        
        Uses the shared initialization logic from core.initializer.
        """
        self.manager = UnifiedSearchManager()
        register_platforms(self.manager, self.logger)
        
        # Initialize content compressor for summarization
        self.content_compressor = ContentCompressor()
    
    async def close(self) -> None:
        """Clean up resources."""
        if self.content_compressor:
            await self.content_compressor.close()
        if self.manager:
            await self.manager.close()
    
    def list_platforms(self) -> List[str]:
        """
        List available platforms.
        
        Returns:
            List of registered platform names
        """
        if not self.manager:
            return []
        return self.manager.get_registered_platforms()
    
    def _parse_platforms(self, platform_str: str) -> List[str]:
        """
        Parse platform string into list of platform names.
        
        Supports:
        - "all" -> all registered platforms
        - "weixin" -> ["weixin"]
        - "weixin,google" -> ["weixin", "google"]
        
        Args:
            platform_str: Platform string to parse
            
        Returns:
            List of platform names
            
        Raises:
            ValueError: If platform string is invalid
        """
        if not platform_str or not platform_str.strip():
            platform_str = "all"
        
        platform_str = platform_str.strip().lower()
        
        if not self.manager:
            raise RuntimeError("Manager not initialized")
        
        registered_platforms = self.manager.get_registered_platforms()
        
        if not registered_platforms:
            raise ValueError("No platforms are registered")
        
        if platform_str == "all":
            return registered_platforms
        
        platforms = [p.strip() for p in platform_str.split(",")]
        platforms = [p for p in platforms if p]
        
        if not platforms:
            raise ValueError("No platforms specified")
        
        invalid_platforms = [p for p in platforms if p not in registered_platforms]
        if invalid_platforms:
            raise ValueError(
                f"Invalid platform(s): {invalid_platforms}. "
                f"Available platforms: {registered_platforms}"
            )
        
        return platforms
    
    async def search(
        self,
        query: str,
        platforms: List[str],
        max_results: int = 10,
        include_content: bool = True,
        progress_display: Optional[ProgressDisplay] = None,
    ) -> List[dict]:
        """
        Execute search on specified platforms.
        
        Args:
            query: Search query string
            platforms: List of platform names to search
            max_results: Maximum number of results (total across all platforms)
            include_content: Whether to include full article content
            progress_display: Optional progress display handler
            
        Returns:
            List of search result dictionaries
        """
        if not self.manager:
            raise RuntimeError("Manager not initialized")
        
        total_platforms = len(platforms)
        all_results: List[dict] = []
        
        # Multi-platform search
        if total_platforms > 1:
            results_per_platform = max_results // total_platforms
            remaining = max_results % total_platforms
            
            for idx, platform_name in enumerate(platforms):
                current_max = results_per_platform
                if idx == total_platforms - 1:
                    current_max += remaining
                
                if progress_display:
                    progress_display.show_platform_progress(
                        idx + 1, total_platforms, platform_name, "Searching..."
                    )
                
                try:
                    # Create progress callback
                    progress_callback = None
                    if progress_display:
                        progress_callback = progress_display.create_progress_callback(
                            platform_name, idx, total_platforms
                        )
                    
                    results = await self.manager.search(
                        platform=platform_name,
                        query=query,
                        max_results=current_max,
                        use_cache=True,
                        include_content=include_content,
                        progress_callback=progress_callback,
                    )
                    
                    # Mark each result with its source platform
                    for result in results:
                        result["platform"] = platform_name
                    
                    all_results.extend(results)
                    
                    if progress_display:
                        progress_display.show_platform_progress(
                            idx + 1, total_platforms, platform_name, f"Found {len(results)} results"
                        )
                
                except Exception as e:
                    self.logger.error(f"Platform {platform_name} failed: {e}", exc_info=True)
                    if progress_display:
                        progress_display.show_platform_progress(
                            idx + 1, total_platforms, platform_name, f"Failed: {str(e)}"
                        )
            
            # Deduplicate by URL
            seen_urls = set()
            deduplicated = []
            for result in all_results:
                url = result.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    deduplicated.append(result)
            
            results = deduplicated[:max_results]
        
        else:
            # Single platform search
            platform_name = platforms[0]
            
            progress_callback = None
            if progress_display:
                progress_callback = progress_display.create_progress_callback(platform_name, 0, 1)
            
            results = await self.manager.search(
                platform=platform_name,
                query=query,
                max_results=max_results,
                use_cache=True,
                include_content=include_content,
                progress_callback=progress_callback,
            )
        
        # Summarize content if include_content is True
        if include_content and results and self.content_compressor:
            results = await self._summarize_results(results, progress_display)
        
        return results
    
    async def _summarize_results(
        self, results: List[dict], progress_display: Optional[ProgressDisplay] = None
    ) -> List[dict]:
        """
        Summarize article content for CLI output concurrently.
        
        Args:
            results: List of search result dictionaries with content
            progress_display: Optional progress display handler
            
        Returns:
            List of results with summarized content
        """
        if not self.content_compressor:
            return results
        
        articles_with_content = [r for r in results if r.get("content")]
        if not articles_with_content:
            return results
        
        total = len(articles_with_content)
        
        # Show summary start message
        if progress_display:
            print(
                f"{progress_display.GRAY}Summarizing {total} articles concurrently...{progress_display.RESET}",
                file=sys.stderr,
            )
        
        # Use semaphore to limit concurrent API calls (avoid rate limiting)
        # Default to 3 concurrent summaries to balance speed and API limits
        semaphore = asyncio.Semaphore(3)
        summarized_count = 0
        
        async def summarize_one(result: dict, index: int) -> None:
            """Summarize a single article."""
            nonlocal summarized_count
            content = result.get("content", "")
            if not content:
                return
            
            title = result.get("title", "Unknown")
            
            async with semaphore:
                try:
                    summary, status = await self.content_compressor.summarize_content(
                        content, max_words=150
                    )
                    result["content"] = summary
                    result["content_status"] = status
                    self.logger.debug(f"Summarized article '{title}': {status}")
                except Exception as e:
                    self.logger.warning(f"Failed to summarize article '{title}': {e}")
                    # Keep original content on failure, but truncate it
                    result["content"] = content[:600] + "..." if len(content) > 600 else content
                    result["content_status"] = "truncated"
                
                # Update progress
                summarized_count += 1
                if progress_display:
                    title_display = title[:50] + "..." if len(title) > 50 else title
                    print(
                        f"{progress_display.GRAY}Summarized {summarized_count}/{total}: '{title_display}'{progress_display.RESET}",
                        file=sys.stderr,
                    )
        
        # Summarize all articles concurrently
        await asyncio.gather(*[summarize_one(result, i) for i, result in enumerate(articles_with_content)])
        
        return results


def create_parser() -> argparse.ArgumentParser:
    """
    Create command-line argument parser.
    
    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description="Vertical search CLI - Search across multiple platforms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search
  vertical-search "Python 异步编程"
  
  # Search specific platform
  vertical-search "Python" --platform weixin
  
  # Search multiple platforms
  vertical-search "Python" --platform weixin,google
  
  # Search all platforms
  vertical-search "Python" --platform all
  
  # Without content (faster)
  vertical-search "Python" --no-content
  
  # List available platforms
  vertical-search --list-platforms
        """,
    )
    
    parser.add_argument(
        "query",
        nargs="?",
        help="Search query string",
    )
    
    parser.add_argument(
        "--platform",
        "-p",
        type=str,
        default="all",
        help="Platform(s) to search: 'all' (default), single platform like 'weixin', "
             "or comma-separated like 'weixin,google'",
    )
    
    parser.add_argument(
        "--max-results",
        "-n",
        type=int,
        default=10,
        help="Maximum number of results (default: 10)",
    )
    
    parser.add_argument(
        "--no-content",
        action="store_true",
        help="Do not fetch full article content (faster)",
    )
    
    parser.add_argument(
        "--list-platforms",
        action="store_true",
        help="List available platforms and exit",
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    
    return parser


async def main_async(args: argparse.Namespace) -> int:
    """
    Async main function.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Determine if we should use rolling console
    # Only use it for actual search operations, not for simple commands
    use_rolling = not args.list_platforms
    
    try:
        # Setup logging
        log_level = logging.DEBUG if args.verbose else logging.INFO
        setup_logger(
            name="vertical_search",
            log_level=log_level,
            use_rolling_console=use_rolling,  # Only for search operations
            rolling_console_lines=4,
            force_reconfigure=True,
        )
        
        cli = VerticalSearchCLI()
        await cli.initialize()
        
        # List platforms if requested
        if args.list_platforms:
            platforms = cli.list_platforms()
            formatter = TextFormatter()
            print(formatter.format_platform_list(platforms))
            return 0
        
        # Validate query
        if not args.query:
            print("Error: Query is required. Use --help for usage information.", file=sys.stderr)
            return 1
        
        # Parse platforms
        try:
            platforms = cli._parse_platforms(args.platform)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        
        # Create formatter and progress display
        formatter = TextFormatter()
        progress_display = ProgressDisplay(verbose=args.verbose)
        
        # Show search start
        progress_display.show_search_start(args.query, platforms)
        
        # Execute search
        try:
            results = await cli.search(
                query=args.query,
                platforms=platforms,
                max_results=args.max_results,
                include_content=not args.no_content,
                progress_display=progress_display,
            )
            
            # Close rolling console handler before printing results
            # This ensures output is not interfered with by the rolling log display
            if use_rolling:
                _close_rolling_console_handler()
            
            # Format and print results
            output = formatter.format_results(
                query=args.query,
                platforms=platforms,
                results=results,
            )
            print(output)
            
            return 0
        
        except Exception as e:
            # Close rolling console handler before error output
            if use_rolling:
                _close_rolling_console_handler()
            print(f"Error: Search failed: {e}", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()
            return 1
    
    finally:
        # Ensure rolling console is properly closed (safe to call multiple times)
        if use_rolling:
            _close_rolling_console_handler()
        await cli.close()
    
    return 0


def main() -> int:
    """
    Main entry point for CLI.
    
    Returns:
        Exit code
    """
    parser = create_parser()
    args = parser.parse_args()
    
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
