"""
Integration tests for URL resolver.

This module tests the URL resolution functionality using CDP to extract
real URLs from Sogou redirect links.
"""

import pytest
import logging
from core.browser_pool import BrowserPool
from core.url_resolver import URLResolver
from platforms.weixin_searcher import WeixinSearcher
from platforms.zhihu_searcher import ZhihuSearcher

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)


@pytest.mark.asyncio
async def test_url_resolver_initialization() -> None:
    """Test URLResolver initialization."""
    resolver = URLResolver(
        target_domains=["mp.weixin.qq.com"],
        redirect_timeout=5.0,
        cache_ttl=3600,
    )

    assert resolver.target_domains == ["mp.weixin.qq.com"]
    assert resolver.redirect_timeout == 5.0
    assert resolver.cache_ttl == 3600
    assert len(resolver.cache) == 0


@pytest.mark.asyncio
async def test_url_resolver_cache() -> None:
    """Test URL resolver cache mechanism."""
    resolver = URLResolver(
        target_domains=["mp.weixin.qq.com"],
        cache_ttl=3600,
    )

    # Test cache miss
    cached = resolver._get_cached_url("https://www.sogou.com/link?url=test")
    assert cached is None

    # Test cache set and get
    resolver._cache_url("https://www.sogou.com/link?url=test", "https://mp.weixin.qq.com/test")
    cached = resolver._get_cached_url("https://www.sogou.com/link?url=test")
    assert cached == "https://mp.weixin.qq.com/test"


