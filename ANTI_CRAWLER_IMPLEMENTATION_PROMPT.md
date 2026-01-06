# Anti-Crawler Implementation Prompt for Vertical Search MCP Server

## Project Overview

You are tasked with implementing anti-crawler strategies for a vertical search MCP (Model Context Protocol) server. The project searches WeChat and Zhihu platforms via Sogou search engine using Playwright browser automation.

## Project Location
```
/Users/z/Documents/dev/vertical_search_mcp
```

## Current Architecture

### Core Components

1. **BrowserPool** (`core/browser_pool.py`): Singleton pattern browser pool
   - Single Playwright instance shared across all requests
   - One BrowserContext with fixed User-Agent
   - Route interceptor blocks images/fonts/stylesheets for performance
   - Performance target: <1s page creation time

2. **UnifiedSearchManager** (`core/search_manager.py`): Central search coordinator
   - Platform registration and routing
   - SearchCache integration (5-minute TTL)
   - Error handling and logging

3. **BasePlatformSearcher** (`core/base_searcher.py`): Abstract base class
   - Common utilities: query sanitization, text cleaning
   - URL resolution from Sogou redirects
   - Pagination support

4. **Platform Searchers** (`platforms/`):
   - `WeixinSearcher`: WeChat article search via Sogou
   - `ZhihuSearcher`: Zhihu search via Sogou
   - Both use click-to-resolve strategy for Sogou redirect URLs

### Configuration
- `config/platforms.yaml`: Platform-specific selectors and parameters
- Environment: Python 3.12+, asyncio, Playwright

## Implementation Tasks

### Task 1: Anti-Crawler Configuration System

Create `config/anti_crawler.yaml` with the following structure:

```yaml
# Anti-crawler configuration

global:
  # Global rate limiting
  rate_limit:
    enabled: true
    max_requests_per_minute: 30
    algorithm: "token_bucket"  # token_bucket | sliding_window | fixed_window
    on_limit_exceeded: "delay"  # reject | delay | queue
  
  # Global delay settings
  delay:
    enabled: true
    min_delay_ms: 1000
    max_delay_ms: 3000
    apply_to: "between_requests"  # before_request | after_request | between_requests

# User-Agent rotation
user_agent:
  enabled: true
  rotation_strategy: "per_session"  # per_request | per_session | per_platform
  pool:
    - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    - "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    - "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"

# Platform-specific overrides
platforms:
  weixin:
    rate_limit:
      max_requests_per_minute: 20
    delay:
      min_delay_ms: 1500
      max_delay_ms: 4000
    login_wall_detection:
      enabled: true
      url_patterns:
        - "unhuman"
        - "need_login"
        - "antispider"
      content_patterns:
        - "请输入验证码"
        - "登录后查看"
  
  zhihu:
    rate_limit:
      max_requests_per_minute: 15
    delay:
      min_delay_ms: 2000
      max_delay_ms: 5000
    login_wall_detection:
      enabled: true
      url_patterns:
        - "unhuman"
        - "need_login"
      content_patterns:
        - "请先登录"
        - "知乎验证"

# Anti-crawler detection responses
detection:
  captcha:
    patterns:
      - "验证码"
      - "captcha"
      - "verify"
    response: "delay_and_retry"
    max_retries: 2
    retry_delay_ms: 5000
  
  ip_ban:
    patterns:
      - "访问频繁"
      - "IP被封"
      - "请稍后再试"
    response: "fail_gracefully"
  
  rate_limit:
    patterns:
      - "请求过于频繁"
      - "too many requests"
    response: "exponential_backoff"
    initial_delay_ms: 2000
    max_delay_ms: 30000
```

### Task 2: User-Agent Rotation System

Implement a User-Agent pool system with the following requirements:

**File: `core/user_agent_pool.py`**

```python
"""
User-Agent rotation pool.

Requirements:
1. Support multiple rotation strategies:
   - per_request: New User-Agent for each request
   - per_session: User-Agent changes when BrowserContext is recreated
   - per_platform: Different User-Agent for each platform
   
2. Thread-safe (asyncio-safe) implementation

3. Load User-Agents from config

4. Provide method to get current User-Agent for a given strategy
"""
```

**Modification to `core/browser_pool.py`:**

