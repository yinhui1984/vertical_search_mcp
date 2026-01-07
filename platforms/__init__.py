"""
Platform adapters for vertical search.

This package contains platform-specific searchers:
- WeixinSearcher: WeChat article search
- ZhihuSearcher: Zhihu content search
- GoogleSearcher: Google Custom Search API
"""

from platforms.weixin_searcher import WeixinSearcher
from platforms.zhihu_searcher import ZhihuSearcher
from platforms.google_searcher import GoogleSearcher

__all__ = ["WeixinSearcher", "ZhihuSearcher", "GoogleSearcher"]
