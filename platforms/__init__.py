"""
Platform adapters for vertical search.

This package contains platform-specific searchers:
- WeixinSearcher: WeChat article search
- ZhihuSearcher: Zhihu content search
"""

from platforms.weixin_searcher import WeixinSearcher
from platforms.zhihu_searcher import ZhihuSearcher

__all__ = ["WeixinSearcher", "ZhihuSearcher"]