The key insight is that Playwright's `page.set_extra_http_headers()` CAN override User-Agent, but it affects all subsequent requests from that page. The recommended approach:

```python
# Option 1: Context Pool (RECOMMENDED)
# Create multiple contexts with different User-Agents
# Pros: True User-Agent rotation, JavaScript fingerprinting consistent
# Cons: Slightly more memory usage

# Option 2: Per-page header override
# Use page.set_extra_http_headers({"User-Agent": "..."}) after creating page
# Pros: Simple, works with existing singleton
# Cons: JavaScript navigator.userAgent won't match HTTP header

# Option 3: CDP User-Agent override (BEST)
# Use Chrome DevTools Protocol to set User-Agent at browser level
# await page.context.browser.new_context() with user_agent parameter
# Or use: await cdp_session.send("Network.setUserAgentOverride", {...})
```

**Implementation Strategy:**
- Implement Context Pool pattern with 3-4 pre-created contexts
- Each context has different User-Agent
- Round-robin or random selection when getting page
- Maintain <1s page creation time by pre-warming contexts

### Task 3: Delay Mechanism

**File: `core/delay_manager.py`**

```python
"""
Async delay manager for anti-crawler.

Requirements:
1. Configurable delay ranges per platform
2. Non-blocking using asyncio.sleep()
3. Support for different delay strategies:
   - before_request: Delay before sending request
   - after_request: Delay after receiving response
   - between_requests: Delay between consecutive requests (track last request time)

4. Random delay within configured range
5. Skip delay for cached requests (already fast)
"""

import asyncio
import random
import time
from typing import Dict, Optional

class DelayManager:
    """
    Manages anti-crawler delays.
    
    Usage:
        delay_manager = DelayManager(config)
        await delay_manager.apply_delay("weixin")  # Apply delay for platform
    """
    
    def __init__(self, config: Dict) -> None:
        self._config = config
        self._last_request_time: Dict[str, float] = {}  # platform -> timestamp
        self._lock = asyncio.Lock()
    
    async def apply_delay(self, platform: str, skip_if_cached: bool = False) -> None:
        """Apply configured delay for platform."""
        pass
    
    async def _get_delay_ms(self, platform: str) -> int:
        """Get random delay in milliseconds for platform."""
        pass
```

**Integration Point: `core/search_manager.py`**

Add delay mechanism in `UnifiedSearchManager.search()`:

```python
async def search(self, platform: str, query: str, ...) -> List[Dict[str, str]]:
    # Check cache first (no delay for cache hits)
    if use_cache:
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # No delay for cached requests
    
    # Apply anti-crawler delay before search
    await self.delay_manager.apply_delay(platform)
    
    # Execute search...
```

### Task 4: Rate Limiting System

**File: `core/rate_limiter.py`**

Implement async-compatible rate limiter:

```python
"""
Async rate limiter for anti-crawler protection.

Requirements:
1. Token bucket algorithm (recommended for bursty traffic)
2. Per-platform rate limits
3. Thread-safe (asyncio.Lock)
4. Configurable behavior when limit exceeded:
   - reject: Raise exception immediately
   - delay: Wait until tokens available
   - queue: Queue request for later execution

5. Logging for rate limit events
"""

import asyncio
import time
from typing import Dict, Optional, Literal

class TokenBucketRateLimiter:
    """
    Token bucket rate limiter.
    
    Algorithm:
    - Bucket has max_tokens capacity
    - Tokens refill at rate of refill_rate per second
    - Each request consumes 1 token
    - If no tokens available, wait/reject/queue based on config
    """
    
    def __init__(
        self,
        max_tokens: int,
        refill_rate: float,  # tokens per second
        on_limit_exceeded: Literal["reject", "delay", "queue"] = "delay"
    ) -> None:
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
            - queue: (advanced) Add to queue for background processing
        """
        pass
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        pass


class RateLimitManager:
    """
    Manages rate limiters for all platforms.
    
    Usage:
        rate_limiter = RateLimitManager(config)
        
        if await rate_limiter.acquire("weixin"):
            # Proceed with request
        else:
            # Handle rate limit exceeded
    """
    
    def __init__(self, config: Dict) -> None:
        self._limiters: Dict[str, TokenBucketRateLimiter] = {}
        self._global_limiter: Optional[TokenBucketRateLimiter] = None
        self._setup_limiters(config)
```

