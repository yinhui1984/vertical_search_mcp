"""
Quick test script for Zhihu platform search.

Usage:
    python test_zhihu.py [query] [max_results]

Examples:
    python test_zhihu.py
    python test_zhihu.py "Python 异步编程" 10
    python test_zhihu.py "机器学习" 15
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.search_manager import UnifiedSearchManager
from platforms.zhihu_searcher import ZhihuSearcher

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
    manager: UnifiedSearchManager,
    query: str,
    max_results: int = 15,
) -> None:
    """Test search and print results."""
    print(f"\n{GRAY}{'='*80}{RESET}")
    print(f"{BOLD}{CYAN}Zhihu Search{RESET}: {GRAY}'{query}'{RESET}")
    print(f"{GRAY}{'='*80}{RESET}")

    # Progress tracking
    last_stage = ""
    last_percentage = -1

    async def progress_callback(stage: str, message: str, current: int, total: int) -> None:
        """Progress callback to show search progress."""
        nonlocal last_stage, last_percentage
        percentage = int(current / total * 100) if total > 0 else 0
        
        # Only print if stage or percentage changed significantly
        if stage != last_stage or abs(percentage - last_percentage) >= 10:
            stage_colors = {
                "searching": CYAN,
                "fetching_content": YELLOW,
                "compressing": MAGENTA,
            }
            stage_color = stage_colors.get(stage, GRAY)
            print(f"{GRAY}  [{stage_color}{stage.upper()}{RESET}{GRAY}] {message} ({current}/{total}, {percentage}%){RESET}")
            last_stage = stage
            last_percentage = percentage

    try:
        results = await manager.search(
            platform="zhihu",
            query=query,
            max_results=max_results,
            include_content=True,
            progress_callback=progress_callback,
        )

        if not results:
            print(f"{GRAY}  No results{RESET}")
            return

        print(f"{GRAY}  Found {len(results)} results{RESET}\n")

        for i, result in enumerate(results, 1):
            title = result.get("title", "N/A")
            url = result.get("url", "N/A")
            content = result.get("content", "")
            content_status = result.get("content_status", "")
            snippet = result.get("snippet", "")
            date = result.get("date", "")

            print(f"{GRAY}[{i}]{RESET} {GREEN}{BOLD}{title}{RESET}")
            print(f"{GRAY}    URL:{RESET} {BLUE}{url}{RESET}")
            
            if date:
                print(f"{GRAY}    Date:{RESET} {MAGENTA}{date}{RESET}")
            if snippet:
                print(f"{GRAY}    Snippet:{RESET} {CYAN}{snippet[:200]}{'...' if len(snippet) > 200 else ''}{RESET}")
            
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
    """Main function to run Zhihu search test."""
    # Get query from command line or use default
    query = sys.argv[1] if len(sys.argv) > 1 else "Python 异步编程"
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    print(f"{BOLD}{CYAN}Zhihu Search Test{RESET}\n")
    print(f"{BOLD}Query:{RESET} {CYAN}'{query}'{RESET}")
    print(f"{BOLD}Max Results:{RESET} {CYAN}{max_results}{RESET}\n")

    manager = UnifiedSearchManager()
    manager.register_platform("zhihu", ZhihuSearcher(manager.browser_pool))

    try:
        await test_search(manager, query, max_results)
    finally:
        await manager.close()
        print(f"{GREEN}Done{RESET}")


if __name__ == "__main__":
    asyncio.run(main())

