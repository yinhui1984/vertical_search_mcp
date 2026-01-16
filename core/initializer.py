"""
Platform initialization module.

This module provides a common function for registering platforms
that can be shared between MCP server and CLI.
"""

import os
import logging
from typing import Optional
from core.search_manager import UnifiedSearchManager
from core.logger import get_logger
from platforms.weixin_searcher import WeixinSearcher
from platforms.google_searcher import GoogleSearcher


def register_platforms(manager: UnifiedSearchManager, logger: Optional[logging.Logger] = None) -> None:
    """
    Register available platforms with the search manager.
    
    This function registers:
    - Weixin (WeChat) - always available
    - Google Custom Search - if credentials are available
    - Zhihu - disabled by default (uncomment to enable)
    
    Args:
        manager: UnifiedSearchManager instance to register platforms with
        logger: Optional logger instance (if None, creates a new one)
    """
    if logger is None:
        logger = get_logger("vertical_search.initializer")
    
    # Register Weixin platform (always available)
    manager.register_platform("weixin", WeixinSearcher(manager.browser_pool))
    
    # Register Google Custom Search (if credentials are available)
    google_api_key = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
    google_search_id = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
    if google_api_key and google_search_id:
        manager.register_platform("google", GoogleSearcher(manager.browser_pool))
        logger.info("Google Custom Search platform registered")
    else:
        logger.debug(
            "Google Custom Search not available: "
            "APIKEY_GOOGLE_CUSTOM_SEARCH or APIKEY_GOOGLE_SEARCH_ID not set"
        )
    
    # Zhihu platform disabled by default due to aggressive anti-crawler measures
    # Uncomment the lines below to enable Zhihu search (may not work reliably)
    # from platforms.zhihu_searcher import ZhihuSearcher
    # manager.register_platform("zhihu", ZhihuSearcher(manager.browser_pool))
    
    logger.info(f"Registered platforms: {manager.get_registered_platforms()}")