@pytest.mark.asyncio
async def test_resolve_single_url_weixin() -> None:
    """Test resolving a single WeChat redirect URL."""
    pool = BrowserPool()
    resolver = URLResolver(target_domains=["mp.weixin.qq.com"], redirect_timeout=5.0)

    try:
        # Get a real Sogou redirect URL from a search
        searcher = WeixinSearcher(pool)
        results = await searcher.search("Python", max_results=1)

        if not results or "sogou.com/link" not in results[0].get("url", ""):
            pytest.skip("No Sogou redirect URL found in search results")

        sogou_url = results[0]["url"]
        page = await pool.get_page()

        try:
            resolved_url = await resolver.resolve_url(page, sogou_url)

            # Check if resolution succeeded
            assert resolved_url is not None
            assert "mp.weixin.qq.com" in resolved_url
            assert "sogou.com" not in resolved_url

            # Check cache
            cached = resolver._get_cached_url(sogou_url)
            assert cached == resolved_url

        finally:
            await page.close()

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_resolve_single_url_zhihu() -> None:
    """Test resolving a single Zhihu redirect URL."""
    pool = BrowserPool()
    resolver = URLResolver(target_domains=["zhihu.com"], redirect_timeout=5.0)

    try:
        # Get a real Sogou redirect URL from a search
        searcher = ZhihuSearcher(pool)
        results = await searcher.search("Python", max_results=1)

        if not results or "sogou.com/link" not in results[0].get("url", ""):
            pytest.skip("No Sogou redirect URL found in search results")

        sogou_url = results[0]["url"]
        page = await pool.get_page()

        try:
            resolved_url = await resolver.resolve_url(page, sogou_url)

            # Check if resolution succeeded
            assert resolved_url is not None
            assert "zhihu.com" in resolved_url
            assert "sogou.com" not in resolved_url

        finally:
            await page.close()

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_resolve_urls_batch() -> None:
    """Test batch URL resolution."""
    pool = BrowserPool()
    resolver = URLResolver(target_domains=["mp.weixin.qq.com"], redirect_timeout=5.0)

    try:
        # Get multiple Sogou redirect URLs from a search
        searcher = WeixinSearcher(pool)
        results = await searcher.search("Python", max_results=3)

        if not results:
            pytest.skip("No search results found")

        # Filter Sogou redirect URLs
        sogou_urls = [r["url"] for r in results if "sogou.com/link" in r.get("url", "")]

        if not sogou_urls:
            pytest.skip("No Sogou redirect URLs found in search results")

        page = await pool.get_page()

        try:
            resolved_urls = await resolver.resolve_urls_batch(page, sogou_urls[:2])

            # Check results
            assert len(resolved_urls) == 2
            for resolved_url in resolved_urls:
                if resolved_url:
                    assert "mp.weixin.qq.com" in resolved_url
                    assert "sogou.com" not in resolved_url

        finally:
            await page.close()

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_resolve_success_rate() -> None:
    """Test URL resolution success rate."""
    pool = BrowserPool()
    resolver = URLResolver(target_domains=["mp.weixin.qq.com"], redirect_timeout=5.0)

    try:
        # Get multiple URLs
        searcher = WeixinSearcher(pool)
        results = await searcher.search("Python", max_results=10)

        if not results:
            pytest.skip("No search results found")

        sogou_urls = [r["url"] for r in results if "sogou.com/link" in r.get("url", "")]

        if len(sogou_urls) < 5:
            pytest.skip(f"Not enough Sogou redirect URLs found: {len(sogou_urls)}")

        page = await pool.get_page()

        try:
            resolved_urls = await resolver.resolve_urls_batch(page, sogou_urls[:5])

            # Count successful resolutions
            success_count = sum(
                1
                for url in resolved_urls
                if url and "mp.weixin.qq.com" in url and "sogou.com" not in url
            )

            success_rate = success_count / len(resolved_urls)

            # Success rate should be > 90%
            assert success_rate >= 0.9, f"Success rate {success_rate:.2%} < 90%"

        finally:
            await page.close()

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_resolve_performance() -> None:
    """Test URL resolution performance."""
    import time

    pool = BrowserPool()
    resolver = URLResolver(target_domains=["mp.weixin.qq.com"], redirect_timeout=5.0)

    try:
        searcher = WeixinSearcher(pool)
        results = await searcher.search("Python", max_results=1)

        if not results or "sogou.com/link" not in results[0].get("url", ""):
            pytest.skip("No Sogou redirect URL found")

        sogou_url = results[0]["url"]
        page = await pool.get_page()

        try:
            start_time = time.time()
            resolved_url = await resolver.resolve_url(page, sogou_url)
            elapsed = time.time() - start_time

            # Single URL resolution should be < 3 seconds
            assert elapsed < 3.0, f"Resolution took {elapsed:.2f}s, expected < 3s"
            assert resolved_url is not None

            # Second resolution should be much faster (cached)
            start_time = time.time()
            resolved_url2 = await resolver.resolve_url(page, sogou_url)
            elapsed_cached = time.time() - start_time

            assert resolved_url2 == resolved_url
            assert (
                elapsed_cached < 0.1
            ), f"Cached resolution took {elapsed_cached:.2f}s, expected < 0.1s"

        finally:
            await page.close()

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_batch_resolve_performance() -> None:
    """Test batch URL resolution performance."""
    import time

    pool = BrowserPool()
    resolver = URLResolver(target_domains=["mp.weixin.qq.com"], redirect_timeout=5.0)

    try:
        searcher = WeixinSearcher(pool)
        results = await searcher.search("Python", max_results=10)

        if not results:
            pytest.skip("No search results found")

        sogou_urls = [r["url"] for r in results if "sogou.com/link" in r.get("url", "")]

        if len(sogou_urls) < 5:
            pytest.skip(f"Not enough Sogou redirect URLs: {len(sogou_urls)}")

        page = await pool.get_page()

        try:
            start_time = time.time()
            resolved_urls = await resolver.resolve_urls_batch(page, sogou_urls[:5])
            elapsed = time.time() - start_time

            # 5 URLs should be resolved in < 15 seconds
            assert elapsed < 15.0, f"Batch resolution took {elapsed:.2f}s, expected < 15s"
            assert len(resolved_urls) == 5

        finally:
            await page.close()

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_weixin_search_with_url_resolution() -> None:
    """Test WeChat search with URL resolution integrated."""
    pool = BrowserPool()
    searcher = WeixinSearcher(pool)

    try:
        results = await searcher.search("Python", max_results=5)

        assert len(results) > 0

        # Check that URLs are resolved (not Sogou redirect links)
        for result in results:
            url = result.get("url", "")
            assert url, "URL should not be empty"
            # URLs should be real WeChat links, not Sogou redirects
            if "mp.weixin.qq.com" in url:
                assert "sogou.com" not in url, f"URL should not contain sogou.com: {url}"

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_zhihu_search_with_url_resolution() -> None:
    """Test Zhihu search with URL resolution integrated."""
    pool = BrowserPool()
    searcher = ZhihuSearcher(pool)

    try:
        results = await searcher.search("Python", max_results=5)

        assert len(results) > 0

        # Check that URLs are resolved (not Sogou redirect links)
        for result in results:
            url = result.get("url", "")
            assert url, "URL should not be empty"
            # URLs should be real Zhihu links, not Sogou redirects
            if "zhihu.com" in url:
                assert "sogou.com" not in url, f"URL should not contain sogou.com: {url}"

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_fallback_strategy() -> None:
    """Test fallback strategy when CDP fails."""
    pool = BrowserPool()
    searcher = WeixinSearcher(pool)

    try:
        results = await searcher.search("Python", max_results=3)

        if not results:
            pytest.skip("No search results found")

        # Even if CDP fails, fallback should work
        # This test verifies that the system gracefully handles CDP failures
        assert len(results) > 0

        # All results should have URLs (either resolved or original)
        for result in results:
            assert "url" in result
            assert result["url"], "URL should not be empty"

    finally:
        await pool.close()