**Integration Point: `core/search_manager.py`**

```python
async def search(self, platform: str, query: str, ...) -> List[Dict[str, str]]:
    # Check rate limit first
    if not await self.rate_limiter.acquire(platform):
        raise RateLimitExceeded(f"Rate limit exceeded for {platform}")
    
    # Check cache...
    # Apply delay...
    # Execute search...
```

### Task 5: Login Wall Detection

**File: `core/anti_crawler_detector.py`**

```python
"""
Anti-crawler detection system.

Requirements:
1. Detect various anti-crawler responses:
   - Login walls (Zhihu-specific)
   - CAPTCHA pages
   - IP bans
   - Rate limit pages

2. Extensible pattern matching:
   - URL pattern matching
   - Page content analysis
   - HTTP status codes

3. Configurable responses:
   - delay_and_retry: Wait and retry
   - fail_gracefully: Return empty results
   - exponential_backoff: Increasing delays

4. Integration with logging for monitoring
"""

from typing import List, Dict, Optional, Literal
from dataclasses import dataclass
from enum import Enum
from playwright.async_api import Page

class DetectionType(Enum):
    LOGIN_WALL = "login_wall"
    CAPTCHA = "captcha"
    IP_BAN = "ip_ban"
    RATE_LIMIT = "rate_limit"
    NONE = "none"

@dataclass
class DetectionResult:
    detected: bool
    detection_type: DetectionType
    confidence: float  # 0.0 - 1.0
    details: Optional[str] = None

class AntiCrawlerDetector:
    """
    Detects anti-crawler responses.
    
    Usage:
        detector = AntiCrawlerDetector(config)
        result = await detector.detect(page, platform="zhihu")
        
        if result.detected:
            if result.detection_type == DetectionType.LOGIN_WALL:
                # Handle login wall
            elif result.detection_type == DetectionType.CAPTCHA:
                # Handle CAPTCHA
    """
    
    def __init__(self, config: Dict) -> None:
        self._config = config
    
    async def detect(self, page: Page, platform: str) -> DetectionResult:
        """
        Detect anti-crawler response on page.
        
        Checks in order:
        1. URL patterns (fastest)
        2. HTTP status (if available)
        3. Page content (slowest, most reliable)
        """
        pass
    
    async def _check_url_patterns(self, url: str, platform: str) -> DetectionResult:
        """Check URL for anti-crawler patterns."""
        pass
    
    async def _check_content_patterns(self, page: Page, platform: str) -> DetectionResult:
        """Check page content for anti-crawler patterns."""
        pass
    
    def _get_platform_patterns(self, platform: str, pattern_type: str) -> List[str]:
        """Get patterns from config for platform."""
        pass
```

**Integration in Platform Searchers:**

Add detection after page navigation:

```python
# In WeixinSearcher.search() and ZhihuSearcher.search()
async def search(self, query: str, ...) -> List[Dict[str, str]]:
    page = await self.browser_pool.get_page()
    
    try:
        await page.goto(url, wait_until="domcontentloaded")
        
        # Check for anti-crawler responses
        detection = await self.detector.detect(page, platform="weixin")
        if detection.detected:
            self.logger.warning(
                f"Anti-crawler detected: {detection.detection_type.value}, "
                f"confidence: {detection.confidence}"
            )
            
            if detection.detection_type == DetectionType.LOGIN_WALL:
                return []  # Return empty results for login walls
            elif detection.detection_type == DetectionType.CAPTCHA:
                # Could implement retry logic here
                return []
        
        # Continue with normal search...
```

### Task 6: Testing Strategy

**File: `tests/unit/test_rate_limiter.py`**

