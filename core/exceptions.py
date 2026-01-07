"""
Exception hierarchy for anti-crawler related errors.

This module defines custom exceptions for anti-crawler protection,
including rate limiting, login walls, CAPTCHA, and IP bans.
"""


class AntiCrawlerException(Exception):
    """Base exception for anti-crawler related errors."""

    pass


class RateLimitExceeded(AntiCrawlerException):
    """Raised when rate limit is exceeded."""

    pass


class LoginWallDetected(AntiCrawlerException):
    """Raised when login wall is detected."""

    pass


class CaptchaDetected(AntiCrawlerException):
    """Raised when CAPTCHA is detected."""

    pass


class IPBanDetected(AntiCrawlerException):
    """Raised when IP ban is detected."""

    pass
