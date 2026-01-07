"""
Unified search manager.

This module implements the unified search manager that handles:
- Platform registration and routing
- Cache management
- Error handling and logging
- Anti-crawler protection (rate limiting, delays, detection)
"""

from typing import Dict, List, Optional, Any, Callable, Awaitable
from core.browser_pool import BrowserPool
from core.cache import SearchCache
from core.base_searcher import BasePlatformSearcher
from core.logger import get_logger
from core.rate_limiter import RateLimitManager
from core.delay_manager import DelayManager
from core.config_loader import load_anti_crawler_config
from core.exceptions import RateLimitExceeded
from core.content_processor import ContentProcessor
import yaml
from pathlib import Path


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

        # Load platform configuration
        self._platform_config = self._load_platform_config()

        # Load anti-crawler configuration
        try:
            self._anti_crawler_config = load_anti_crawler_config()
            # Initialize rate limiter
            self.rate_limiter = RateLimitManager(self._anti_crawler_config)
            # Initialize delay manager
            self.delay_manager = DelayManager(self._anti_crawler_config)
        except Exception as e:
            self.logger.warning(
                f"Failed to load anti-crawler config: {e}, "
                f"continuing without anti-crawler protection"
            )
            self._anti_crawler_config = {}
            # Create dummy components that don't do anything
            self.rate_limiter = RateLimitManager({})
            self.delay_manager = DelayManager({})

        # Content processor (lazy initialization)
        self._content_processor: Optional[ContentProcessor] = None

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
        use_cache: bool = True,
        include_content: bool = False,
        progress_callback: Optional[Callable[[str, str, int, int], Awaitable[None]]] = None,
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
            use_cache: Whether to use cache (default: True)
            include_content: Whether to fetch and include full article content (default: False)
            progress_callback: Optional async callback for progress updates.
                Signature: (stage: str, message: str, current: int, total: int) -> None

        Returns:
            List of search result dictionaries (with 'content' field if include_content=True)

        Raises:
            ValueError: If platform is not registered or max_results > 30
            RuntimeError: If search execution fails
        """
        # Validate max_results limit
        MAX_RESULTS_LIMIT = 30
        if max_results > MAX_RESULTS_LIMIT:
            raise ValueError(f"max_results cannot exceed {MAX_RESULTS_LIMIT}")

        # Check rate limit first
        try:
            await self.rate_limiter.acquire(platform)
        except RateLimitExceeded:
            self.logger.warning(f"Rate limit exceeded for {platform}:{query}")
            raise

        # Report progress: searching stage
        if progress_callback:
            await progress_callback(
                "searching",
                f"Starting search on {platform} for '{query}'...",
                0,
                max_results,
            )

        # Check cache first (skip delay for cache hits)
        cache_key = None
        if use_cache:
            cache_key = self.cache.get_cache_key(
                platform=platform,
                query=query,
                params={"max_results": max_results},
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                self.logger.info(f"Cache hit for {platform}:{query}")
                # Report progress: completed (cache hit)
                if progress_callback:
                    await progress_callback(
                        "searching",
                        f"Cache hit, returning {len(cached)} results",
                        len(cached),
                        max_results,
                    )
                # Type assertion: cached value should be List[Dict[str, str]]
                # Cache stores Any type, but we know it's List[Dict[str, str]] here
                return cached  # type: ignore[no-any-return]

        # Apply anti-crawler delay (only for non-cached requests)
        await self.delay_manager.apply_delay(platform, skip_if_cached=False)

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
            results = await searcher.search(query=query, max_results=max_results)

            # Report progress: searching completed
            if progress_callback:
                await progress_callback(
                    "searching",
                    f"Found {len(results)} results",
                    len(results),
                    max_results,
                )

            # Cache results
            if use_cache and cache_key is not None:
                self.cache.set(cache_key, results)
                self.logger.debug(f"Cached results for {platform}:{query}")

            self.logger.info(f"Search completed: {len(results)} results for {platform}:{query}")

            # Process content if requested
            if include_content:
                try:
                    self.logger.info(f"Processing content for {len(results)} results")
                    results = await self._process_content(
                        results, platform, progress_callback=progress_callback
                    )
                    self.logger.info(f"Content processing completed for {platform}:{query}")
                except Exception as e:
                    self.logger.error(
                        f"Content processing failed: {e}, returning results without content",
                        exc_info=True,
                    )
                    # Continue with results without content rather than failing

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

    def _load_platform_config(self) -> Dict[str, Any]:
        """
        Load platform configuration from YAML file.

        Returns:
            Dictionary containing platform configuration
        """
        config_path = Path(__file__).parent.parent / "config" / "platforms.yaml"

        if not config_path.exists():
            self.logger.warning(f"Platform config file not found: {config_path}")
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config: Dict[str, Any] = yaml.safe_load(f) or {}
            return config
        except Exception as e:
            self.logger.error(f"Failed to load platform config: {e}")
            return {}

    def _get_content_processor(self) -> ContentProcessor:
        """
        Get or create content processor instance.

        Returns:
            ContentProcessor instance
        """
        if self._content_processor is None:
            from core.config_loader import load_compression_config

            compression_config = load_compression_config()
            self._content_processor = ContentProcessor(
                browser_pool=self.browser_pool,
                cache=self.cache,
                platform_config=self._platform_config,
                compression_config=compression_config,
            )
        return self._content_processor

    async def _process_content(
        self,
        results: List[Dict[str, str]],
        platform: str,
        progress_callback: Optional[Callable[[str, str, int, int], Awaitable[None]]] = None,
    ) -> List[Dict[str, str]]:
        """
        Process content for search results.

        Args:
            results: List of search result dictionaries
            platform: Platform name
            progress_callback: Optional async callback for progress updates

        Returns:
            List of results with content added
        """
        processor = self._get_content_processor()
        return await processor.process_results(
            results, platform, progress_callback=progress_callback
        )

    async def close(self) -> None:
        """
        Close browser pool and clean up resources.

        This should be called when the manager is no longer needed.
        """
        await self.browser_pool.close()
        self.logger.info("UnifiedSearchManager closed")
