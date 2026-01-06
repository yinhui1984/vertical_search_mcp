"""
Quick test script to search on Weixin platform.

Usage:
    python quick_test.py
"""

import asyncio
from core.search_manager import UnifiedSearchManager
from platforms.weixin_searcher import WeixinSearcher

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
GRAY = "\033[90m"
RED = "\033[31m"


async def test_search(
    platform_name: str,
    manager: UnifiedSearchManager,
    platform: str,
    query: str,
    max_results: int = 15,
) -> None:
    """Test search and print results."""
    print(f"\n{GRAY}{'='*80}{RESET}")
    print(f"{BOLD}{CYAN}{platform_name}{RESET}: {GRAY}'{query}'{RESET}")
    print(f"{GRAY}{'='*80}{RESET}")

    try:
        results = await manager.search(
            platform=platform,
            query=query,
            max_results=max_results,
            include_content=True,
        )

        if not results:
            print(f"{GRAY}  No results{RESET}")
            return

        print(f"{GRAY}  Found {len(results)} results{RESET}\n")

        for i, result in enumerate(results, 1):
            # MCP returned data - highlight with colors
            title = result.get("title", "N/A")
            url = result.get("url", "N/A")
            content = result.get("content", "")
            content_status = result.get("content_status", "")

            # Script label (gray) + MCP data (colored)
            print(f"{GRAY}[{i}]{RESET} {GREEN}{BOLD}{title}{RESET}")
            print(f"{GRAY}    URL:{RESET} {BLUE}{url}{RESET}")
            
            if content:
                # Status color coding
                if content_status == "truncated":
                    status_color = RED
                elif content_status in ["compressed", "batch_compressed"]:
                    status_color = YELLOW
                elif content_status == "fetch_failed":
                    status_color = RED
                else:
                    status_color = GREEN
                
                status_text = f" {status_color}[{content_status}]{RESET}" if content_status else ""
                print(f"{GRAY}    Content{status_text}:{RESET} {GRAY}{len(content)} chars{RESET}")
                print(f"{CYAN}{content}{RESET}")
            else:
                print(f"{GRAY}    Content:{RESET} {RED}None{RESET}")
            print()

    except Exception as e:
        print(f"{RED}  ERROR: {e}{RESET}")
        import traceback
        traceback.print_exc()


async def main() -> None:
    """Main function to run quick tests."""
    query = "cursor mcp"
    max_results = 15

    manager = UnifiedSearchManager()
    manager.register_platform("weixin", WeixinSearcher(manager.browser_pool))

    try:
        await test_search("Weixin", manager, "weixin", query, max_results)
    finally:
        await manager.close()
        print(f"{GREEN}Done{RESET}")


if __name__ == "__main__":
    asyncio.run(main())

