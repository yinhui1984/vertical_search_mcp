"""
Async delay manager for anti-crawler protection.

This module implements configurable delays to avoid triggering
anti-crawler mechanisms by spacing out requests.
"""

import asyncio
import random
import time
from typing import Dict, Any
from core.logger import get_logger

logger = get_logger("vertical_search.delay_manager")


class DelayManager:
    """
    Manages anti-crawler delays.

    This class implements configurable delays per platform to avoid
    triggering anti-crawler mechanisms. Supports three strategies:
    - before_request: Delay before sending request
    - after_request: Delay after receiving response
    - between_requests: Delay between consecutive requests (tracks last request time)

    Attributes:
        config: Configuration dictionary
        last_request_time: Dictionary mapping platform to last request timestamp
        lock: Async lock for thread-safety
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize delay manager.

        Args:
            config: Anti-crawler configuration dictionary
        """
        self._config = config
        self._last_request_time: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def apply_delay(self, platform: str, skip_if_cached: bool = False) -> None:
        """
        Apply configured delay for platform.

        Args:
            platform: Platform name
            skip_if_cached: If True, skip delay (for cached requests)
        """
        if skip_if_cached:
            return

        global_config = self._config.get("global", {})
        delay_config = global_config.get("delay", {})

        if not delay_config.get("enabled", True):
            return

        apply_to = delay_config.get("apply_to", "between_requests")

        if apply_to == "before_request":
            delay_ms = await self._get_delay_ms(platform)
            if delay_ms > 0:
                logger.debug(f"Applying {delay_ms}ms delay before request for {platform}")
                await asyncio.sleep(delay_ms / 1000.0)
        elif apply_to == "between_requests":
            async with self._lock:
                last_time = self._last_request_time.get(platform, 0)
                now = time.monotonic()
                elapsed = now - last_time

                delay_ms = await self._get_delay_ms(platform)
                delay_seconds = delay_ms / 1000.0

                if elapsed < delay_seconds:
                    wait_time = delay_seconds - elapsed
                    logger.debug(f"Applying {wait_time:.2f}s delay between requests for {platform}")
                    await asyncio.sleep(wait_time)

                self._last_request_time[platform] = time.monotonic()
        elif apply_to == "after_request":
            # This will be called after the request completes
            # For now, we'll track the time but not delay
            async with self._lock:
                self._last_request_time[platform] = time.monotonic()

    async def apply_delay_after(self, platform: str) -> None:
        """
        Apply delay after request completes.

        This is used when apply_to is "after_request".

        Args:
            platform: Platform name
        """
        global_config = self._config.get("global", {})
        delay_config = global_config.get("delay", {})

        if not delay_config.get("enabled", True):
            return

        apply_to = delay_config.get("apply_to", "between_requests")

        if apply_to == "after_request":
            delay_ms = await self._get_delay_ms(platform)
            if delay_ms > 0:
                logger.debug(f"Applying {delay_ms}ms delay after request for {platform}")
                await asyncio.sleep(delay_ms / 1000.0)

        # Always update last request time
        async with self._lock:
            self._last_request_time[platform] = time.monotonic()

    async def _get_delay_ms(self, platform: str) -> int:
        """
        Get random delay in milliseconds for platform.

        Args:
            platform: Platform name

        Returns:
            Delay in milliseconds
        """
        # Check platform-specific config first
        platforms_config = self._config.get("platforms", {})
        platform_config = platforms_config.get(platform, {})

        platform_delay = platform_config.get("delay", {})
        if platform_delay:
            min_delay: int = int(platform_delay.get("min_delay_ms", 1000))
            max_delay: int = int(platform_delay.get("max_delay_ms", 3000))
        else:
            # Fall back to global config
            global_config = self._config.get("global", {})
            delay_config = global_config.get("delay", {})
            min_delay = int(delay_config.get("min_delay_ms", 1000))
            max_delay = int(delay_config.get("max_delay_ms", 3000))

        if min_delay >= max_delay:
            return min_delay

        # Random delay within range
        return random.randint(min_delay, max_delay)
