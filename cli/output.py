"""
Text output formatter for CLI.

Provides colored text output with progress display.
"""

import sys
from typing import List, Dict, Any


class TextFormatter:
    """
    Text formatter with colored output.
    
    Provides simple, clean text output suitable for terminal display.
    """
    
    # ANSI color codes - GitHub-inspired professional palette
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    # Primary text colors
    WHITE = "\033[97m"  # Main titles and headers
    LIGHT_GRAY = "\033[37m"  # Secondary text, content
    DIM_GRAY = "\033[90m"  # Metadata, labels
    
    # Accent colors (softer, GitHub-style)
    BLUE = "\033[94m"  # Links, URLs (softer blue)
    GREEN = "\033[92m"  # Success, titles (softer green)
    YELLOW = "\033[93m"  # Warnings, compressed status (softer yellow)
    RED = "\033[91m"  # Errors, truncated status (softer red)
    PURPLE = "\033[95m"  # Platform labels, tags (softer purple)
    
    # Legacy aliases for compatibility
    CYAN = LIGHT_GRAY  # Use light gray instead of bright cyan
    MAGENTA = PURPLE  # Use softer purple
    GRAY = DIM_GRAY  # Use dim gray
    
    def format_results(
        self,
        query: str,
        platforms: List[str],
        results: List[Dict[str, Any]],
    ) -> str:
        """
        Format search results as colored text.
        
        Args:
            query: Search query
            platforms: List of platforms searched
            results: List of result dictionaries
            
        Returns:
            Formatted string
        """
        output = []
        
        # Header
        platform_names = []
        for p in platforms:
            display_name = {"weixin": "WeChat", "zhihu": "Zhihu", "google": "Google"}.get(p, p)
            platform_names.append(display_name)
        
        if len(platforms) > 1:
            platform_display = ", ".join(platform_names)
            output.append(
                f"{self.BOLD}{self.WHITE}Search Results{self.RESET}: {self.LIGHT_GRAY}'{query}'{self.RESET} {self.DIM_GRAY}across {platform_display}{self.RESET}"
            )
        else:
            output.append(
                f"{self.BOLD}{self.WHITE}Search Results{self.RESET}: {self.LIGHT_GRAY}'{query}'{self.RESET} {self.DIM_GRAY}on {platform_names[0]}{self.RESET}"
            )
        
        output.append("")
        
        if not results:
            output.append(f"{self.DIM_GRAY}No results found.{self.RESET}")
            return "\n".join(output)
        
        output.append(f"{self.DIM_GRAY}Found {len(results)} result(s){self.RESET}\n")
        
        # Results
        for i, result in enumerate(results, 1):
            title = result.get("title", "N/A")
            url = result.get("url", "N/A")
            source = result.get("source", "")
            date = result.get("date", "")
            snippet = result.get("snippet", "")
            content = result.get("content", "")
            content_status = result.get("content_status", "")
            result_platform = result.get("platform", "")
            
            output.append(f"{self.DIM_GRAY}[{i}]{self.RESET} {self.BOLD}{self.WHITE}{title}{self.RESET}")
            
            # Show platform for multi-platform results
            if len(platforms) > 1 and result_platform:
                platform_label = {"weixin": "WeChat", "zhihu": "Zhihu", "google": "Google"}.get(
                    result_platform, result_platform
                )
                output.append(
                    f"{self.DIM_GRAY}    Platform:{self.RESET} {self.PURPLE}{platform_label}{self.RESET}"
                )
            
            if source:
                output.append(f"{self.DIM_GRAY}    Source:{self.RESET} {self.LIGHT_GRAY}{source}{self.RESET}")
            if date:
                output.append(f"{self.DIM_GRAY}    Date:{self.RESET} {self.LIGHT_GRAY}{date}{self.RESET}")
            if snippet:
                snippet_text = snippet[:200] + "..." if len(snippet) > 200 else snippet
                output.append(f"{self.DIM_GRAY}    Summary:{self.RESET} {self.LIGHT_GRAY}{snippet_text}{self.RESET}")
            
            output.append(f"{self.DIM_GRAY}    URL:{self.RESET} {self.BLUE}{url}{self.RESET}")
            
            if content:
                # Determine status display
                if content_status == "summarized":
                    status_color = self.GREEN
                    status_label = "Summary"
                elif content_status == "truncated":
                    status_color = self.RED
                    status_label = "Truncated"
                elif content_status in ["compressed", "batch_compressed"]:
                    status_color = self.YELLOW
                    status_label = "Compressed"
                elif content_status == "fetched":
                    status_color = self.GREEN
                    status_label = "Content"
                else:
                    status_color = self.DIM_GRAY
                    status_label = "Content"
                
                status_text = f" {status_color}[{content_status}]{self.RESET}" if content_status else ""
                output.append(
                    f"{self.DIM_GRAY}    {status_label}{status_text}:{self.RESET} {self.DIM_GRAY}{len(content)} chars{self.RESET}"
                )
                # Display content (already summarized, so no need to truncate)
                output.append(f"{self.LIGHT_GRAY}{content}{self.RESET}")
            
            output.append("")
        
        return "\n".join(output)
    
    def format_platform_list(self, platforms: List[str]) -> str:
        """
        Format platform list for display.
        
        Args:
            platforms: List of platform names
            
        Returns:
            Formatted string
        """
        output = ["Available platforms:"]
        for platform in platforms:
            display_name = {"weixin": "WeChat", "zhihu": "Zhihu", "google": "Google"}.get(
                platform, platform
            )
            output.append(f"  - {platform} ({display_name})")
        return "\n".join(output)


