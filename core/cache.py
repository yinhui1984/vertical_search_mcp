"""
Search cache for storing search results with TTL expiration.

This module implements a simple in-memory cache with TTL (Time To Live)
mechanism. Cache entries automatically expire after the TTL period.

Features:
- TTL expiration mechanism
- Automatic cleanup of expired entries
- Cache key generation from platform, query, and parameters
"""

import time
import hashlib
import json
from typing import Any, Optional, Tuple, Dict


class SearchCache:
    """
    Simple in-memory cache with TTL expiration.

    Attributes:
        cache: Dictionary storing cache entries as (value, timestamp) tuples
        ttl: Time to live in seconds (default: 300 seconds = 5 minutes)
    """

    def __init__(self, ttl: int = 300) -> None:
        """
        Initialize cache with TTL.

        Args:
            ttl: Time to live in seconds. Default is 300 (5 minutes).
        """
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.ttl = ttl

    def _generate_key(self, platform: str, query: str, params: Dict[str, Any]) -> str:
        """
        Generate cache key from platform, query, and parameters.

        Format: platform:query:hash(params)

        Args:
            platform: Platform name (e.g., 'weixin', 'zhihu')
            query: Search query string
            params: Additional parameters (e.g., max_results, time_filter)

        Returns:
            MD5 hash of the cache key string
        """
        # Sort params to ensure consistent key generation
        params_str = json.dumps(params, sort_keys=True)
        key_str = f"{platform}:{query}:{params_str}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """
        Get cached value if it exists and hasn't expired.

        Args:
            key: Cache key

        Returns:
            Cached value if found and not expired, None otherwise
        """
        if key in self.cache:
            value, timestamp = self.cache[key]
            current_time = time.time()

            # Check if entry has expired
            if current_time - timestamp < self.ttl:
                return value
            else:
                # Remove expired entry
                del self.cache[key]

        return None

    def set(self, key: str, value: Any) -> None:
        """
        Set cache value with current timestamp.

        Args:
            key: Cache key
            value: Value to cache
        """
        self.cache[key] = (value, time.time())

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()

    def get_cache_key(self, platform: str, query: str, params: Dict[str, Any]) -> str:
        """
        Public method to generate cache key.

        This is a convenience method that wraps _generate_key for external use.

        Args:
            platform: Platform name
            query: Search query string
            params: Additional parameters

        Returns:
            Cache key string
        """
        return self._generate_key(platform, query, params)
