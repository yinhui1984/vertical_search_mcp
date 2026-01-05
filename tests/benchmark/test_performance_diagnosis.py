"""
Performance diagnosis tool for WeixinSearcher.

This tool helps identify where time is being spent during searches.
It breaks down the search process into stages and measures each one.
"""

import time
import pytest
from core.browser_pool import BrowserPool
from platforms.weixin_searcher import WeixinSearcher
from playwright.async_api import Page


class TestPerformanceDiagnosis:
    """Diagnostic tests to identify performance bottlenecks."""

    @pytest.fixture
    async def browser_pool(self) -> BrowserPool:
        """Create and initialize browser pool."""
        pool = BrowserPool()
        await pool.init()
        yield pool
        await pool.close()

    @pytest.fixture
    def searcher(self, browser_pool: BrowserPool) -> WeixinSearcher:
        """Create WeixinSearcher instance."""
        return WeixinSearcher(browser_pool)

    @pytest.mark.asyncio
    async def test_breakdown_search_timing(self, searcher: WeixinSearcher) -> None:
        """
        Break down search timing into stages.

        This helps identify where time is being spent:
        - Browser initialization (first search only)
        - Page creation
        - Navigation
        - Waiting for selectors
        - Parsing results
        """
        import asyncio

        query = "Python"
        max_results = 5

        # Stage 1: Get page (browser pool)
        start_page = time.time()
        page = await searcher.browser_pool.get_page()
        time_page = time.time() - start_page

        try:
            # Build URL
            from urllib.parse import urlencode

            params = {
                "query": query,
                "type": "2",
                "ie": "utf8",
            }
            url = f"{searcher.base_url}?{urlencode(params)}"

            # Stage 2: Navigate
            start_nav = time.time()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            time_nav = time.time() - start_nav

            # Stage 3: Wait for selectors
            start_wait = time.time()
            selectors = searcher.config.get("selectors", {}).get("article_list", [])
            page_loaded = False
            selector_used = None

            for selector in selectors:
                try:
                    await page.wait_for_selector(selector, timeout=2000, state="visible")
                    page_loaded = True
                    selector_used = selector
                    break
                except Exception:
                    continue

            time_wait = time.time() - start_wait

            # Stage 4: Parse results
            start_parse = time.time()
            results = await searcher._parse_results(page, max_results)
            time_parse = time.time() - start_parse

            total_time = time_page + time_nav + time_wait + time_parse

            print(f"\n{'='*60}")
            print(f"Performance Breakdown for query: '{query}'")
            print(f"{'='*60}")
            print(f"1. Page creation:        {time_page:6.2f}s ({time_page/total_time*100:5.1f}%)")
            print(f"2. Navigation:           {time_nav:6.2f}s ({time_nav/total_time*100:5.1f}%)")
            print(f"3. Wait for selectors:   {time_wait:6.2f}s ({time_wait/total_time*100:5.1f}%)")
            print(f"   - Selector used:      {selector_used or 'None'}")
            print(f"4. Parse results:        {time_parse:6.2f}s ({time_parse/total_time*100:5.1f}%)")
            print(f"{'='*60}")
            print(f"Total time:              {total_time:6.2f}s")
            print(f"Results found:           {len(results)}")
            print(f"{'='*60}\n")

            # Check for potential issues
            if time_nav > 10.0:
                print("⚠️  WARNING: Navigation took > 10s - possible network/anti-bot issue")
            if time_wait > 5.0:
                print("⚠️  WARNING: Waiting for selectors took > 5s - selector may be wrong")
            if time_parse > 2.0:
                print("⚠️  WARNING: Parsing took > 2s - may have too many elements")

        finally:
            await page.close()

    @pytest.mark.asyncio
    async def test_check_anti_bot_detection(self, browser_pool: BrowserPool) -> None:
        """
        Check if we're being blocked by anti-bot measures.

        This test:
        1. Loads the search page
        2. Checks for common anti-bot indicators:
           - Captcha presence
           - Block messages
           - Redirects to verification pages
        """
        page = await browser_pool.get_page()

        try:
            url = "https://weixin.sogou.com/weixin?query=Python&type=2&ie=utf8"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Check page title and content for anti-bot indicators
            title = await page.title()
            content = await page.content()

            # Check for common anti-bot indicators
            anti_bot_indicators = [
                "验证码",
                "captcha",
                "验证",
                "访问过于频繁",
                "请稍后再试",
                "blocked",
                "403",
                "Forbidden",
            ]

            found_indicators = []
            for indicator in anti_bot_indicators:
                if indicator.lower() in title.lower() or indicator.lower() in content.lower():
                    found_indicators.append(indicator)

            print(f"\n{'='*60}")
            print(f"Anti-Bot Detection Check")
            print(f"{'='*60}")
            print(f"Page title: {title}")
            print(f"URL: {page.url}")

            if found_indicators:
                print(f"\n⚠️  WARNING: Possible anti-bot detection!")
                print(f"Found indicators: {', '.join(found_indicators)}")
            else:
                print(f"\n✅ No obvious anti-bot indicators found")

            # Check if we got redirected
            if "weixin.sogou.com" not in page.url:
                print(f"\n⚠️  WARNING: Redirected to different domain: {page.url}")

            print(f"{'='*60}\n")

        finally:
            await page.close()

    @pytest.mark.asyncio
    async def test_network_timing(self, browser_pool: BrowserPool) -> None:
        """
        Measure network timing for the search request.

        This helps identify if slowness is due to network issues.
        """
        page = await browser_pool.get_page()

        try:
            url = "https://weixin.sogou.com/weixin?query=Python&type=2&ie=utf8"

            # Enable request/response tracking
            requests_timing = []

            async def handle_request(request):
                if "weixin.sogou.com" in request.url:
                    requests_timing.append(
                        {
                            "type": "request",
                            "url": request.url,
                            "time": time.time(),
                        }
                    )

            async def handle_response(response):
                if "weixin.sogou.com" in response.url:
                    requests_timing.append(
                        {
                            "type": "response",
                            "url": response.url,
                            "status": response.status,
                            "time": time.time(),
                        }
                    )

            page.on("request", handle_request)
            page.on("response", handle_response)

            start = time.time()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            elapsed = time.time() - start

            print(f"\n{'='*60}")
            print(f"Network Timing Analysis")
            print(f"{'='*60}")
            print(f"Total navigation time: {elapsed:.2f}s")
            print(f"\nRequests/Responses tracked: {len(requests_timing)}")

            # Find main document request
            main_request = None
            for item in requests_timing:
                if item["type"] == "request" and "weixin.sogou.com/weixin" in item["url"]:
                    main_request = item
                    break

            if main_request:
                # Find corresponding response
                for item in requests_timing:
                    if (
                        item["type"] == "response"
                        and item["url"] == main_request["url"]
                    ):
                        request_time = main_request["time"]
                        response_time = item["time"]
                        network_time = response_time - request_time
                        print(f"\nMain request timing:")
                        print(f"  Request sent:     {request_time:.3f}")
                        print(f"  Response received: {response_time:.3f}")
                        print(f"  Network time:     {network_time:.2f}s")
                        print(f"  Status code:      {item['status']}")

            print(f"{'='*60}\n")

        finally:
            await page.close()

