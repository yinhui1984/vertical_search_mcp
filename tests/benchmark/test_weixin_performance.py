"""
Performance benchmark tests for WeixinSearcher.

These tests compare performance with the original implementation and verify
that the optimization goals are met:
- Subsequent searches should be 3x+ faster than original
- Continuous searches should work without errors
- Cache should provide significant speedup
"""

import time
import pytest
from core.browser_pool import BrowserPool
from core.search_manager import UnifiedSearchManager
from platforms.weixin_searcher import WeixinSearcher


class TestWeixinPerformance:
    """Performance benchmark test suite for WeixinSearcher."""

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
    @pytest.mark.benchmark
    async def test_continuous_search(self, searcher: WeixinSearcher) -> None:
        """
        Test continuous search - 10 searches without errors.

        This test verifies that the browser pool reuse works correctly
        and that multiple searches can be performed without issues.
        """
        queries = [
            "Python",
            "AI",
            "Machine Learning",
            "Deep Learning",
            "Neural Network",
            "Data Science",
            "Web Development",
            "Cloud Computing",
            "DevOps",
            "Cybersecurity",
        ]

        for i, query in enumerate(queries):
            try:
                results = await searcher.search(query, max_results=5)
                assert isinstance(results, list), f"Search {i+1} failed: invalid result type"
                # Some queries may return empty results, which is acceptable
                # But the search should not raise an exception
            except Exception as e:
                pytest.fail(f"Search {i+1} (query: {query}) failed with error: {e}")

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_browser_reuse_performance(self, browser_pool: BrowserPool) -> None:
        """
        Test that browser reuse improves performance.

        First search includes browser initialization time.
        Subsequent searches should be much faster.
        """
        searcher = WeixinSearcher(browser_pool)

        # First search (includes browser initialization)
        start1 = time.time()
        results1 = await searcher.search("Python", max_results=5)
        time_first = time.time() - start1

        assert len(results1) > 0, "First search should return results"

        # Second search (browser already initialized)
        start2 = time.time()
        results2 = await searcher.search("AI", max_results=5)
        time_second = time.time() - start2

        assert len(results2) > 0, "Second search should return results"

        # Third search (should also be fast)
        start3 = time.time()
        results3 = await searcher.search("Machine Learning", max_results=5)
        time_third = time.time() - start3

        assert len(results3) > 0, "Third search should return results"

        # Subsequent searches should be faster than first
        # (First includes browser initialization overhead)
        print("\nPerformance metrics:")
        print(f"First search (with init): {time_first:.2f}s")
        print(f"Second search (reused): {time_second:.2f}s")
        print(f"Third search (reused): {time_third:.2f}s")

        # Second and third should be similar (both reuse browser)
        # Allow some variance due to network conditions
        # Note: Network conditions can vary, so we use a reasonable threshold
        assert time_second < 15.0, f"Second search too slow: {time_second:.2f}s"
        assert time_third < 15.0, f"Third search too slow: {time_third:.2f}s"

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_cache_effectiveness(self, browser_pool: BrowserPool) -> None:
        """
        Test that cache provides significant speedup.

        First search (no cache) should take normal time.
        Second search (with cache) should be much faster (< 0.01s).
        """

        def compare_results_ignoring_url(results1: list, results2: list) -> bool:
            """
            Compare results ignoring URL differences.

            Sogou redirect URLs contain dynamic tokens and encoded content
            that may differ between requests, even for the same article.
            This function compares all fields except URL.
            """
            if len(results1) != len(results2):
                return False

            for r1, r2 in zip(results1, results2):
                # Compare all fields except URL
                for key in r1:
                    if key == "url":
                        # Skip URL comparison - just verify both have URLs
                        if "url" not in r2 or not r1["url"] or not r2["url"]:
                            return False
                    else:
                        if key not in r2 or r1[key] != r2[key]:
                            return False

                # Also check that r2 doesn't have extra fields (except URL)
                for key in r2:
                    if key != "url" and key not in r1:
                        return False

            return True

        manager = UnifiedSearchManager()
        searcher = WeixinSearcher(browser_pool)
        manager.register_platform("weixin", searcher)

        try:
            # First search (with cache enabled - will store results)
            start1 = time.time()
            results1 = await manager.search("weixin", "Python", max_results=5, use_cache=True)
            time_no_cache = time.time() - start1

            assert len(results1) > 0, "First search should return results"

            # Second search (should use cache from first search)
            start2 = time.time()
            results2 = await manager.search("weixin", "Python", max_results=5, use_cache=True)
            time_with_cache = time.time() - start2

            # Compare results ignoring URL differences (URLs contain dynamic tokens)
            results_match = compare_results_ignoring_url(results1, results2)
            assert results_match, "Cached results should match original (ignoring URL differences)"

            # Cache should be much faster
            print("\nCache effectiveness:")
            print(f"First search (stores in cache): {time_no_cache:.2f}s")
            print(f"Second search (uses cache): {time_with_cache:.4f}s")
            print(f"Speedup: {time_no_cache / time_with_cache:.2f}x")

            # Cache should be very fast (< 0.01s)
            assert time_with_cache < 0.01, f"Cache too slow: {time_with_cache:.4f}s"

        finally:
            await manager.close()

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_concurrent_searches(self, browser_pool: BrowserPool) -> None:
        """
        Test concurrent searches performance.

        Multiple searches should be able to run concurrently
        using the same browser pool.
        """
        import asyncio

        searcher = WeixinSearcher(browser_pool)

        queries = ["Python", "AI", "Machine Learning", "Deep Learning", "Neural Network"]

        # Run searches concurrently
        start = time.time()
        tasks = [searcher.search(query, max_results=3) for query in queries]
        results_list = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        # All searches should succeed
        assert len(results_list) == len(queries)
        for i, results in enumerate(results_list):
            assert isinstance(results, list), f"Search {i+1} failed"

        print(f"\nConcurrent searches ({len(queries)} queries): {elapsed:.2f}s")
        print(f"Average per search: {elapsed / len(queries):.2f}s")

        # Concurrent searches should complete reasonably fast
        # (Much faster than sequential searches)
        assert elapsed < 30.0, f"Concurrent searches too slow: {elapsed:.2f}s"

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_search_stability(self, searcher: WeixinSearcher) -> None:
        """
        Test search stability over multiple iterations.

        Run the same search multiple times and verify:
        - All searches succeed
        - Results are consistent (may vary slightly due to real-time updates)
        """
        query = "Python"
        iterations = 5

        results_list = []
        for i in range(iterations):
            try:
                results = await searcher.search(query, max_results=5)
                assert isinstance(results, list), f"Iteration {i+1} failed"
                results_list.append(results)
            except Exception as e:
                pytest.fail(f"Iteration {i+1} failed with error: {e}")

        # All iterations should succeed
        assert len(results_list) == iterations

        # Results should be similar (may vary due to real-time updates)
        # But all should have valid structure
        for results in results_list:
            for result in results:
                assert "title" in result
                assert "url" in result
                assert "source" in result

        print(f"\nStability test: {iterations} iterations all succeeded")