```python
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
from unittest.mock import patch, AsyncMock
from core.rate_limiter import TokenBucketRateLimiter, RateLimitManager

class TestTokenBucketRateLimiter:
    
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self) -> None:
        """Test acquiring tokens within limit."""
        limiter = TokenBucketRateLimiter(max_tokens=10, refill_rate=1.0)
        
        for _ in range(10):
            assert await limiter.acquire() == True
    
    @pytest.mark.asyncio
    async def test_acquire_exceeds_limit_reject(self) -> None:
        """Test rejection when limit exceeded."""
        limiter = TokenBucketRateLimiter(
            max_tokens=2, 
            refill_rate=0.1, 
            on_limit_exceeded="reject"
        )
        
        assert await limiter.acquire() == True
        assert await limiter.acquire() == True
        assert await limiter.acquire() == False  # Should be rejected
    
    @pytest.mark.asyncio
    async def test_acquire_exceeds_limit_delay(self) -> None:
        """Test delay when limit exceeded."""
        # Use mock time to speed up test
        with patch('time.monotonic') as mock_time:
            mock_time.return_value = 0.0
            
            limiter = TokenBucketRateLimiter(
                max_tokens=1, 
                refill_rate=1.0,  # 1 token per second
                on_limit_exceeded="delay"
            )
            
            assert await limiter.acquire() == True
            
            # Simulate time passing
            mock_time.return_value = 1.0  # 1 second later
            
            assert await limiter.acquire() == True  # Should refill
    
    @pytest.mark.asyncio
    async def test_concurrent_acquire(self) -> None:
        """Test thread-safety with concurrent access."""
        limiter = TokenBucketRateLimiter(
            max_tokens=5, 
            refill_rate=0.0,  # No refill for this test
            on_limit_exceeded="reject"
        )
        
        async def try_acquire() -> bool:
            return await limiter.acquire()
        
        # Run 10 concurrent acquire attempts
        results = await asyncio.gather(*[try_acquire() for _ in range(10)])
        
        # Exactly 5 should succeed
        assert sum(results) == 5
```

**File: `tests/unit/test_delay_manager.py`**

```python
"""
Unit tests for delay manager.

Test strategy:
1. Mock asyncio.sleep to verify delay durations
2. Test random delay within range
3. Test skip_if_cached behavior
4. Test platform-specific delays
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from core.delay_manager import DelayManager

class TestDelayManager:
    
    @pytest.fixture
    def config(self) -> Dict:
        return {
            "global": {
                "delay": {
                    "enabled": True,
                    "min_delay_ms": 1000,
                    "max_delay_ms": 2000,
                }
            },
            "platforms": {
                "weixin": {
                    "delay": {
                        "min_delay_ms": 1500,
                        "max_delay_ms": 3000,
                    }
                }
            }
        }
    
    @pytest.mark.asyncio
    async def test_delay_within_range(self, config: Dict) -> None:
        """Test delay is within configured range."""
        manager = DelayManager(config)
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await manager.apply_delay("weixin")
            
            # Verify sleep was called
            mock_sleep.assert_called_once()
            delay = mock_sleep.call_args[0][0]
            
            # Delay should be between 1.5 and 3.0 seconds
            assert 1.5 <= delay <= 3.0
```

**File: `tests/unit/test_anti_crawler_detector.py`**

```python
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
    DetectionResult
)

class TestAntiCrawlerDetector:
    
    @pytest.fixture
    def config(self) -> Dict:
        return {
            "platforms": {
                "zhihu": {
                    "login_wall_detection": {
                        "enabled": True,
                        "url_patterns": ["unhuman", "need_login"],
                        "content_patterns": ["请先登录", "知乎验证"],
                    }
                }
            }
        }
    
    @pytest.mark.asyncio
    async def test_detect_login_wall_by_url(self, config: Dict) -> None:
        """Test login wall detection by URL pattern."""
        detector = AntiCrawlerDetector(config)
        
        # Mock page with login wall URL
        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://zhihu.sogou.com/unhuman?redirect=...")
        page.content = AsyncMock(return_value="<html>...</html>")
        
        result = await detector.detect(page, platform="zhihu")
        
        assert result.detected == True
        assert result.detection_type == DetectionType.LOGIN_WALL
    
    @pytest.mark.asyncio
    async def test_detect_login_wall_by_content(self, config: Dict) -> None:
        """Test login wall detection by content pattern."""
        detector = AntiCrawlerDetector(config)
        
        # Mock page with normal URL but login wall content
        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://zhihu.sogou.com/zhihu?query=test")
        page.content = AsyncMock(return_value="<html><body>请先登录后查看内容</body></html>")
        
        result = await detector.detect(page, platform="zhihu")
        
        assert result.detected == True
        assert result.detection_type == DetectionType.LOGIN_WALL
    
    @pytest.mark.asyncio
    async def test_no_detection_normal_page(self, config: Dict) -> None:
        """Test no detection for normal page."""
        detector = AntiCrawlerDetector(config)
        
        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://zhihu.sogou.com/zhihu?query=test")
        page.content = AsyncMock(return_value="<html><body>Normal search results</body></html>")
        
        result = await detector.detect(page, platform="zhihu")
        
        assert result.detected == False
        assert result.detection_type == DetectionType.NONE
```

