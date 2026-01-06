"""
Content processor coordinator.

This module coordinates content fetching, token estimation, and compression
to process search results with full article content.
"""

import asyncio
import yaml
from typing import List, Dict, Any, Optional
from pathlib import Path
from core.browser_pool import BrowserPool
from core.cache import SearchCache
from core.content_fetcher import ContentFetcher
from core.content_compressor import ContentCompressor
from core.token_estimator import TokenEstimator
from core.logger import get_logger
from core.config_loader import load_compression_config


class ContentProcessor:
    """
    Content processor that coordinates fetching, estimation, and compression.

    Handles the full pipeline:
    1. Fetch article contents (concurrent, with limits)
    2. Estimate tokens
    3. Compress single articles if needed
    4. Compress batch if total exceeds threshold
    5. Cache results
    """

    def __init__(
        self,
        browser_pool: BrowserPool,
        cache: SearchCache,
        platform_config: Dict[str, Any],
        compression_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize content processor.

        Args:
            browser_pool: BrowserPool instance
            cache: SearchCache instance
            platform_config: Platform configuration (from platforms.yaml)
            compression_config: Compression configuration (optional, loads from file if not provided)
        """
        self.browser_pool = browser_pool
        self.cache = cache
        self.platform_config = platform_config
        self.logger = get_logger("vertical_search.content_processor")

        # Load compression config
        if compression_config is None:
            compression_config = load_compression_config()
        self.compression_config = compression_config.get("compression", {})
        self.thresholds = self.compression_config.get("thresholds", {})
        self.fetch_config = self.compression_config.get("fetch", {})

        # Initialize components
        self.content_fetcher = ContentFetcher(browser_pool, platform_config)
        self.content_compressor = ContentCompressor(compression_config)
        self.token_estimator = TokenEstimator()

        # Configuration
        self.concurrency = self.fetch_config.get("concurrency", 5)
        self.fetch_timeout = self.fetch_config.get("timeout", 10)
        self.single_article_threshold = self.thresholds.get("single_article", 3000)
        self.total_content_threshold = self.thresholds.get("total_content", 50000)
        self.final_output_threshold = self.thresholds.get("final_output", 80000)

    async def process_results(
        self, results: List[Dict[str, str]], platform: str
    ) -> List[Dict[str, str]]:
        """
        Process search results to fetch and compress content.

        Args:
            results: List of search result dictionaries
            platform: Platform name (e.g., 'weixin', 'zhihu')

        Returns:
            List of results with content added (and compressed if needed)
        """
        if not results:
            return results

        self.logger.info(f"Processing {len(results)} results for content fetching")

        # Step 1: Fetch all article contents (concurrent, with semaphore limit)
        urls = [result.get("url", "") for result in results]
        contents = await self._fetch_all_contents(urls, platform)

        # Step 2: Add content to results
        for i, (result, content) in enumerate(zip(results, contents)):
            if content and isinstance(content, str):
                result["content"] = content
                result["content_status"] = "fetched"
            else:
                result["content"] = ""
                result["content_status"] = "fetch_failed"

        # Step 3: Estimate tokens for each article
        articles_to_compress = []
        for result in results:
            if content := result.get("content"):
                tokens = self.token_estimator.estimate_tokens(content)
                result["content_tokens"] = tokens
                
                title = result.get("title", "Unknown")
                needs_compression = tokens > self.single_article_threshold
                self.logger.info(
                    f"Article '{title}': {len(content)} chars -> {tokens} tokens "
                    f"(threshold: {self.single_article_threshold}, "
                    f"needs compression: {needs_compression})"
                )

                # Check if single article needs compression
                if self._should_compress_single(result):
                    articles_to_compress.append(result)

        # Step 4: Compress single articles if needed
        if articles_to_compress:
            self.logger.info(
                f"Compressing {len(articles_to_compress)} single articles "
                f"(exceeding {self.single_article_threshold} tokens threshold)"
            )
            for i, article in enumerate(articles_to_compress, 1):
                try:
                    title = article.get("title", f"Article {i}")
                    original_tokens = article.get("content_tokens", 0)
                    self.logger.info(
                        f"Compressing article {i}/{len(articles_to_compress)}: "
                        f"'{title}' ({original_tokens} tokens)"
                    )
                    
                    compressed_article = await self.content_compressor.compress_article(
                        article, max_tokens=2000  # Target 2000 tokens per article
                    )
                    # Update tokens after compression
                    if compressed_content := compressed_article.get("content"):
                        new_tokens = self.token_estimator.estimate_tokens(compressed_content)
                        compressed_article["content_tokens"] = new_tokens
                        self.logger.info(
                            f"Article '{title}' compressed: {original_tokens} -> {new_tokens} tokens "
                            f"({new_tokens/original_tokens*100:.1f}% of original)"
                        )
                except Exception as e:
                    self.logger.error(
                        f"Failed to compress article '{article.get('title', 'Unknown')}': {e}",
                        exc_info=True
                    )
                    # Keep original content on failure

        # Step 5: Calculate total tokens
        total_tokens = self.token_estimator.estimate_total_tokens(results)

        self.logger.info(f"Total tokens after single compression: {total_tokens}")

        # Step 6: Batch compress if total exceeds threshold
        if self._should_compress_batch(total_tokens):
            self.logger.info(
                f"Total tokens ({total_tokens}) exceeds threshold ({self.total_content_threshold}), "
                f"starting batch compression (target: {self.final_output_threshold} tokens)"
            )
            try:
                results = await self.content_compressor.compress_batch(
                    results, max_total_tokens=self.final_output_threshold
                )
                # Re-estimate total tokens after batch compression
                total_tokens = self.token_estimator.estimate_total_tokens(results)
                self.logger.info(
                    f"Batch compression completed: {total_tokens} tokens "
                    f"({total_tokens/self.final_output_threshold*100:.1f}% of target)"
                )
            except Exception as e:
                self.logger.error(f"Batch compression failed: {e}", exc_info=True)

        # Step 7: Final check - truncate if still too large
        if total_tokens > self.final_output_threshold:
            self.logger.warning(
                f"Total tokens ({total_tokens}) still exceeds final threshold ({self.final_output_threshold}), truncating"
            )
            # Truncate each article's content proportionally
            for result in results:
                if content := result.get("content"):
                    # Calculate target length per article
                    target_chars = (
                        len(content)
                        * self.final_output_threshold
                        // total_tokens
                    )
                    if len(content) > target_chars:
                        result["content"] = content[: target_chars - 3] + "..."
                        result["content_status"] = "truncated"

        return results

    async def _fetch_all_contents(
        self, urls: List[str], platform: str
    ) -> List[Optional[str]]:
        """
        Fetch all article contents concurrently with semaphore limit.

        Args:
            urls: List of URLs to fetch
            platform: Platform name

        Returns:
            List of content strings (None if fetch failed)
        """
        semaphore = asyncio.Semaphore(self.concurrency)

        async def fetch_one(url: str) -> Optional[str]:
            async with semaphore:
                if not url:
                    return None

                # Check cache first
                url_hash = ContentFetcher.get_url_hash(url)
                cached = self.cache.get_content(url_hash)
                if cached is not None:
                    self.logger.debug(f"Cache hit for content: {url}")
                    return cached

                # Fetch content
                content = await self.content_fetcher.fetch_content(
                    url, platform, timeout=self.fetch_timeout
                )

                # Cache if successful
                if content:
                    cache_ttl = self.compression_config.get("cache", {}).get(
                        "content_ttl", 3600
                    )
                    self.cache.set_content(url_hash, content, ttl=cache_ttl)

                return content

        # Fetch all concurrently
        results = await asyncio.gather(*[fetch_one(url) for url in urls])
        return list(results)

    def _should_compress_single(self, article: Dict[str, Any]) -> bool:
        """
        Check if single article should be compressed.

        Args:
            article: Article dictionary with content and content_tokens

        Returns:
            True if article should be compressed
        """
        tokens = article.get("content_tokens", 0)
        should_compress = tokens > self.single_article_threshold
        if should_compress:
            title = article.get("title", "Unknown")
            self.logger.info(
                f"Article '{title}' needs compression: {tokens} tokens > {self.single_article_threshold} threshold"
            )
        return should_compress

    def _should_compress_batch(self, total_tokens: int) -> bool:
        """
        Check if batch compression is needed.

        Args:
            total_tokens: Total estimated tokens

        Returns:
            True if batch compression is needed
        """
        return total_tokens > self.total_content_threshold

