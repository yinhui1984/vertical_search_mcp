"""
Quick test script to print search results from Weixin and Zhihu platforms.

This script demonstrates basic search functionality and prints results
in a readable format.

Usage:
    python quick_test.py [query] [max_results] [platform]
    
Examples:
    python quick_test.py                    # Search "Python" on both platforms
    python quick_test.py "AI"               # Search "AI" on both platforms
    python quick_test.py "Python" 10        # Search "Python" with 10 results
    python quick_test.py "Python" 5 weixin  # Search only Weixin platform
    python quick_test.py "Python" 5 zhihu   # Search only Zhihu platform
"""

import asyncio
import sys
from core.browser_pool import BrowserPool
from platforms.weixin_searcher import WeixinSearcher
from platforms.zhihu_searcher import ZhihuSearcher


async def test_search(platform_name: str, searcher, query: str, max_results: int = 5) -> None:
    """
    Test search and print results.

    Args:
        platform_name: Name of the platform (for display)
        searcher: Searcher instance
        query: Search query
        max_results: Maximum number of results to return
    """
    print(f"\n{'='*80}")
    print(f"{platform_name} Search Results for: '{query}'")
    print(f"{'='*80}\n")

    try:
        results = await searcher.search(query, max_results=max_results)

        if not results:
            print(f"No results found for '{query}'")
            return

        print(f"Found {len(results)} results:\n")

        for i, result in enumerate(results, 1):
            title = result.get("title", "N/A")
            url = result.get("url", "N/A")
            source = result.get("source", "N/A")
            date = result.get("date", "")
            snippet = result.get("snippet", "")

            print(f"[{i}] {title}")
            print(f"     URL: {url}")
            print(f"     Source: {source}")
            if date:
                print(f"     Date: {date}")
            if snippet:
                # Truncate snippet if too long
                snippet_display = snippet[:100] + "..." if len(snippet) > 100 else snippet
                print(f"     Snippet: {snippet_display}")
            print()

    except Exception as e:
        print(f"Error during search: {e}")


async def main() -> None:
    """Main function to run quick tests."""
    # Parse command line arguments
    query = sys.argv[1] if len(sys.argv) > 1 else "Python"
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    platform = sys.argv[3].lower() if len(sys.argv) > 3 else "both"

    # Validate max_results
    if max_results > 30:
        print("Warning: max_results cannot exceed 30, using 30 instead")
        max_results = 30

    # Initialize browser pool
    pool = BrowserPool()
    await pool.init()

    try:
        if platform in ["both", "weixin", "all"]:
            # Test Weixin search
            weixin_searcher = WeixinSearcher(pool)
            await test_search("Weixin", weixin_searcher, query, max_results=max_results)

        if platform in ["both", "zhihu", "all"]:
            # Test Zhihu search
            zhihu_searcher = ZhihuSearcher(pool)
            await test_search("Zhihu", zhihu_searcher, query, max_results=max_results)

    finally:
        # Clean up
        await pool.close()
        print(f"\n{'='*80}")
        print("Test completed!")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())