### Task 7: Integration and Refactoring

**Modified `core/search_manager.py`:**

```python
"""
Unified search manager with anti-crawler protection.
"""

from typing import Dict, List, Optional
from core.browser_pool import BrowserPool
from core.cache import SearchCache
from core.base_searcher import BasePlatformSearcher
from core.logger import get_logger
from core.delay_manager import DelayManager
from core.rate_limiter import RateLimitManager
from core.anti_crawler_detector import AntiCrawlerDetector
from core.config_loader import load_anti_crawler_config


class UnifiedSearchManager:
    """
    Unified search manager with anti-crawler protection.
    """

    def __init__(self) -> None:
        """Initialize unified search manager."""
        self.browser_pool = BrowserPool()
        self.cache = SearchCache(ttl=300)
        self.searchers: Dict[str, BasePlatformSearcher] = {}
        self.logger = get_logger("vertical_search.search_manager")
        
        # Load anti-crawler configuration
        self._anti_crawler_config = load_anti_crawler_config()
        
        # Initialize anti-crawler components
        self.delay_manager = DelayManager(self._anti_crawler_config)
        self.rate_limiter = RateLimitManager(self._anti_crawler_config)
        self.detector = AntiCrawlerDetector(self._anti_crawler_config)

    async def search(
        self,
        platform: str,
        query: str,
        max_results: int = 10,
        time_filter: Optional[str] = None,
        use_cache: bool = True,
    ) -> List[Dict[str, str]]:
        """
        Execute search with anti-crawler protection.
        """
        # 1. Check rate limit
        if not await self.rate_limiter.acquire(platform):
            self.logger.warning(f"Rate limit exceeded for {platform}")
            raise RateLimitExceeded(f"Rate limit exceeded for {platform}")
        
        # 2. Check cache (no delay for cache hits)
        if use_cache:
            cache_key = self.cache.get_cache_key(
                platform=platform,
                query=query,
                params={"max_results": max_results, "time_filter": time_filter},
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                self.logger.info(f"Cache hit for {platform}:{query}")
                return cached
        
        # 3. Apply anti-crawler delay (only for non-cached requests)
        await self.delay_manager.apply_delay(platform)
        
        # 4. Route to platform searcher
        if platform not in self.searchers:
            raise ValueError(f"Platform '{platform}' not registered")
        
        searcher = self.searchers[platform]
        
        # 5. Execute search with detection
        try:
            results = await searcher.search(
                query=query, 
                max_results=max_results, 
                time_filter=time_filter
            )
            
            # 6. Cache results
            if use_cache:
                self.cache.set(cache_key, results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Search failed for {platform}:{query}: {e}")
            raise
```

## Implementation Order

1. **Phase 1: Configuration System**
   - Create `config/anti_crawler.yaml`
   - Create `core/config_loader.py` to load config

2. **Phase 2: Rate Limiting**
   - Implement `core/rate_limiter.py`
   - Write unit tests
   - Integrate into `UnifiedSearchManager`

3. **Phase 3: Delay Mechanism**
   - Implement `core/delay_manager.py`
   - Write unit tests
   - Integrate into `UnifiedSearchManager`

4. **Phase 4: User-Agent Rotation**
   - Implement `core/user_agent_pool.py`
   - Modify `core/browser_pool.py` to use context pool
   - Write unit tests

5. **Phase 5: Anti-Crawler Detection**
   - Implement `core/anti_crawler_detector.py`
   - Integrate into platform searchers
   - Write unit tests

6. **Phase 6: Integration Testing**
   - Write integration tests
   - Performance benchmarks
   - End-to-end testing

## Code Style Requirements

