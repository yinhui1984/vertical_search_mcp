"""
Tests for token estimator module.
"""

from core.token_estimator import TokenEstimator


class TestTokenEstimator:
    """Test cases for TokenEstimator."""

    def test_estimate_empty_text(self):
        """Test estimation with empty text."""
        estimator = TokenEstimator()
        assert estimator.estimate_tokens("") == 0
        assert estimator.estimate_tokens(None) == 0

    def test_estimate_chinese_text(self):
        """Test estimation for Chinese text."""
        estimator = TokenEstimator()
        # Chinese text: 10 characters
        text = "这是一个测试文本"
        tokens = estimator.estimate_tokens(text)
        # Should be approximately 10 / 1.3 + 10 (safety margin) = ~17-18
        assert tokens > 0
        assert tokens >= 10  # At least 10 tokens

    def test_estimate_english_text(self):
        """Test estimation for English text."""
        estimator = TokenEstimator()
        # English text: 20 characters
        text = "This is a test text"
        tokens = estimator.estimate_tokens(text)
        # Should be approximately 20 / 3.5 + 10 (safety margin) = ~15-16
        assert tokens > 0
        assert tokens >= 10  # At least 10 tokens

    def test_estimate_mixed_text(self):
        """Test estimation for mixed Chinese and English text."""
        estimator = TokenEstimator()
        # Mixed text
        text = "This is a test 这是一个测试"
        tokens = estimator.estimate_tokens(text)
        assert tokens > 0
        assert tokens >= 10

    def test_estimate_total_tokens(self):
        """Test total token estimation for results."""
        estimator = TokenEstimator()
        results = [
            {"title": "Test Title 1", "snippet": "Test snippet 1"},
            {"title": "Test Title 2", "snippet": "Test snippet 2"},
        ]
        total = estimator.estimate_total_tokens(results)
        assert total > 0

    def test_estimate_total_tokens_with_content(self):
        """Test total token estimation with content."""
        estimator = TokenEstimator()
        results = [
            {
                "title": "Test Title",
                "snippet": "Test snippet",
                "content": "This is a longer content text for testing",
            }
        ]
        total = estimator.estimate_total_tokens(results)
        assert total > 0
        # Should include tokens from title, snippet, and content
        assert total >= 30

    def test_estimate_conservative(self):
        """Test that estimation is conservative (overestimates)."""
        estimator = TokenEstimator()
        # Short text should still get safety margin
        text = "Test"
        tokens = estimator.estimate_tokens(text)
        # Should have safety margin
        assert tokens >= 10
