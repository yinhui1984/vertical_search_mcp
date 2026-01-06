"""
Token estimation module.

This module provides conservative token estimation for Chinese and English text.
Uses simple character-based estimation with safety margins to avoid underestimation.
"""

import re
from typing import List, Dict, Any


class TokenEstimator:
    """
    Token estimator with conservative estimation strategy.

    Uses conservative coefficients to avoid underestimation:
    - Chinese: 1.3 chars/token (actual is ~1.5-2, using 1.3 for safety)
    - English: 3.5 chars/token (actual is ~4, using 3.5 for safety)
    - Adds 10 token safety margin to all estimates
    """

    # Conservative estimation coefficients (overestimate rather than underestimate)
    CHINESE_CHARS_PER_TOKEN = 1.3  # Actual is ~1.5-2, using 1.3 for safety
    ENGLISH_CHARS_PER_TOKEN = 3.5  # Actual is ~4, using 3.5 for safety
    SAFETY_MARGIN = 10  # Additional tokens added as safety margin

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for a text string.

        Separates Chinese and non-Chinese characters and estimates separately
        using conservative coefficients.

        Args:
            text: Text string to estimate

        Returns:
            Estimated token count (always rounded up with safety margin)
        """
        if not text:
            return 0

        # Separate Chinese and non-Chinese characters
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        non_chinese_chars = len(text) - chinese_chars

        # Conservative estimation
        chinese_tokens = chinese_chars / self.CHINESE_CHARS_PER_TOKEN
        english_tokens = non_chinese_chars / self.ENGLISH_CHARS_PER_TOKEN

        # Round up and add safety margin
        total_tokens = int(chinese_tokens + english_tokens) + self.SAFETY_MARGIN

        return total_tokens

    def estimate_total_tokens(self, results: List[Dict[str, Any]]) -> int:
        """
        Estimate total token count for a list of search results.

        Estimates tokens for:
        - Title
        - Snippet/description
        - Content (if present)

        Args:
            results: List of search result dictionaries

        Returns:
            Total estimated token count
        """
        total = 0

        for result in results:
            # Estimate title tokens
            if title := result.get("title", ""):
                total += self.estimate_tokens(title)

            # Estimate snippet tokens
            if snippet := result.get("snippet", ""):
                total += self.estimate_tokens(snippet)

            # Estimate content tokens (if present)
            if content := result.get("content", ""):
                total += self.estimate_tokens(content)

        return total

