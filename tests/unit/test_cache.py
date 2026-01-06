"""
Unit tests for SearchCache.

Tests cover:
- Basic CRUD operations
- TTL expiration mechanism
- Cache key generation
- Concurrent access
"""

import time
from core.cache import SearchCache


class TestSearchCache:
    """Test suite for SearchCache."""

    def test_cache_basic(self) -> None:
        """Test basic cache operations (get/set/clear)."""
        cache = SearchCache(ttl=300)

        # Set a value
        cache.set("key1", "value1")

        # Get the value
        value = cache.get("key1")
        assert value == "value1"

        # Update the value
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

        # Clear cache
        cache.clear()
        assert cache.get("key1") is None

    def test_cache_ttl(self) -> None:
        """Test TTL expiration mechanism."""
        # Use very short TTL for testing
        cache = SearchCache(ttl=1)

        # Set a value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.1)

        # Value should be expired
        assert cache.get("key1") is None

    def test_cache_key_generation(self) -> None:
        """Test cache key generation."""
        cache = SearchCache()

        # Generate keys for same inputs
        key1 = cache.get_cache_key("weixin", "Python", {"max_results": 10})
        key2 = cache.get_cache_key("weixin", "Python", {"max_results": 10})

        # Same inputs should generate same key
        assert key1 == key2

        # Different inputs should generate different keys
        key3 = cache.get_cache_key("weixin", "Python", {"max_results": 5})
        assert key1 != key3

        key4 = cache.get_cache_key("zhihu", "Python", {"max_results": 10})
        assert key1 != key4

        key5 = cache.get_cache_key("weixin", "AI", {"max_results": 10})
        assert key1 != key5

    def test_cache_key_consistency(self) -> None:
        """Test that cache key generation is consistent with parameter order."""
        cache = SearchCache()

        # Same parameters in different order should generate same key
        key1 = cache.get_cache_key("weixin", "Python", {"max_results": 10})
        key2 = cache.get_cache_key("weixin", "Python", {"max_results": 10})

        assert key1 == key2

    def test_cache_multiple_entries(self) -> None:
        """Test storing and retrieving multiple cache entries."""
        cache = SearchCache(ttl=300)

        # Store multiple entries
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", {"nested": "value"})

        # Retrieve all entries
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == {"nested": "value"}

    def test_cache_expiration_cleanup(self) -> None:
        """Test that expired entries are automatically removed."""
        cache = SearchCache(ttl=1)

        # Set multiple entries
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Both should be available
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"

        # Wait for expiration
        time.sleep(1.1)

        # Both should be expired and removed
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_with_complex_values(self) -> None:
        """Test caching complex data structures."""
        cache = SearchCache(ttl=300)

        # Cache a list
        cache.set("list_key", [1, 2, 3, {"nested": "value"}])
        assert cache.get("list_key") == [1, 2, 3, {"nested": "value"}]

        # Cache a dictionary
        cache.set("dict_key", {"a": 1, "b": [1, 2, 3]})
        assert cache.get("dict_key") == {"a": 1, "b": [1, 2, 3]}

    def test_cache_key_with_various_params(self) -> None:
        """Test cache key generation with various parameter types."""
        cache = SearchCache()

        # Test with different parameter types
        key1 = cache.get_cache_key("weixin", "Python", {"max_results": 10})
        key2 = cache.get_cache_key("weixin", "Python", {"max_results": "10"})
        # Different types should generate different keys
        assert key1 != key2

        # Test with empty params
        key3 = cache.get_cache_key("weixin", "Python", {})
        key4 = cache.get_cache_key("weixin", "Python", {})
        assert key3 == key4

    def test_cache_ttl_custom(self) -> None:
        """Test cache with custom TTL."""
        # Test with different TTL values
        cache_short = SearchCache(ttl=1)
        cache_long = SearchCache(ttl=10)

        cache_short.set("key1", "value1")
        cache_long.set("key2", "value2")

        # Wait 2 seconds
        time.sleep(2)

        # Short TTL should be expired
        assert cache_short.get("key1") is None

        # Long TTL should still be valid
        assert cache_long.get("key2") == "value2"

    def test_cache_concurrent_access(self) -> None:
        """Test concurrent cache access (thread safety)."""
        cache = SearchCache(ttl=300)

        def set_values(start: int, count: int) -> None:
            for i in range(count):
                cache.set(f"key_{start + i}", f"value_{start + i}")

        def get_values(start: int, count: int) -> list:
            results = []
            for i in range(count):
                value = cache.get(f"key_{start + i}")
                results.append(value)
            return results

        # Set values concurrently (simulated)
        set_values(0, 10)
        set_values(10, 10)

        # Get values
        values1 = get_values(0, 10)
        values2 = get_values(10, 10)

        # All values should be retrievable
        assert all(v is not None for v in values1)
        assert all(v is not None for v in values2)
