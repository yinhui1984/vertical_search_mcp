"""
Quick test script for Google Custom Search platform.

Usage:
    python test_google.py [query] [max_results]

Examples:
    python test_google.py
    python test_google.py "Python async programming" 10
    python test_google.py "web3 trends 2026" 15

Environment variables (required):
    APIKEY_GOOGLE_CUSTOM_SEARCH: Google Custom Search API key
    APIKEY_GOOGLE_SEARCH_ID: Google Custom Search Engine ID
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.search_manager import UnifiedSearchManager
from platforms.google_searcher import GoogleSearcher

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
    print(f"{BOLD}{CYAN}Google Search{RESET}: {GRAY}'{query}'{RESET}")
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
            platform="google",
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
    """Main function to run Google search test."""
    # Check credentials
    google_api_key = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
    google_search_id = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
    
    if not google_api_key:
        print(f"{RED}✗ APIKEY_GOOGLE_CUSTOM_SEARCH not set{RESET}")
        print(f"{YELLOW}  Set it with: export APIKEY_GOOGLE_CUSTOM_SEARCH='your-api-key'{RESET}")
        sys.exit(1)
    
    if not google_search_id:
        print(f"{RED}✗ APIKEY_GOOGLE_SEARCH_ID not set{RESET}")
        print(f"{YELLOW}  Set it with: export APIKEY_GOOGLE_SEARCH_ID='your-search-engine-id'{RESET}")
        sys.exit(1)

    # Get query from command line or use default
    query = sys.argv[1] if len(sys.argv) > 1 else "web3 trends 2026"
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    print(f"{BOLD}{CYAN}Google Custom Search Test{RESET}\n")
    print(f"{GREEN}✓ API Key: {google_api_key[:20]}...{RESET}")
    print(f"{GREEN}✓ Search Engine ID: {google_search_id}{RESET}\n")
    print(f"{BOLD}Query:{RESET} {CYAN}'{query}'{RESET}")
    print(f"{BOLD}Max Results:{RESET} {CYAN}{max_results}{RESET}\n")

    manager = UnifiedSearchManager()
    manager.register_platform("google", GoogleSearcher(manager.browser_pool))

    try:
        await test_search(manager, query, max_results)
    finally:
        await manager.close()
        print(f"{GREEN}Done{RESET}")


if __name__ == "__main__":
    asyncio.run(main())

