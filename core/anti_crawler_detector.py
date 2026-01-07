"""
Anti-crawler detection system.

This module detects various anti-crawler responses including:
- Login walls (Zhihu-specific)
- CAPTCHA pages
- IP bans
- Rate limit pages
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
from playwright.async_api import Page
from core.logger import get_logger

logger = get_logger("vertical_search.anti_crawler_detector")


class DetectionType(Enum):
    """Types of anti-crawler detection."""

    LOGIN_WALL = "login_wall"
    CAPTCHA = "captcha"
    IP_BAN = "ip_ban"
    RATE_LIMIT = "rate_limit"
    NONE = "none"


@dataclass
class DetectionResult:
    """
    Result of anti-crawler detection.

    Attributes:
        detected: Whether anti-crawler was detected
        detection_type: Type of detection
        confidence: Confidence score (0.0 - 1.0)
        details: Additional details about the detection
    """

    detected: bool
    detection_type: DetectionType
    confidence: float  # 0.0 - 1.0
    details: Optional[str] = None


class AntiCrawlerDetector:
    """
    Detects anti-crawler responses.

    This class checks for various anti-crawler mechanisms by:
    1. URL pattern matching (fastest)
    2. HTTP status codes (if available)
    3. Page content analysis (slowest, most reliable)

    Usage:
        detector = AntiCrawlerDetector(config)
        result = await detector.detect(page, platform="zhihu")

        if result.detected:
            if result.detection_type == DetectionType.LOGIN_WALL:
                # Handle login wall
            elif result.detection_type == DetectionType.CAPTCHA:
                # Handle CAPTCHA
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize anti-crawler detector.

        Args:
            config: Anti-crawler configuration dictionary
        """
        self._config = config
        self._detection_config = config.get("detection", {})

    async def detect(self, page: Page, platform: str) -> DetectionResult:
        """
        Detect anti-crawler response on page.

        Checks in order:
        1. URL patterns (fastest)
        2. HTTP status (if available)
        3. Page content (slowest, most reliable)

        Args:
            page: Playwright Page object
            platform: Platform name (e.g., 'weixin', 'zhihu')

        Returns:
            DetectionResult with detection information
        """
        # Check URL patterns first (fastest)
        url = page.url
        url_result = await self._check_url_patterns(url, platform)
        if url_result.detected:
            return url_result

        # Check page content (more reliable but slower)
        content_result = await self._check_content_patterns(page, platform)
        if content_result.detected:
            return content_result

        # No detection
        return DetectionResult(detected=False, detection_type=DetectionType.NONE, confidence=0.0)

    async def _check_url_patterns(self, url: str, platform: str) -> DetectionResult:
        """
        Check URL for anti-crawler patterns.

        Args:
            url: Page URL
            platform: Platform name

        Returns:
            DetectionResult
        """
        # Check platform-specific login wall patterns
        platforms_config = self._config.get("platforms", {})
        platform_config = platforms_config.get(platform, {})
        login_wall_config = platform_config.get("login_wall_detection", {})

        if login_wall_config.get("enabled", False):
            url_patterns = login_wall_config.get("url_patterns", [])
            for pattern in url_patterns:
                if pattern.lower() in url.lower():
                    logger.warning(f"Login wall detected by URL pattern '{pattern}' in {url}")
                    return DetectionResult(
                        detected=True,
                        detection_type=DetectionType.LOGIN_WALL,
                        confidence=0.9,
                        details=f"URL pattern '{pattern}' matched",
                    )

        # Check global detection patterns
        for detection_type, detection_config in self._detection_config.items():
            patterns = detection_config.get("patterns", [])
            for pattern in patterns:
                if pattern.lower() in url.lower():
                    detection_enum = self._get_detection_type_from_string(detection_type)
                    logger.warning(
                        f"{detection_enum.value} detected by URL pattern '{pattern}' in {url}"
                    )
                    return DetectionResult(
                        detected=True,
                        detection_type=detection_enum,
                        confidence=0.8,
                        details=f"URL pattern '{pattern}' matched",
                    )

        return DetectionResult(detected=False, detection_type=DetectionType.NONE, confidence=0.0)

    async def _check_content_patterns(self, page: Page, platform: str) -> DetectionResult:
        """
        Check page content for anti-crawler patterns.

        Args:
            page: Playwright Page object
            platform: Platform name

        Returns:
            DetectionResult
        """
        try:
            # Get page content
            content = await page.content()
            content_lower = content.lower()

            # Check platform-specific login wall patterns
            platforms_config = self._config.get("platforms", {})
            platform_config = platforms_config.get(platform, {})
            login_wall_config = platform_config.get("login_wall_detection", {})

            if login_wall_config.get("enabled", False):
                content_patterns = login_wall_config.get("content_patterns", [])
                for pattern in content_patterns:
                    if pattern in content_lower:
                        logger.warning(
                            f"Login wall detected by content pattern '{pattern}' on {platform}"
                        )
                        return DetectionResult(
                            detected=True,
                            detection_type=DetectionType.LOGIN_WALL,
                            confidence=0.95,
                            details=f"Content pattern '{pattern}' matched",
                        )

            # Check global detection patterns with more precise matching
            for detection_type, detection_config in self._detection_config.items():
                patterns = detection_config.get("patterns", [])
                for pattern in patterns:
                    # For captcha detection, use more precise matching with DOM checks
                    if detection_type == "captcha":
                        pattern_lower = pattern.lower()
                        if pattern_lower in content_lower:
                            # First, check if page actually has captcha elements (more reliable)
                            has_captcha_elements = await self._check_captcha_elements(page)
                            
                            # Additional context checks for captcha
                            captcha_contexts = [
                                "验证码",
                                "captcha",
                                "verify code",
                                "verification code",
                                "请输入",
                                "please enter",
                                "输入验证码",
                                "enter code",
                            ]
                            
                            # Check if captcha context appears near the pattern
                            pattern_index = content_lower.find(pattern_lower)
                            if pattern_index >= 0:
                                # Check surrounding context (200 chars before and after)
                                context_start = max(0, pattern_index - 200)
                                context_end = min(
                                    len(content_lower), pattern_index + len(pattern_lower) + 200
                                )
                                context = content_lower[context_start:context_end]
                                has_captcha_context = any(ctx in context for ctx in captcha_contexts)
                                
                                # Check for negative indicators (suggests normal content, not captcha page)
                                negative_indicators = [
                                    "<article",
                                    "<main",
                                    'class="content"',
                                    'class="article"',
                                    'id="content"',
                                    'id="article"',
                                ]
                                has_negative_indicators = any(
                                    indicator in content_lower for indicator in negative_indicators
                                )
                                
                                # Only trigger if:
                                # 1. Has captcha elements in DOM (strongest indicator), OR
                                # 2. Has captcha context AND no negative indicators (normal content)
                                if has_captcha_elements:
                                    # Strong detection: actual captcha elements found
                                    detection_enum = self._get_detection_type_from_string(
                                        detection_type
                                    )
                                    logger.warning(
                                        f"{detection_enum.value} detected by content pattern '{pattern}' with captcha elements"
                                    )
                                    return DetectionResult(
                                        detected=True,
                                        detection_type=detection_enum,
                                        confidence=0.95,
                                        details=f"Content pattern '{pattern}' matched with captcha elements in DOM",
                                    )
                                elif has_captcha_context and not has_negative_indicators:
                                    # Medium detection: context suggests captcha, no normal content
                                    detection_enum = self._get_detection_type_from_string(
                                        detection_type
                                    )
                                    logger.warning(
                                        f"{detection_enum.value} detected by content pattern '{pattern}' with context (no normal content found)"
                                    )
                                    return DetectionResult(
                                        detected=True,
                                        detection_type=detection_enum,
                                        confidence=0.7,
                                        details=f"Content pattern '{pattern}' matched with captcha context, no normal content indicators",
                                    )
                                # If has negative indicators (normal content present), likely false positive - skip
                    else:
                        # For other detection types, use simple matching
                        if pattern.lower() in content_lower:
                            detection_enum = self._get_detection_type_from_string(detection_type)
                            logger.warning(
                                f"{detection_enum.value} detected by content pattern '{pattern}'"
                            )
                            return DetectionResult(
                                detected=True,
                                detection_type=detection_enum,
                                confidence=0.9,
                                details=f"Content pattern '{pattern}' matched",
                            )

        except Exception as e:
            logger.warning(f"Error checking content patterns: {e}")

        return DetectionResult(detected=False, detection_type=DetectionType.NONE, confidence=0.0)

    async def _check_captcha_elements(self, page: Page) -> bool:
        """
        Check if page contains actual captcha input elements.
        
        This is more reliable than text pattern matching as it checks for
        actual DOM elements that indicate a captcha form.
        
        Args:
            page: Playwright Page object
            
        Returns:
            True if captcha elements are found, False otherwise
        """
        try:
            # Common captcha input selectors (case-insensitive matching via JavaScript)
            # Use evaluate to check for elements with case-insensitive attribute matching
            has_captcha = await page.evaluate("""
                () => {
                    // Check for input elements with captcha-related attributes
                    const inputs = document.querySelectorAll('input[type="text"]');
                    for (const input of inputs) {
                        const name = (input.getAttribute('name') || '').toLowerCase();
                        const id = (input.getAttribute('id') || '').toLowerCase();
                        const placeholder = (input.getAttribute('placeholder') || '').toLowerCase();
                        const className = (input.getAttribute('class') || '').toLowerCase();
                        
                        if (name.includes('captcha') || name.includes('verify') || name.includes('code') ||
                            id.includes('captcha') || id.includes('verify') || id.includes('code') ||
                            placeholder.includes('captcha') || placeholder.includes('verify') || 
                            placeholder.includes('验证码') || placeholder.includes('code') ||
                            className.includes('captcha') || className.includes('verify')) {
                            if (input.offsetParent !== null) {  // Check if visible
                                return true;
                            }
                        }
                    }
                    
                    // Check for captcha images
                    const images = document.querySelectorAll('img');
                    for (const img of images) {
                        const alt = (img.getAttribute('alt') || '').toLowerCase();
                        const src = (img.getAttribute('src') || '').toLowerCase();
                        if (alt.includes('captcha') || alt.includes('验证码') ||
                            src.includes('captcha')) {
                            if (img.offsetParent !== null) {  // Check if visible
                                return true;
                            }
                        }
                    }
                    
                    // Check for captcha canvas
                    const canvases = document.querySelectorAll('canvas');
                    for (const canvas of canvases) {
                        const id = (canvas.getAttribute('id') || '').toLowerCase();
                        if (id.includes('captcha')) {
                            if (canvas.offsetParent !== null) {  // Check if visible
                                return true;
                            }
                        }
                    }
                    
                    // Check for common captcha class/ID patterns
                    if (document.querySelector('.captcha, #captcha, [class*="captcha"], [id*="captcha"]')) {
                        return true;
                    }
                    
                    return false;
                }
            """)
            
            return bool(has_captcha)
        except Exception as e:
            logger.debug(f"Error checking captcha elements: {e}")
            return False

    def _get_detection_type_from_string(self, detection_type: str) -> DetectionType:
        """
        Convert string detection type to enum.

        Args:
            detection_type: String detection type

        Returns:
            DetectionType enum
        """
        type_map = {
            "captcha": DetectionType.CAPTCHA,
            "ip_ban": DetectionType.IP_BAN,
            "rate_limit": DetectionType.RATE_LIMIT,
        }
        return type_map.get(detection_type, DetectionType.NONE)

    def _get_platform_patterns(self, platform: str, pattern_type: str) -> List[str]:
        """
        Get patterns from config for platform.

        Args:
            platform: Platform name
            pattern_type: Pattern type (e.g., 'url_patterns', 'content_patterns')

        Returns:
            List of patterns
        """
        platforms_config = self._config.get("platforms", {})
        platform_config = platforms_config.get(platform, {})
        login_wall_config = platform_config.get("login_wall_detection", {})
        patterns = login_wall_config.get(pattern_type, [])
        # Type assertion: patterns should be List[str] from config
        if isinstance(patterns, list):
            # Ensure all items are strings
            return [str(p) for p in patterns]
        return []