1. **Type Hints**: Full type hints on all functions and methods
2. **Docstrings**: Google-style docstrings
3. **Async/Await**: All I/O operations must be async
4. **SOLID Principles**: Single responsibility, dependency injection
5. **Error Handling**: Proper exception hierarchy
6. **Logging**: Use existing logger from `core/logger.py`

## File Structure After Implementation

```
vertical_search_mcp/
├── config/
│   ├── platforms.yaml          # Existing
│   └── anti_crawler.yaml       # NEW
├── core/
│   ├── __init__.py
│   ├── base_searcher.py        # Modified (add detector)
│   ├── browser_pool.py         # Modified (context pool)
│   ├── cache.py                # Existing
│   ├── config_loader.py        # NEW
│   ├── delay_manager.py        # NEW
│   ├── logger.py               # Existing
│   ├── rate_limiter.py         # NEW
│   ├── search_manager.py       # Modified
│   ├── url_resolver.py         # Existing
│   ├── user_agent_pool.py      # NEW
│   └── anti_crawler_detector.py # NEW
├── platforms/
│   ├── weixin_searcher.py      # Modified (add detection)
│   └── zhihu_searcher.py       # Modified (add detection)
└── tests/
    └── unit/
        ├── test_rate_limiter.py      # NEW
        ├── test_delay_manager.py     # NEW
        ├── test_anti_crawler_detector.py # NEW
        └── test_user_agent_pool.py   # NEW
```

## Performance Constraints

1. **Page Creation Time**: Must maintain <1s for subsequent pages
2. **Cache Response Time**: <10ms for cache hits
3. **Rate Limiter Overhead**: <1ms per check
4. **Delay**: Only apply to non-cached requests
5. **Memory**: Context pool should use <500MB additional memory

## Key Design Decisions

### Q1: User-Agent Rotation Strategy
**Answer**: Implement Context Pool pattern with CDP User-Agent override
- Create 3-4 contexts with different User-Agents at initialization
- Round-robin selection when getting page
- Pre-warm contexts to maintain <1s page creation time
- Use `page.set_extra_http_headers()` for per-request override if needed

### Q2: Delay Location
**Answer**: In `UnifiedSearchManager.search()` (Option A)
- Global control over all platforms
- Skip delay for cache hits
- Easy to configure per-platform via config
- Clean separation of concerns

### Q3: Rate Limiting Algorithm
**Answer**: Token Bucket with "delay" behavior
- Smooth handling of bursty traffic
- Non-blocking async implementation
- Per-platform limits with global fallback

### Q4: Login Wall Handling
**Answer**: Return empty results immediately
- No retry (login walls indicate account required)
- Log for monitoring
- Cache detection result to avoid repeated parsing

### Q5: Testing Approach
**Answer**: Mock-based unit tests + controlled integration tests
- Mock Playwright pages with fixture content
- Mock time for rate limiter tests
- No real site requests in unit tests
- Integration tests with timeouts and circuit breakers

## Exception Hierarchy

```python
# core/exceptions.py

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
```

## Environment Variables

Add support for environment variable overrides:

```python
# core/config_loader.py

import os
import yaml
from typing import Dict, Any

def load_anti_crawler_config() -> Dict[str, Any]:
    """Load anti-crawler config with environment variable overrides."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        "config", 
        "anti_crawler.yaml"
    )
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    # Environment variable overrides
    if os.environ.get("ANTI_CRAWLER_ENABLED") == "false":
        config["global"]["rate_limit"]["enabled"] = False
        config["global"]["delay"]["enabled"] = False
    
    if rate_limit := os.environ.get("ANTI_CRAWLER_RATE_LIMIT"):
        config["global"]["rate_limit"]["max_requests_per_minute"] = int(rate_limit)
    
    return config
```

## Summary

This implementation adds comprehensive anti-crawler protection to the vertical search MCP server while maintaining the existing performance characteristics. The design prioritizes:

1. **Configurability**: All parameters in YAML config
2. **Extensibility**: Easy to add new platforms and detection patterns
3. **Performance**: Minimal overhead, skip delays for cache hits
4. **Testability**: Mock-friendly design with dependency injection
5. **Observability**: Comprehensive logging for monitoring

Please implement these components following the specifications above, ensuring all code passes mypy type checking and pytest tests.
