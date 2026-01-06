"""
Unit tests for anti-crawler detector.

Test strategy:
1. Mock Playwright Page with controlled responses
2. Test URL pattern detection
3. Test content pattern detection
4. Test different detection types
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from core.anti_crawler_detector import (
    AntiCrawlerDetector,
    DetectionType,
    DetectionResult,
)


class TestAntiCrawlerDetector:
    """Test AntiCrawlerDetector class."""

    @pytest.fixture
    def config(self) -> dict:
        """Create test configuration."""
        return {
            "platforms": {
                "zhihu": {
                    "login_wall_detection": {
                        "enabled": True,
                        "url_patterns": ["unhuman", "need_login"],
                        "content_patterns": ["请先登录", "知乎验证"],
                    }
                },
                "weixin": {
                    "login_wall_detection": {
                        "enabled": True,
                        "url_patterns": ["unhuman", "need_login", "antispider"],
                        "content_patterns": ["请输入验证码", "登录后查看"],
                    }
                },
            },
            "detection": {
                "captcha": {
                    "patterns": ["验证码", "captcha", "verify"],
                },
                "ip_ban": {
                    "patterns": ["访问频繁", "IP被封", "请稍后再试"],
                },
            },
        }

    @pytest.mark.asyncio
    async def test_detect_login_wall_by_url(self, config: dict) -> None:
        """Test login wall detection by URL pattern."""
        detector = AntiCrawlerDetector(config)

        # Mock page with login wall URL
        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://zhihu.sogou.com/unhuman?redirect=...")
        page.content = AsyncMock(return_value="<html>...</html>")

        result = await detector.detect(page, platform="zhihu")

        assert result.detected is True
        assert result.detection_type == DetectionType.LOGIN_WALL
        assert result.confidence > 0.8

    @pytest.mark.asyncio
    async def test_detect_login_wall_by_content(self, config: dict) -> None:
        """Test login wall detection by content pattern."""
        detector = AntiCrawlerDetector(config)

        # Mock page with normal URL but login wall content
        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://zhihu.sogou.com/zhihu?query=test")
        page.content = AsyncMock(return_value="<html><body>请先登录后查看内容</body></html>")

        result = await detector.detect(page, platform="zhihu")

        assert result.detected is True
        assert result.detection_type == DetectionType.LOGIN_WALL
        assert result.confidence > 0.9

    @pytest.mark.asyncio
    async def test_detect_captcha(self, config: dict) -> None:
        """Test CAPTCHA detection."""
        detector = AntiCrawlerDetector(config)

        # Use a platform without login_wall config, or use a CAPTCHA pattern not in login_wall
        # "captcha" pattern is in global detection config, not in platform-specific login_wall
        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://weixin.sogou.com/weixin?query=test")
        page.content = AsyncMock(return_value="<html><body>Please enter captcha code</body></html>")

        result = await detector.detect(page, platform="weixin")

        assert result.detected is True
        assert result.detection_type == DetectionType.CAPTCHA

    @pytest.mark.asyncio
    async def test_detect_ip_ban(self, config: dict) -> None:
        """Test IP ban detection."""
        detector = AntiCrawlerDetector(config)

        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://weixin.sogou.com/weixin?query=test")
        page.content = AsyncMock(return_value="<html><body>访问频繁，请稍后再试</body></html>")

        result = await detector.detect(page, platform="weixin")

        assert result.detected is True
        assert result.detection_type == DetectionType.IP_BAN

    @pytest.mark.asyncio
    async def test_no_detection_normal_page(self, config: dict) -> None:
        """Test no detection for normal page."""
        detector = AntiCrawlerDetector(config)

        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://zhihu.sogou.com/zhihu?query=test")
        page.content = AsyncMock(return_value="<html><body>Normal search results</body></html>")

        result = await detector.detect(page, platform="zhihu")

        assert result.detected is False
        assert result.detection_type == DetectionType.NONE

    @pytest.mark.asyncio
    async def test_detection_priority_url_first(self, config: dict) -> None:
        """Test that URL detection happens before content detection."""
        detector = AntiCrawlerDetector(config)

        # URL matches, content also matches - should detect from URL (faster)
        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://zhihu.sogou.com/unhuman")
        page.content = AsyncMock(return_value="<html><body>请先登录</body></html>")

        result = await detector.detect(page, platform="zhihu")

        assert result.detected is True
        assert result.detection_type == DetectionType.LOGIN_WALL
        # Should have URL-based confidence (slightly lower than content)
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_error_handling(self, config: dict) -> None:
        """Test error handling in content detection."""
        detector = AntiCrawlerDetector(config)

        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://zhihu.sogou.com/zhihu?query=test")
        page.content = AsyncMock(side_effect=Exception("Network error"))

        # Should not raise, but return no detection
        result = await detector.detect(page, platform="zhihu")

        assert result.detected is False
        assert result.detection_type == DetectionType.NONE

    @pytest.mark.asyncio
    async def test_platform_specific_patterns(self, config: dict) -> None:
        """Test that platform-specific patterns are used."""
        detector = AntiCrawlerDetector(config)

        # Weixin has different patterns than Zhihu
        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://weixin.sogou.com/weixin?query=test")
        page.content = AsyncMock(return_value="<html><body>登录后查看</body></html>")

        result = await detector.detect(page, platform="weixin")

        assert result.detected is True
        assert result.detection_type == DetectionType.LOGIN_WALL

    @pytest.mark.asyncio
    async def test_empty_config(self) -> None:
        """Test detector with empty config."""
        detector = AntiCrawlerDetector({})

        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://test.com")
        page.content = AsyncMock(return_value="<html></html>")

        result = await detector.detect(page, platform="test")

        assert result.detected is False