class ProgressDisplay:
    """
    Progress display handler for CLI.
    
    Provides simple, non-spammy progress updates.
    """
    
    # GitHub-inspired professional palette
    RESET = "\033[0m"
    DIM_GRAY = "\033[90m"  # Metadata, progress indicators
    LIGHT_GRAY = "\033[37m"  # Secondary text
    BLUE = "\033[94m"  # Primary actions, search messages
    GREEN = "\033[92m"  # Success states
    YELLOW = "\033[93m"  # Warnings
    
    # Legacy aliases for compatibility
    GRAY = DIM_GRAY
    CYAN = BLUE  # Use blue for progress messages
    
    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize progress display.
        
        Args:
            verbose: Whether to show detailed progress
        """
        self.verbose = verbose
        self.last_stage = ""
        self.cache_hit_detected = False
    
    def show_search_start(self, query: str, platforms: List[str]) -> None:
        """
        Show search start message.
        
        Args:
            query: Search query
            platforms: List of platforms to search
        """
        platform_names = []
        for p in platforms:
            display_name = {"weixin": "WeChat", "zhihu": "Zhihu", "google": "Google"}.get(p, p)
            platform_names.append(display_name)
        
        if len(platforms) > 1:
            print(
                f"\n{self.BLUE}Searching{self.RESET} {self.LIGHT_GRAY}'{query}'{self.RESET} {self.DIM_GRAY}across {', '.join(platform_names)}...{self.RESET}",
                file=sys.stderr,
            )
        else:
            print(
                f"\n{self.BLUE}Searching{self.RESET} {self.LIGHT_GRAY}'{query}'{self.RESET} {self.DIM_GRAY}on {platform_names[0]}...{self.RESET}",
                file=sys.stderr,
            )
    
    def show_cache_hit(self) -> None:
        """Show cache hit message."""
        if not self.cache_hit_detected:
            print(f"{self.DIM_GRAY}[Cache hit]{self.RESET} {self.LIGHT_GRAY}Returning cached results{self.RESET}", file=sys.stderr)
            self.cache_hit_detected = True
    
    def show_platform_progress(
        self, platform_num: int, total_platforms: int, platform_name: str, message: str
    ) -> None:
        """
        Show platform progress message.
        
        Args:
            platform_num: Current platform number (1-based)
            total_platforms: Total number of platforms
            platform_name: Name of the platform
            message: Progress message
        """
        if total_platforms > 1:
            display_name = {"weixin": "WeChat", "zhihu": "Zhihu", "google": "Google"}.get(
                platform_name, platform_name
            )
            print(
                f"{self.DIM_GRAY}[{platform_num}/{total_platforms}]{self.RESET} {self.LIGHT_GRAY}{display_name}:{self.RESET} {message}",
                file=sys.stderr,
            )
        elif self.verbose:
            print(f"{self.DIM_GRAY}{message}{self.RESET}", file=sys.stderr)
    
    def create_progress_callback(
        self, platform_name: str, platform_index: int, total_platforms: int
    ):
        """
        Create progress callback function for search manager.
        
        Args:
            platform_name: Name of the platform
            platform_index: Zero-based index of the platform
            total_platforms: Total number of platforms
            
        Returns:
            Async callback function
        """
        async def progress_callback(stage: str, message: str, current: int, total: int) -> None:
            # Detect cache hit
            if "cache hit" in message.lower():
                self.show_cache_hit()
                return
            
            # Only show progress for stage changes or significant updates
            if stage != self.last_stage:
                self.last_stage = stage
                
                # Format message for display
                if total_platforms > 1:
                    display_name = {"weixin": "WeChat", "zhihu": "Zhihu", "google": "Google"}.get(
                        platform_name, platform_name
                    )
                    if stage == "searching" and "found" in message.lower():
                        # Show completion message
                        self.show_platform_progress(
                            platform_index + 1, total_platforms, platform_name, message
                        )
                elif self.verbose:
                    percentage = int((current / total * 100)) if total > 0 else 0
                    print(
                        f"{self.DIM_GRAY}[{stage.upper()}]{self.RESET} {self.LIGHT_GRAY}{message}{self.RESET} {self.DIM_GRAY}({current}/{total}, {percentage}%){self.RESET}",
                        file=sys.stderr,
                    )
        
        return progress_callback
