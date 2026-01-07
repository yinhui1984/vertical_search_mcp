"""
Content compressor module.

This module handles intelligent compression of article content using DeepSeek API
to stay within token limits while preserving key information.
"""

import os
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from openai import AsyncOpenAI
from openai import RateLimitError
from core.logger import get_logger
from core.config_loader import load_compression_config


class ContentCompressor:
    """
    Content compressor using DeepSeek API.

    Provides intelligent compression of article content while preserving
    core information and key details.
    """

    # Compression prompts
    SINGLE_ARTICLE_COMPRESS_PROMPT = """You are a professional content compression expert. Please compress the following article into a refined version.

Compression requirements:
1. Retain core viewpoints and main arguments
2. Retain key data, numbers, dates
3. Retain technical terms and technical details
4. Retain conclusions and recommendations
5. Remove redundant descriptions, repeated content, transitional statements
6. Maintain logical coherence after compression

Article type identification and handling:
- Technical articles: Retain code examples (shortened), technical principles, implementation steps
- News reports: Retain 5W1H (when, where, who, what, why, how)
- Opinion pieces: Retain core arguments, key evidence, final conclusions
- Tutorial guides: Retain key steps, precautions, common questions

Output format: Output the compressed content directly, without any prefix or explanation."""

    BATCH_COMPRESS_PROMPT = """You are a professional content integration expert. Please integrate and compress the following multiple articles into a structured summary.

Integration requirements:
1. Identify the core viewpoints of each article
2. Merge identical/similar viewpoints, mark sources
3. Retain differentiated viewpoints and unique insights
4. Extract common key data and conclusions
5. Maintain distinguishability between articles

Output format:
## Comprehensive Summary
[Overall theme and common viewpoints]

## Key Points by Article
### Article 1: [Title]
- Core viewpoint: ...
- Key data: ...

### Article 2: [Title]
- Core viewpoint: ...
- Unique insight: ...

## Difference Comparison (if any)
[Differences in viewpoints between articles]"""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize content compressor.

        Args:
            config: Compression configuration dictionary (optional, loads from file if not provided)
        """
        if config is None:
            config = load_compression_config()

        self.config = config.get("compression", {})
        self.api_config = self.config.get("api", {})
        self.logger = get_logger("vertical_search.content_compressor")
        self._http_client = None  # Initialize HTTP client reference

        # Initialize DeepSeek API client
        api_key = os.getenv("APIKEY_DEEPSEEK")
        if not api_key:
            self.logger.warning(
                "APIKEY_DEEPSEEK environment variable not set. Compression will fail."
            )
            self.client = None
        else:
            try:
                # Check if SOCKS proxy is configured and handle it properly
                import httpx

                # Check for SOCKS proxy in environment
                all_proxy = os.getenv("ALL_PROXY") or os.getenv("all_proxy")
                if all_proxy and all_proxy.startswith("socks"):
                    # SOCKS proxy detected - need socksio package
                    try:
                        import socksio  # noqa: F401

                        # Create httpx client with SOCKS proxy support
                        self._http_client = httpx.AsyncClient(
                            proxy=all_proxy,
                            timeout=httpx.Timeout(self.api_config.get("timeout", 30)),
                        )
                        self.logger.debug("Initialized httpx client with SOCKS proxy support")
                    except ImportError:
                        self.logger.warning(
                            "SOCKS proxy detected but 'socksio' package not installed. "
                            "Installing httpx[socks] or setting NO_PROXY for DeepSeek API. "
                            "Creating client without proxy."
                        )
                        # Create client without proxy for DeepSeek API
                        # Set trust_env=False to avoid reading proxy from environment variables
                        self._http_client = httpx.AsyncClient(
                            trust_env=False,  # Don't read proxy from environment
                            timeout=httpx.Timeout(self.api_config.get("timeout", 30)),
                        )
                else:
                    # No SOCKS proxy or non-SOCKS proxy - create client without proxy
                    # Set trust_env=False to avoid reading proxy from environment variables
                    # This prevents AsyncOpenAI from trying to use SOCKS proxy from env
                    self._http_client = httpx.AsyncClient(
                        trust_env=False,  # Don't read proxy from environment
                        timeout=httpx.Timeout(self.api_config.get("timeout", 30)),
                    )
                    self.logger.debug("Initialized httpx client without proxy (trust_env=False)")

                self.client = AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://api.deepseek.com/v1",
                    http_client=self._http_client,
                )
                self.logger.info("DeepSeek API client initialized successfully")
            except Exception as e:
                self.logger.warning(
                    f"Failed to initialize DeepSeek API client: {e}. Compression will fail."
                )
                self.client = None
                self._http_client = None
        self.model = self.api_config.get("model", "deepseek-chat")
        self.timeout = self.api_config.get("timeout", 30)
        self.max_retries = self.api_config.get("max_retries", 2)

    async def close(self) -> None:
        """
        Clean up resources, safely close HTTP client.

        This method should be called when the compressor is no longer needed
        to prevent resource leaks and avoid AttributeError on client close.
        """
        if self._http_client:
            try:
                await self._http_client.aclose()
                self.logger.debug("HTTP client closed successfully")
            except AttributeError:
                # Handle case where _mounts attribute doesn't exist
                self.logger.debug("HTTP client close skipped (no _mounts attribute)")
            except Exception as e:
                self.logger.warning(f"Error closing HTTP client: {e}")
            finally:
                self._http_client = None

        if self.client:
            # AsyncOpenAI client cleanup
            try:
                if hasattr(self.client, "_client") and hasattr(self.client._client, "close"):
                    await self.client._client.close()
            except Exception as e:
                self.logger.debug(f"Error closing OpenAI client: {e}")
            self.client = None

    async def compress_content(
        self, content: str, max_tokens: int, temperature: float = 0.3
    ) -> Tuple[str, str]:
        """
        Compress a single content string.

        Args:
            content: Content string to compress
            max_tokens: Target maximum tokens for compressed content
            temperature: API temperature parameter (default: 0.3 for consistency)

        Returns:
            Tuple of (compressed_content, status)
            Status: 'compressed' | 'truncated' | 'original'
        """
        if not content:
            return "", "original"

        if not self.client:
            self.logger.warning(
                f"DeepSeek API client not available, using truncation fallback. "
                f"Content length: {len(content)} chars, target: {max_tokens} tokens"
            )
            return self._truncate(content, max_tokens), "truncated"

        # Calculate dynamic timeout based on content size
        # Formula: min(120, max(60, len(content) / 100))
        # This gives 60-120 seconds based on content size
        dynamic_timeout = min(120, max(60, len(content) / 100))
        self.logger.info(
            f"Attempting to compress content: {len(content)} chars -> target {max_tokens} tokens "
            f"(timeout: {dynamic_timeout:.1f}s)"
        )

        async def _compress_with_timeout(timeout_seconds: float, attempt_num: int = 1) -> Tuple[str, str]:
            """Helper function to compress with specified timeout."""
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": self.SINGLE_ARTICLE_COMPRESS_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": f"Please compress the following content to approximately {max_tokens} tokens:\n\n{content}",
                            },
                        ],
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stream=False,
                    ),
                    timeout=timeout_seconds,
                )
                compressed = response.choices[0].message.content or ""
                self.logger.info(
                    f"Successfully compressed content (attempt {attempt_num}): "
                    f"{len(content)} chars -> {len(compressed)} chars "
                    f"({len(compressed)/len(content)*100:.1f}% of original)"
                )
                return compressed, "compressed"
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"Compression timeout after {timeout_seconds:.1f}s (attempt {attempt_num})"
                )
                raise
            except Exception as e:
                self.logger.error(f"Compression error (attempt {attempt_num}): {e}")
                raise

        try:
            compressed, status = await _compress_with_timeout(dynamic_timeout, attempt_num=1)
            return compressed, status

        except RateLimitError:
            self.logger.warning("Rate limit error, waiting and retrying...")
            await asyncio.sleep(5)
            try:
                compressed, status = await _compress_with_timeout(dynamic_timeout, attempt_num=2)
                return compressed, status
            except Exception as e:
                self.logger.error(f"Retry after rate limit failed: {e}")
                return self._truncate(content, max_tokens), "truncated"

        except asyncio.TimeoutError:
            # Retry with exponential backoff (double the timeout)
            retry_timeout = min(180, dynamic_timeout * 2)
            self.logger.info(
                f"Compression timeout after {dynamic_timeout:.1f}s, retrying with {retry_timeout:.1f}s timeout"
            )
            try:
                # Exponential backoff: wait before retry
                await asyncio.sleep(2)
                compressed, status = await _compress_with_timeout(retry_timeout, attempt_num=2)
                return compressed, status
            except (asyncio.TimeoutError, Exception) as e:
                self.logger.warning(
                    f"Compression retry failed after {retry_timeout:.1f}s: {e}, "
                    f"using truncation fallback"
                )
                return self._truncate(content, max_tokens), "truncated"

        except Exception as e:
            self.logger.error(f"Compression failed: {e}, using truncation fallback", exc_info=True)
            return self._truncate(content, max_tokens), "truncated"

    async def compress_article(self, article: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
        """
        Compress a single article's content.

        Args:
            article: Article dictionary with 'content' key
            max_tokens: Target maximum tokens for compressed content

        Returns:
            Article dictionary with compressed content and status
        """
        content = article.get("content", "")
        if not content:
            return article

        title = article.get("title", "Unknown")
        self.logger.info(f"Compressing article: '{title}' ({len(content)} chars)")

        compressed, status = await self.compress_content(content, max_tokens)
        article["content"] = compressed
        article["content_status"] = status

        self.logger.info(
            f"Article compression completed: '{title}' -> status: {status}, "
            f"{len(compressed)} chars"
        )

        return article

    async def compress_batch(
        self, articles: List[Dict[str, Any]], max_total_tokens: int
    ) -> List[Dict[str, Any]]:
        """
        Compress multiple articles in batch.

        Args:
            articles: List of article dictionaries with 'content' key
            max_total_tokens: Target maximum total tokens for all compressed articles

        Returns:
            List of article dictionaries with compressed content
        """
        if not articles:
            return articles

        # Prepare batch content
        batch_content = []
        for i, article in enumerate(articles):
            title = article.get("title", f"Article {i+1}")
            content = article.get("content", "")
            if content:
                batch_content.append(f"### Article {i+1}: {title}\n\n{content}")

        combined_content = "\n\n".join(batch_content)

        if not self.client:
            self.logger.error("DeepSeek API client not initialized. Cannot compress batch.")
            return articles

        # Calculate dynamic timeout for batch compression
        # Use content size to determine timeout, with minimum of 120s and maximum of 300s
        batch_timeout = min(300, max(120, len(combined_content) / 50))
        self.logger.info(
            f"Batch compression: {len(combined_content)} chars, "
            f"target {max_total_tokens} tokens, timeout: {batch_timeout:.1f}s"
        )

        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": self.BATCH_COMPRESS_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": f"Please compress the following articles to approximately {max_total_tokens} tokens total:\n\n{combined_content}",
                        },
                    ],
                    max_tokens=max_total_tokens,
                    temperature=0.3,
                    stream=False,
                ),
                timeout=batch_timeout,
            )

            compressed_batch = response.choices[0].message.content or ""

            # Parse compressed batch back into individual articles
            # For simplicity, we'll return the batch as a single content for all articles
            # In a more sophisticated implementation, we could parse the structured output
            for article in articles:
                article["content"] = compressed_batch
                article["content_status"] = "batch_compressed"

            return articles

        except Exception as e:
            self.logger.error(f"Batch compression failed: {e}", exc_info=True)
            # Fallback: compress individually
            for article in articles:
                content = article.get("content", "")
                if content:
                    truncated = self._truncate(content, max_total_tokens // len(articles))
                    article["content"] = truncated
                    article["content_status"] = "truncated"
            return articles

    def _truncate(self, content: str, max_chars: int) -> str:
        """
        Simple truncation fallback.

        Args:
            content: Content to truncate
            max_chars: Maximum characters (rough token estimate: 1 char ≈ 1 token for Chinese)

        Returns:
            Truncated content with "..." suffix
        """
        if len(content) <= max_chars:
            return content
        return content[: max_chars - 3] + "..."
