"""
Configuration loader for anti-crawler settings.

This module loads anti-crawler configuration from YAML file
and supports environment variable overrides.
"""

import os
import yaml
from typing import Dict, Any
from pathlib import Path
from core.logger import get_logger

logger = get_logger("vertical_search.config_loader")


def load_anti_crawler_config() -> Dict[str, Any]:
    """
    Load anti-crawler configuration from YAML file with environment variable overrides.

    Environment variable overrides:
    - ANTI_CRAWLER_ENABLED: "false" to disable all anti-crawler features
    - ANTI_CRAWLER_RATE_LIMIT: Override global max_requests_per_minute
    - ANTI_CRAWLER_DELAY_MIN: Override global min_delay_ms
    - ANTI_CRAWLER_DELAY_MAX: Override global max_delay_ms

    Returns:
        Dictionary containing anti-crawler configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    # Get config file path relative to project root
    config_path = Path(__file__).parent.parent / "config" / "anti_crawler.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Anti-crawler config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config: Dict[str, Any] = yaml.safe_load(f) or {}

    # Environment variable overrides
    if os.environ.get("ANTI_CRAWLER_ENABLED", "").lower() == "false":
        logger.info("Anti-crawler disabled via environment variable")
        if "global" in config:
            if "rate_limit" in config["global"]:
                config["global"]["rate_limit"]["enabled"] = False
            if "delay" in config["global"]:
                config["global"]["delay"]["enabled"] = False

    if rate_limit := os.environ.get("ANTI_CRAWLER_RATE_LIMIT"):
        try:
            rate_limit_value = int(rate_limit)
            if "global" in config and "rate_limit" in config["global"]:
                config["global"]["rate_limit"]["max_requests_per_minute"] = rate_limit_value
                logger.info(f"Rate limit overridden via environment: {rate_limit_value}")
        except ValueError:
            logger.warning(f"Invalid ANTI_CRAWLER_RATE_LIMIT value: {rate_limit}")

    if delay_min := os.environ.get("ANTI_CRAWLER_DELAY_MIN"):
        try:
            delay_min_value = int(delay_min)
            if "global" in config and "delay" in config["global"]:
                config["global"]["delay"]["min_delay_ms"] = delay_min_value
                logger.info(f"Min delay overridden via environment: {delay_min_value}ms")
        except ValueError:
            logger.warning(f"Invalid ANTI_CRAWLER_DELAY_MIN value: {delay_min}")

    if delay_max := os.environ.get("ANTI_CRAWLER_DELAY_MAX"):
        try:
            delay_max_value = int(delay_max)
            if "global" in config and "delay" in config["global"]:
                config["global"]["delay"]["max_delay_ms"] = delay_max_value
                logger.info(f"Max delay overridden via environment: {delay_max_value}ms")
        except ValueError:
            logger.warning(f"Invalid ANTI_CRAWLER_DELAY_MAX value: {delay_max}")

    return config


def load_compression_config() -> Dict[str, Any]:
    """
    Load compression configuration from YAML file.

    Returns:
        Dictionary containing compression configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    # Get config file path relative to project root
    config_path = Path(__file__).parent.parent / "config" / "compression.yaml"

    if not config_path.exists():
        logger.warning(
            f"Compression config file not found: {config_path}, using defaults"
        )
        # Return default configuration
        return {
            "compression": {
                "enabled": True,
                "api": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "timeout": 30,
                    "max_retries": 2,
                },
                "thresholds": {
                    "single_article": 3000,
                    "total_content": 50000,
                    "final_output": 80000,
                },
                "fetch": {"concurrency": 5, "timeout": 10},
                "cache": {"content_ttl": 3600, "compressed_ttl": 86400},
            }
        }

    with open(config_path, "r", encoding="utf-8") as f:
        config: Dict[str, Any] = yaml.safe_load(f) or {}

    return config

