"""
Unit tests for rate limiter.

Test strategy:
1. Mock time to speed up tests
2. Test token bucket refill logic
3. Test different on_limit_exceeded behaviors
4. Test concurrent access (asyncio safety)
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from core.rate_limiter import TokenBucketRateLimiter, RateLimitManager
from core.exceptions import RateLimitExceeded


class TestTokenBucketRateLimiter:
    """Test TokenBucketRateLimiter class."""

    @pytest.mark.asyncio
    async def test_acquire_within_limit(self) -> None:
        """Test acquiring tokens within limit."""
        limiter = TokenBucketRateLimiter(max_tokens=10, refill_rate=1.0)

        for _ in range(10):
            assert await limiter.acquire() is True

    @pytest.mark.asyncio
    async def test_acquire_exceeds_limit_reject(self) -> None:
        """Test rejection when limit exceeded."""
        limiter = TokenBucketRateLimiter(
            max_tokens=2, refill_rate=0.1, on_limit_exceeded="reject"
        )

        assert await limiter.acquire() is True
        assert await limiter.acquire() is True
        assert await limiter.acquire() is False  # Should be rejected

    @pytest.mark.asyncio
    async def test_acquire_exceeds_limit_delay(self) -> None:
        """Test delay when limit exceeded."""
        limiter = TokenBucketRateLimiter(
            max_tokens=1, refill_rate=1.0, on_limit_exceeded="delay"
        )

        assert await limiter.acquire() is True

        # Wait a bit for token to refill
        await asyncio.sleep(1.1)

        assert await limiter.acquire() is True  # Should refill and succeed

    @pytest.mark.asyncio
    async def test_token_refill(self) -> None:
        """Test token refill mechanism."""
        limiter = TokenBucketRateLimiter(max_tokens=10, refill_rate=1.0)

        # Consume all tokens
        for _ in range(10):
            await limiter.acquire()

        # Wait for refill (1 token per second)
        await asyncio.sleep(1.1)

        # Should be able to acquire at least 1 token
        assert await limiter.acquire() is True

    @pytest.mark.asyncio
    async def test_concurrent_acquire(self) -> None:
        """Test thread-safety with concurrent access."""
        # Use a very small refill_rate instead of 0.0 (which is invalid)
        # This ensures tokens don't refill during the test
        limiter = TokenBucketRateLimiter(
            max_tokens=5, refill_rate=0.0001, on_limit_exceeded="reject"
        )

        async def try_acquire() -> bool:
            return await limiter.acquire()

        # Run 10 concurrent acquire attempts
        results = await asyncio.gather(*[try_acquire() for _ in range(10)])

        # Exactly 5 should succeed (max_tokens=5, no refill during test)
        assert sum(results) == 5

    @pytest.mark.asyncio
    async def test_max_tokens_cap(self) -> None:
        """Test that tokens don't exceed max_tokens."""
        limiter = TokenBucketRateLimiter(max_tokens=5, refill_rate=100.0)

        # Wait long enough for many tokens to accumulate
        await asyncio.sleep(0.1)

        # Should still only have max_tokens
        tokens = limiter.get_current_tokens()
        assert tokens <= 5.0

    def test_invalid_max_tokens(self) -> None:
        """Test that invalid max_tokens raises ValueError."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            TokenBucketRateLimiter(max_tokens=0, refill_rate=1.0)

    def test_invalid_refill_rate(self) -> None:
        """Test that invalid refill_rate raises ValueError."""
        with pytest.raises(ValueError, match="refill_rate must be positive"):
            TokenBucketRateLimiter(max_tokens=10, refill_rate=0.0)


class TestRateLimitManager:
    """Test RateLimitManager class."""

    @pytest.fixture
    def config(self) -> dict:
        """Create test configuration."""
        return {
            "global": {
                "rate_limit": {
                    "enabled": True,
                    "max_requests_per_minute": 30,
                    "algorithm": "token_bucket",
                    "on_limit_exceeded": "delay",
                }
            },
            "platforms": {
                "weixin": {
                    "rate_limit": {
                        "max_requests_per_minute": 20,
                    }
                },
                "zhihu": {
                    "rate_limit": {
                        "max_requests_per_minute": 15,
                    }
                },
            },
        }

    @pytest.mark.asyncio
    async def test_global_limiter(self, config: dict) -> None:
        """Test global rate limiter."""
        manager = RateLimitManager(config)

        # Should be able to acquire tokens
        for _ in range(5):
            assert await manager.acquire("unknown_platform") is True

    @pytest.mark.asyncio
    async def test_platform_limiter(self, config: dict) -> None:
        """Test platform-specific rate limiter."""
        manager = RateLimitManager(config)

        # Should use platform-specific limiter
        for _ in range(5):
            assert await manager.acquire("weixin") is True

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, config: dict) -> None:
        """Test that rate limit exceeded raises exception."""
        # Use reject mode for testing
        config["global"]["rate_limit"]["on_limit_exceeded"] = "reject"
        config["global"]["rate_limit"]["max_requests_per_minute"] = 2

        manager = RateLimitManager(config)

        # Acquire 2 tokens (limit)
        await manager.acquire("test")
        await manager.acquire("test")

        # Third request should raise exception
        with pytest.raises(RateLimitExceeded):
            await manager.acquire("test")

    @pytest.mark.asyncio
    async def test_disabled_rate_limiting(self) -> None:
        """Test that disabled rate limiting always succeeds."""
        config = {
            "global": {
                "rate_limit": {
                    "enabled": False,
                }
            }
        }

        manager = RateLimitManager(config)

        # Should always succeed when disabled
        for _ in range(10):
            assert await manager.acquire("test") is True

    @pytest.mark.asyncio
    async def test_no_config(self) -> None:
        """Test manager with minimal config."""
        config = {"global": {}}

        manager = RateLimitManager(config)

        # Should work without rate limiting
        assert await manager.acquire("test") is True

