"""
Quick test script to verify Google Custom Search API availability.

Usage:
    python test_google_api.py [query]

Example:
    python test_google_api.py "Python async programming"
"""

import asyncio
import os
import sys
from typing import Dict, Any, List, Optional, Tuple
import httpx

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


def check_credentials() -> Tuple[Optional[str], Optional[str]]:
    """
    Check if Google API credentials are set.
    
    Returns:
        Tuple of (api_key, search_engine_id) or (None, None) if missing
    """
    api_key = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
    search_engine_id = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
    
    return api_key, search_engine_id


async def test_google_search(
    api_key: str,
    search_engine_id: str,
    query: str,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """
    Test Google Custom Search API.
    
    Args:
        api_key: Google API key
        search_engine_id: Custom Search Engine ID
        query: Search query
        max_results: Maximum number of results (max 10 per request)
    
    Returns:
        List of search results
    """
    base_url = "https://www.googleapis.com/customsearch/v1"
    results: List[Dict[str, Any]] = []
    
    # Calculate number of requests needed
    results_per_request = 10
    num_requests = (max_results + results_per_request - 1) // results_per_request
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for request_num in range(num_requests):
            start_index = request_num * results_per_request + 1
            remaining = max_results - len(results)
            num = min(results_per_request, remaining)
            
            if num <= 0:
                break
            
            params = {
                "key": api_key,
                "cx": search_engine_id,
                "q": query,
                "num": num,
                "start": start_index,
            }
            
            print(f"{GRAY}  Request {request_num + 1}/{num_requests}: start={start_index}, num={num}{RESET}")
            
            try:
                response = await client.get(base_url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                # Extract items
                items = data.get("items", [])
                print(f"{GREEN}  ✓ Got {len(items)} results{RESET}")
                
                for item in items:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "date": item.get("pagemap", {}).get("metatags", [{}])[0].get("article:published_time", ""),
                    })
                
                # Check if there are more results
                total_results = data.get("searchInformation", {}).get("totalResults", "0")
                print(f"{GRAY}  Total results available: {total_results}{RESET}")
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    print(f"{RED}  ✗ Rate limit exceeded (429){RESET}")
                    print(f"{YELLOW}  Waiting 2 seconds before retry...{RESET}")
                    await asyncio.sleep(2)
                    continue
                elif e.response.status_code == 400:
                    error_data = e.response.json() if e.response.content else {}
                    error_msg = error_data.get("error", {}).get("message", "Invalid request")
                    print(f"{RED}  ✗ Invalid request (400): {error_msg}{RESET}")
                    break
                elif e.response.status_code == 401:
                    print(f"{RED}  ✗ Invalid credentials (401){RESET}")
                    break
                else:
                    print(f"{RED}  ✗ HTTP error {e.response.status_code}: {e}{RESET}")
                    break
            except httpx.RequestError as e:
                print(f"{RED}  ✗ Network error: {e}{RESET}")
                break
            except Exception as e:
                print(f"{RED}  ✗ Unexpected error: {e}{RESET}")
                import traceback
                traceback.print_exc()
                break
    
    return results


def print_results(results: List[Dict[str, Any]]) -> None:
    """Print search results in a formatted way."""
    if not results:
        print(f"{GRAY}  No results found{RESET}")
        return
    
    print(f"\n{GRAY}{'='*80}{RESET}")
    print(f"{BOLD}{GREEN}Found {len(results)} results:{RESET}")
    print(f"{GRAY}{'='*80}{RESET}\n")
    
    for i, result in enumerate(results, 1):
        title = result.get("title", "N/A")
        url = result.get("url", "N/A")
        snippet = result.get("snippet", "")
        date = result.get("date", "")
        
        print(f"{GRAY}[{i}]{RESET} {GREEN}{BOLD}{title}{RESET}")
        print(f"{GRAY}    URL:{RESET} {BLUE}{url}{RESET}")
        if date:
            print(f"{GRAY}    Date:{RESET} {MAGENTA}{date}{RESET}")
        if snippet:
            print(f"{GRAY}    Snippet:{RESET} {CYAN}{snippet[:200]}{'...' if len(snippet) > 200 else ''}{RESET}")
        print()


async def main() -> None:
    """Main function."""
    print(f"{BOLD}{CYAN}Google Custom Search API Test{RESET}\n")
    
    # Check credentials
    api_key, search_engine_id = check_credentials()
    
    if not api_key:
        print(f"{RED}✗ APIKEY_GOOGLE_CUSTOM_SEARCH not set{RESET}")
        print(f"{YELLOW}  Set it with: export APIKEY_GOOGLE_CUSTOM_SEARCH='your-api-key'{RESET}")
        sys.exit(1)
    
    if not search_engine_id:
        print(f"{RED}✗ APIKEY_GOOGLE_SEARCH_ID not set{RESET}")
        print(f"{YELLOW}  Set it with: export APIKEY_GOOGLE_SEARCH_ID='your-search-engine-id'{RESET}")
        sys.exit(1)
    
    print(f"{GREEN}✓ API Key: {api_key[:20]}...{RESET}")
    print(f"{GREEN}✓ Search Engine ID: {search_engine_id}{RESET}\n")
    
    # Get query from command line or use default
    query = sys.argv[1] if len(sys.argv) > 1 else "Python async programming"
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    print(f"{BOLD}Query:{RESET} {CYAN}'{query}'{RESET}")
    print(f"{BOLD}Max Results:{RESET} {CYAN}{max_results}{RESET}\n")
    
    # Test search
    print(f"{GRAY}Testing Google Custom Search API...{RESET}\n")
    
    try:
        results = await test_google_search(api_key, search_engine_id, query, max_results)
        print_results(results)
        
        if results:
            print(f"{GREEN}✓ Test successful! API is working correctly.{RESET}")
        else:
            print(f"{YELLOW}⚠ Test completed but no results returned.{RESET}")
    
    except Exception as e:
        print(f"{RED}✗ Test failed: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

