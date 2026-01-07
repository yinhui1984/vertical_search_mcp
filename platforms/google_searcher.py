"""
Google Custom Search platform searcher.

This module implements Google Custom Search API integration.
Unlike browser-based searchers, this uses REST API for search but still
uses browser pool for content fetching.
"""

import os
import asyncio
import yaml
from typing import List, Dict, Any
from core.base_searcher import BasePlatformSearcher
from core.browser_pool import BrowserPool
import httpx


class GoogleSearcher(BasePlatformSearcher):
    """
    Google Custom Search platform searcher.

    This searcher implements Google search using Custom Search API.
    It uses REST API for search and browser pool for content fetching.
    """

    def __init__(self, browser_pool: BrowserPool) -> None:
        """
        Initialize Google searcher.

        Args:
            browser_pool: BrowserPool instance for managing browser pages
        """
        super().__init__(browser_pool)
        self.config = self._load_config()
        self.api_key = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
        self.search_engine_id = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
        self.base_url = self.config.get("api", {}).get(
            "base_url", "https://www.googleapis.com/customsearch/v1"
        )

    def _load_config(self) -> Dict[str, Any]:
        """
        Load platform configuration from YAML file.

        Returns:
            Dictionary containing platform configuration

        Raises:
            FileNotFoundError: If config file doesn't exist
            KeyError: If 'google' section is missing in config
        """
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config", "platforms.yaml"
        )

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            configs = yaml.safe_load(f)

        if "google" not in configs:
            raise KeyError("'google' section not found in config file")

        return configs["google"]  # type: ignore[no-any-return]

    async def search(
        self, query: str, max_results: int = 10, **kwargs: Any
    ) -> List[Dict[str, str]]:
        """
        Execute Google Custom Search.

        This method:
        1. Validates API credentials
        2. Sanitizes the query
        3. Makes paginated API requests
        4. Transforms JSON response to standard format

        Args:
            query: Search query string
            max_results: Maximum number of results to return (max: 30)
            **kwargs: Additional parameters (not used currently)

        Returns:
            List of search result dictionaries, each containing:
            - title: Article title
            - url: Article URL
            - source: Source platform name
            - date: Publication date (if available)
            - snippet: Article snippet/description (if available)
        """
        # Validate API credentials
        if not self.api_key or not self.search_engine_id:
            self.logger.warning(
                "Google Custom Search API credentials not set. "
                "Set APIKEY_GOOGLE_CUSTOM_SEARCH and APIKEY_GOOGLE_SEARCH_ID environment variables."
            )
            return []

        # Validate max_results limit
        max_total_results = self.config.get("api", {}).get("max_total_results", 30)
        if max_results > max_total_results:
            self.logger.warning(
                f"max_results ({max_results}) exceeds platform limit ({max_total_results}), "
                f"capping to {max_total_results}"
            )
            max_results = max_total_results

        # Sanitize query
        query = self._sanitize_query(query)
        if not query:
            return []

        # Get results per request from config
        results_per_request = self.config.get("api", {}).get("max_results_per_request", 10)

        # Calculate number of requests needed
        num_requests = (max_results + results_per_request - 1) // results_per_request

        results: List[Dict[str, str]] = []
        source_name = self.config.get("metadata", {}).get("display_name", "Google")

        async with httpx.AsyncClient(timeout=30.0) as client:
            for request_num in range(num_requests):
                start_index = request_num * results_per_request + 1
                remaining = max_results - len(results)
                num = min(results_per_request, remaining)

                if num <= 0:
                    break

                params = {
                    "key": self.api_key,
                    "cx": self.search_engine_id,
                    "q": query,
                    "num": num,
                    "start": start_index,
                }

                self.logger.debug(
                    f"Making API request {request_num + 1}/{num_requests}: "
                    f"start={start_index}, num={num}"
                )

                # Retry logic with exponential backoff
                max_retries = 3
                retry_delay = 1.0
                request_success = False

                for retry in range(max_retries):
                    try:
                        response = await client.get(self.base_url, params=params)
                        response.raise_for_status()

                        data = response.json()
                        items = data.get("items", [])

                        self.logger.info(
                            f"Got {len(items)} results from API request {request_num + 1}"
                        )

                        # Transform results to standard format
                        for item in items:
                            # Extract date from pagemap if available
                            date = ""
                            pagemap = item.get("pagemap", {})
                            if pagemap:
                                metatags = pagemap.get("metatags", [])
                                if metatags and len(metatags) > 0:
                                    date = metatags[0].get("article:published_time", "")

                            results.append(
                                {
                                    "title": item.get("title", ""),
                                    "url": item.get("link", ""),
                                    "source": source_name,
                                    "snippet": item.get("snippet", ""),
                                    "date": date,
                                }
                            )

                        request_success = True
                        break

                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429:
                            # Rate limit exceeded
                            if retry < max_retries - 1:
                                self.logger.warning(
                                    f"Rate limit exceeded (429), retrying in {retry_delay}s "
                                    f"(attempt {retry + 1}/{max_retries})"
                                )
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2  # Exponential backoff
                                continue
                            else:
                                self.logger.error(
                                    f"Rate limit exceeded (429) after {max_retries} retries, "
                                    f"returning partial results"
                                )
                                break
                        elif e.response.status_code == 400:
                            # Invalid query
                            error_data = e.response.json() if e.response.content else {}
                            error_msg = error_data.get("error", {}).get(
                                "message", "Invalid request"
                            )
                            self.logger.error(f"Invalid request (400): {error_msg}")
                            break
                        elif e.response.status_code == 401:
                            # Invalid credentials
                            self.logger.error("Invalid API credentials (401)")
                            break
                        else:
                            # Other HTTP errors
                            if retry < max_retries - 1:
                                self.logger.warning(
                                    f"HTTP error {e.response.status_code}, retrying in {retry_delay}s "
                                    f"(attempt {retry + 1}/{max_retries})"
                                )
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            else:
                                self.logger.error(
                                    f"HTTP error {e.response.status_code} after {max_retries} retries: {e}"
                                )
                                break

                    except httpx.RequestError as e:
                        # Network errors
                        if retry < max_retries - 1:
                            self.logger.warning(
                                f"Network error, retrying in {retry_delay}s "
                                f"(attempt {retry + 1}/{max_retries}): {e}"
                            )
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        else:
                            self.logger.error(f"Network error after {max_retries} retries: {e}")
                            break

                    except Exception as e:
                        # Unexpected errors
                        self.logger.error(f"Unexpected error in API request: {e}", exc_info=True)
                        break

                # If request failed after all retries, break pagination loop
                if not request_success:
                    self.logger.warning(
                        f"Request {request_num + 1} failed, returning {len(results)} partial results"
                    )
                    break

                # Check if we have enough results
                if len(results) >= max_results:
                    break

        # Return limited results
        return results[:max_results]
