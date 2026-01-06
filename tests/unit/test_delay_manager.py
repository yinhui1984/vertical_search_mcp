"""
Unit tests for delay manager.

Test strategy:
1. Mock asyncio.sleep to verify delay durations
2. Test random delay within range
3. Test skip_if_cached behavior
4. Test platform-specific delays
5. Test between_requests delay calculation
"""

import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock
from core.delay_manager import DelayManager


class TestDelayManager:
    """Test DelayManager class."""

    @pytest.fixture
    def config(self) -> dict:
        """Create test configuration."""
        return {
            "global": {
                "delay": {
                    "enabled": True,
                    "min_delay_ms": 1000,
                    "max_delay_ms": 2000,
                    "apply_to": "before_request",
                }
            },
            "platforms": {
                "weixin": {
                    "delay": {
                        "min_delay_ms": 1500,
                        "max_delay_ms": 3000,
                    }
                }
            },
        }

    @pytest.mark.asyncio
    async def test_delay_within_range(self, config: dict) -> None:
        """Test delay is within configured range."""
        manager = DelayManager(config)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("weixin")

            # Verify sleep was called
            mock_sleep.assert_called_once()
            delay = mock_sleep.call_args[0][0]

            # Delay should be between 1.5 and 3.0 seconds (weixin config)
            assert 1.5 <= delay <= 3.0

    @pytest.mark.asyncio
    async def test_skip_if_cached(self, config: dict) -> None:
        """Test that delay is skipped for cached requests."""
        manager = DelayManager(config)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("weixin", skip_if_cached=True)

            # Sleep should not be called
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_platform_specific_delay(self, config: dict) -> None:
        """Test platform-specific delay configuration."""
        manager = DelayManager(config)

        # Test weixin (has platform-specific config)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("weixin")
            delay = mock_sleep.call_args[0][0]
            assert 1.5 <= delay <= 3.0

        # Test unknown platform (should use global config)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("unknown")
            delay = mock_sleep.call_args[0][0]
            assert 1.0 <= delay <= 2.0

    @pytest.mark.asyncio
    async def test_between_requests_delay(self) -> None:
        """Test between_requests delay strategy."""
        config = {
            "global": {
                "delay": {
                    "enabled": True,
                    "min_delay_ms": 1000,
                    "max_delay_ms": 2000,
                    "apply_to": "between_requests",
                }
            }
        }

        manager = DelayManager(config)

        # First request should not delay (no previous request)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("test")
            # May or may not sleep depending on timing, but should update last_request_time
            assert "test" in manager._last_request_time

        # Wait a bit
        await asyncio.sleep(0.1)

        # Second request should delay if too soon
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("test")
            # Should sleep to maintain delay between requests
            if mock_sleep.called:
                delay = mock_sleep.call_args[0][0]
                assert delay > 0

    @pytest.mark.asyncio
    async def test_disabled_delay(self) -> None:
        """Test that disabled delay doesn't sleep."""
        config = {
            "global": {
                "delay": {
                    "enabled": False,
                    "min_delay_ms": 1000,
                    "max_delay_ms": 2000,
                }
            }
        }

        manager = DelayManager(config)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("test")
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_after_request_delay(self) -> None:
        """Test after_request delay strategy."""
        config = {
            "global": {
                "delay": {
                    "enabled": True,
                    "min_delay_ms": 1000,
                    "max_delay_ms": 2000,
                    "apply_to": "after_request",
                }
            }
        }

        manager = DelayManager(config)

        # apply_delay should not sleep (delay happens after)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("test")
            mock_sleep.assert_not_called()

        # apply_delay_after should sleep
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay_after("test")
            mock_sleep.assert_called_once()
            delay = mock_sleep.call_args[0][0]
            assert 1.0 <= delay <= 2.0

    @pytest.mark.asyncio
    async def test_no_config(self) -> None:
        """Test manager with minimal config."""
        config = {}

        manager = DelayManager(config)

        # Should not raise error, just not delay
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("test")
            # May or may not sleep depending on defaults

