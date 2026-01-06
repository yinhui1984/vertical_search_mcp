"""
Unified search manager.

This module implements the unified search manager that handles:
- Platform registration and routing
- Cache management
- Error handling and logging
"""

from typing import Dict, List, Optional
from core.browser_pool import BrowserPool
from core.cache import SearchCache
from core.base_searcher import BasePlatformSearcher
from core.logger import get_logger


class UnifiedSearchManager:
    """
    Unified search manager.

    Responsible for platform routing, cache management, and error handling.

    Attributes:
        browser_pool: BrowserPool instance for managing browsers
        cache: SearchCache instance for caching results
        searchers: Dictionary mapping platform names to searcher instances
        logger: Logger instance for logging
    """

    def __init__(self) -> None:
        """Initialize unified search manager."""
        self.browser_pool = BrowserPool()
        self.cache = SearchCache(ttl=300)
        self.searchers: Dict[str, BasePlatformSearcher] = {}
        self.logger = get_logger("vertical_search.search_manager")

    def register_platform(self, platform: str, searcher: BasePlatformSearcher) -> None:
        """
        Register a platform searcher.

        Args:
            platform: Platform name (e.g., 'weixin', 'zhihu')
            searcher: Platform searcher instance

        Raises:
            ValueError: If platform name is empty or searcher is None
        """
        if not platform:
            raise ValueError("Platform name cannot be empty")
        if searcher is None:
            raise ValueError("Searcher cannot be None")

        self.searchers[platform] = searcher
        self.logger.info(f"Platform '{platform}' registered")

    async def search(
        self,
        platform: str,
        query: str,
        max_results: int = 10,
        time_filter: Optional[str] = None,
        use_cache: bool = True,
    ) -> List[Dict[str, str]]:
        """
        Execute search on specified platform.

        This method:
        1. Checks cache first (if use_cache is True)
        2. Routes to the appropriate platform searcher
        3. Executes the search
        4. Caches the results (if use_cache is True)
        5. Handles errors and logs appropriately

        Args:
            platform: Platform name (must be registered)
            query: Search query string
            max_results: Maximum number of results to return (max: 30)
            time_filter: Optional time filter (e.g., 'day', 'week', 'month')
            use_cache: Whether to use cache (default: True)

        Returns:
            List of search result dictionaries

        Raises:
            ValueError: If platform is not registered or max_results > 30
            RuntimeError: If search execution fails
        """
        # Validate max_results limit
        MAX_RESULTS_LIMIT = 30
        if max_results > MAX_RESULTS_LIMIT:
            raise ValueError(f"max_results cannot exceed {MAX_RESULTS_LIMIT}")

        # Check cache first
        if use_cache:
            cache_key = self.cache.get_cache_key(
                platform=platform,
                query=query,
                params={"max_results": max_results, "time_filter": time_filter},
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                self.logger.info(f"Cache hit for {platform}:{query}")
                # Type assertion: cached value should be List[Dict[str, str]]
                # Cache stores Any type, but we know it's List[Dict[str, str]] here
                return cached  # type: ignore[no-any-return]

        # Route to corresponding platform
        if platform not in self.searchers:
            available = list(self.searchers.keys())
            error_msg = (
                f"Platform '{platform}' not registered. " f"Available platforms: {available}"
            )
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        searcher = self.searchers[platform]

        # Execute search
        try:
            self.logger.info(f"Executing search on {platform} for query: {query}")
            results = await searcher.search(
                query=query, max_results=max_results, time_filter=time_filter
            )

            # Cache results
            if use_cache:
                self.cache.set(cache_key, results)
                self.logger.debug(f"Cached results for {platform}:{query}")

            self.logger.info(f"Search completed: {len(results)} results for {platform}:{query}")
            return results

        except Exception as e:
            error_msg = f"Search failed for {platform}:{query}: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    def get_registered_platforms(self) -> List[str]:
        """
        Get list of registered platform names.

        Returns:
            List of registered platform names
        """
        return list(self.searchers.keys())

    async def close(self) -> None:
        """
        Close browser pool and clean up resources.

        This should be called when the manager is no longer needed.
        """
        await self.browser_pool.close()
        self.logger.info("UnifiedSearchManager closed")
