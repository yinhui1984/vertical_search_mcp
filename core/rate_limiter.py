"""
Async rate limiter for anti-crawler protection.

This module implements token bucket rate limiting algorithm
with support for per-platform limits and global fallback.
"""

import asyncio
import time
from typing import Dict, Optional, Literal, Any
from core.logger import get_logger
from core.exceptions import RateLimitExceeded

logger = get_logger("vertical_search.rate_limiter")


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter.

    Algorithm:
    - Bucket has max_tokens capacity
    - Tokens refill at rate of refill_rate per second
    - Each request consumes 1 token
    - If no tokens available, behavior depends on on_limit_exceeded setting

    Attributes:
        max_tokens: Maximum number of tokens in bucket
        refill_rate: Tokens refilled per second
        tokens: Current number of tokens in bucket
        last_refill: Timestamp of last token refill
        lock: Async lock for thread-safety
        on_limit_exceeded: Behavior when limit exceeded
    """

    def __init__(
        self,
        max_tokens: int,
        refill_rate: float,  # tokens per second
        on_limit_exceeded: Literal["reject", "delay", "queue"] = "delay",
    ) -> None:
        """
        Initialize token bucket rate limiter.

        Args:
            max_tokens: Maximum number of tokens in bucket
            refill_rate: Tokens refilled per second
            on_limit_exceeded: Behavior when limit exceeded
                - reject: Return False immediately if no tokens
                - delay: Wait until token available, then return True
                - queue: (Not implemented) Add to queue for background processing
        """
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be positive")

        self._max_tokens = max_tokens
        self._refill_rate = refill_rate
        self._tokens = float(max_tokens)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()
        self._on_limit_exceeded = on_limit_exceeded

    async def acquire(self) -> bool:
        """
        Acquire a token.

        Returns:
            True if token acquired, False if rejected

        Behavior based on on_limit_exceeded:
            - reject: Return False immediately if no tokens
            - delay: Wait until token available, then return True
            - queue: (Not implemented) Raise NotImplementedError
        """
        async with self._lock:
            self._refill()

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True

            # No tokens available
            if self._on_limit_exceeded == "reject":
                logger.debug("Rate limit exceeded, rejecting request")
                return False
            elif self._on_limit_exceeded == "delay":
                # Calculate wait time until next token is available
                wait_time = (1.0 - self._tokens) / self._refill_rate
                if wait_time > 0:
                    logger.debug(f"Rate limit exceeded, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    # Refill again after waiting
                    self._refill()
                    if self._tokens >= 1.0:
                        self._tokens -= 1.0
                        return True
                return False
            elif self._on_limit_exceeded == "queue":
                raise NotImplementedError("Queue mode not implemented")
            else:
                raise ValueError(f"Unknown on_limit_exceeded: {self._on_limit_exceeded}")

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill

        if elapsed > 0:
            # Calculate tokens to add: elapsed_time * refill_rate
            tokens_to_add = elapsed * self._refill_rate
            self._tokens = min(self._max_tokens, self._tokens + tokens_to_add)
            self._last_refill = now

    def get_current_tokens(self) -> float:
        """
        Get current number of tokens (for testing/monitoring).

        Returns:
            Current number of tokens in bucket
        """
        async def _get() -> float:
            async with self._lock:
                self._refill()
                return self._tokens

        # This is a bit of a hack, but we need to call the async method
        # For testing purposes, we'll create a simple sync wrapper
        return self._tokens


class RateLimitManager:
    """
    Manages rate limiters for all platforms.

    This class provides per-platform rate limiting with global fallback.
    Each platform can have its own rate limiter, and there's also a global
    limiter that applies to all requests.

    Attributes:
        limiters: Dictionary mapping platform names to rate limiters
        global_limiter: Global rate limiter (optional)
        config: Configuration dictionary
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize rate limit manager.

        Args:
            config: Anti-crawler configuration dictionary
        """
        self._limiters: Dict[str, TokenBucketRateLimiter] = {}
        self._global_limiter: Optional[TokenBucketRateLimiter] = None
        self._config = config
        self._setup_limiters(config)

    def _setup_limiters(self, config: Dict[str, Any]) -> None:
        """Setup rate limiters from configuration."""
        global_config = config.get("global", {})
        rate_limit_config = global_config.get("rate_limit", {})

        if not rate_limit_config.get("enabled", True):
            logger.info("Rate limiting disabled in configuration")
            return

        # Global rate limiter
        max_requests_per_minute = rate_limit_config.get("max_requests_per_minute", 30)
        algorithm = rate_limit_config.get("algorithm", "token_bucket")
        on_limit_exceeded = rate_limit_config.get("on_limit_exceeded", "delay")

        if algorithm != "token_bucket":
            logger.warning(f"Only token_bucket algorithm is supported, got: {algorithm}")

        # Convert requests per minute to tokens per second
        refill_rate = max_requests_per_minute / 60.0

        self._global_limiter = TokenBucketRateLimiter(
            max_tokens=max_requests_per_minute,
            refill_rate=refill_rate,
            on_limit_exceeded=on_limit_exceeded,
        )

        logger.info(
            f"Global rate limiter initialized: {max_requests_per_minute} req/min, "
            f"refill_rate={refill_rate:.2f} tokens/s"
        )

        # Per-platform rate limiters
        platforms_config = config.get("platforms", {})
        for platform_name, platform_config in platforms_config.items():
            platform_rate_limit = platform_config.get("rate_limit", {})
            if platform_rate_limit:
                platform_max = platform_rate_limit.get("max_requests_per_minute")
                if platform_max:
                    platform_refill_rate = platform_max / 60.0
                    self._limiters[platform_name] = TokenBucketRateLimiter(
                        max_tokens=platform_max,
                        refill_rate=platform_refill_rate,
                        on_limit_exceeded=on_limit_exceeded,
                    )
                    logger.info(
                        f"Platform '{platform_name}' rate limiter: "
                        f"{platform_max} req/min, refill_rate={platform_refill_rate:.2f} tokens/s"
                    )

    async def acquire(self, platform: str) -> bool:
        """
        Acquire a token for a platform.

        First tries platform-specific limiter, then falls back to global limiter.

        Args:
            platform: Platform name

        Returns:
            True if token acquired, False if rejected

        Raises:
            RateLimitExceeded: If rate limit exceeded and configured to raise
        """
        # Try platform-specific limiter first
        if platform in self._limiters:
            acquired = await self._limiters[platform].acquire()
            if not acquired:
                logger.warning(f"Rate limit exceeded for platform '{platform}'")
                raise RateLimitExceeded(f"Rate limit exceeded for platform '{platform}'")
            return True

        # Fall back to global limiter
        if self._global_limiter:
            acquired = await self._global_limiter.acquire()
            if not acquired:
                logger.warning(f"Global rate limit exceeded for platform '{platform}'")
                raise RateLimitExceeded("Global rate limit exceeded")
            return True

        # No rate limiting configured
        return True

