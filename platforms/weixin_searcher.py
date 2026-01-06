"""
WeChat (Weixin) platform searcher.

This module implements the WeChat article search functionality using Sogou search.
It inherits from BasePlatformSearcher and implements platform-specific search logic.
"""

import os
import asyncio
import yaml
from typing import List, Dict, Optional, Any
from urllib.parse import urlencode
from core.base_searcher import BasePlatformSearcher
from core.browser_pool import BrowserPool
from playwright.async_api import ElementHandle


class WeixinSearcher(BasePlatformSearcher):
    """
    WeChat (Weixin) platform searcher.

    This searcher implements WeChat article search using Sogou search engine.
    It uses the browser pool for page management and loads configuration from YAML.
    """

    def __init__(self, browser_pool: BrowserPool) -> None:
        """
        Initialize WeChat searcher.

        Args:
            browser_pool: BrowserPool instance for managing browser pages
        """
        super().__init__(browser_pool)
        self.config = self._load_config()
        self.base_url = self.config.get("base_url", "https://weixin.sogou.com/weixin")

    def _load_config(self) -> Dict[str, Any]:
        """
        Load platform configuration from YAML file.

        Returns:
            Dictionary containing platform configuration

        Raises:
            FileNotFoundError: If config file doesn't exist
            KeyError: If 'weixin' section is missing in config
        """
        # Get config file path relative to project root
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config", "platforms.yaml"
        )

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            configs = yaml.safe_load(f)

        if "weixin" not in configs:
            raise KeyError("'weixin' section not found in config file")

        return configs["weixin"]  # type: ignore[no-any-return]

    async def search(
        self, query: str, max_results: int = 10, time_filter: Optional[str] = None, **kwargs: Any
    ) -> List[Dict[str, str]]:
        """
        Execute WeChat article search.

        This method:
        1. Sanitizes the query
        2. Builds the search URL with parameters
        3. Navigates to the search page
        4. Waits for results to load
        5. Parses and extracts results (with pagination if needed)

        Args:
            query: Search query string
            max_results: Maximum number of results to return (max: 30)
            time_filter: Optional time filter ('day', 'week', 'month', 'year')
            **kwargs: Additional parameters (not used currently)

        Returns:
            List of search result dictionaries, each containing:
            - title: Article title
            - url: Article URL
            - source: Source platform name
            - date: Publication date (if available)
            - snippet: Article snippet/description (if available)

        Raises:
            ValueError: If max_results > 30
        """
        # Validate max_results limit
        MAX_RESULTS_LIMIT = 30
        if max_results > MAX_RESULTS_LIMIT:
            raise ValueError(f"max_results cannot exceed {MAX_RESULTS_LIMIT}")

        # Sanitize query
        query = self._sanitize_query(query)
        if not query:
            return []

        # Build search URL
        params: Dict[str, str] = {
            "query": query,
            "type": self.config.get("url_params", {}).get("type", "2"),
            "ie": self.config.get("url_params", {}).get("ie", "utf8"),
        }

        # Add time filter if specified
        if time_filter:
            time_filters = self.config.get("time_filters", {})
            time_code = time_filters.get(time_filter)
            if time_code:
                params["tsn"] = time_code

        url = f"{self.base_url}?{urlencode(params)}"

        # Get page from browser pool
        page = await self.browser_pool.get_page()

        try:
            # Navigate to search page
            # Use domcontentloaded for faster initial load, then wait for specific elements
            # This is faster than networkidle which waits for all network activity to stop
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Wait for search results to load
            # Try multiple selectors in order with shorter timeout per selector
            # This prevents long waits if first selector doesn't match
            selectors = self.config.get("selectors", {}).get("article_list", [])
            page_loaded = False

            # Use shorter timeout per selector (2 seconds) to fail fast
            # This way if first selector doesn't work, we quickly try the next one
            # Total max wait time: 2s * number of selectors (much better than 10s each)
            for selector in selectors:
                try:
                    # Wait with shorter timeout for faster failure
                    # state="visible" ensures element is actually visible, not just in DOM
                    await page.wait_for_selector(selector, timeout=2000, state="visible")
                    page_loaded = True
                    break
                except Exception:
                    # Try next selector immediately (don't wait full timeout)
                    continue

            # If no selector matched, the page might still be loading
            # Give it one more chance with a slightly longer wait
            if not page_loaded:
                try:
                    # Try the first selector again with a bit more time
                    # Sometimes results load just after domcontentloaded
                    first_selector = selectors[0] if selectors else None
                    if first_selector:
                        await page.wait_for_selector(first_selector, timeout=3000, state="visible")
                        page_loaded = True
                except Exception:
                    # No results found or page structure changed
                    # This could indicate:
                    # 1. Anti-bot detection (captcha or block)
                    # 2. Page structure changed
                    # 3. Network issues
                    return []

            # Parse and extract results
            # Use pagination if max_results > 10 (Sogou returns 10 results per page)
            RESULTS_PER_PAGE = 10
            if max_results > RESULTS_PER_PAGE:
                # Use pagination to collect results from multiple pages
                results = await self._parse_results_with_pagination(
                    page, max_results, RESULTS_PER_PAGE
                )
            else:
                # Single page is enough
                results = await self._parse_results(page, max_results)

            # Resolve Sogou redirect links to real URLs by clicking links on search results page
            # This is more reliable than accessing links directly (which may expire)
            target_domains = ["mp.weixin.qq.com"]
            redirect_count = sum(1 for r in results if "sogou.com/link" in r.get("url", ""))

            if redirect_count > 0:
                self.logger.info(
                    f"Resolving {redirect_count} Sogou redirect URLs by clicking links on search page"
                )

                # Get all redirect URLs and their indices
                redirect_urls = [r["url"] for r in results if "sogou.com/link" in r.get("url", "")]
                redirect_indices = [
                    i for i, r in enumerate(results) if "sogou.com/link" in r.get("url", "")
                ]

                self.logger.debug(
                    f"Found {len(redirect_urls)} redirect URLs, {len(redirect_indices)} indices"
                )

                # Get all link elements from search results page
                selectors = self.config.get("selectors", {}).get("article_list", [])
                all_link_elements = []
                for selector in selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        if elements:
                            self.logger.debug(
                                f"Found {len(elements)} elements with selector: {selector}"
                            )
                            for element in elements:
                                link_elem = await element.query_selector("a")
                                if link_elem:
                                    all_link_elements.append(link_elem)
                            if all_link_elements:
                                self.logger.debug(f"Found {len(all_link_elements)} link elements")
                                break
                    except Exception as e:
                        self.logger.debug(f"Error with selector {selector}: {e}")
                        continue

                if not all_link_elements:
                    self.logger.warning("No link elements found on search results page")
                else:
                    self.logger.debug(
                        f"Total link elements found: {len(all_link_elements)}, need to resolve: {len(redirect_indices)}"
                    )

                # Resolve URLs by clicking links on the search results page
                resolved_urls: List[Optional[str]] = []
                for idx, result_idx in enumerate(redirect_indices):
                    try:
                        self.logger.info(
                            f"Resolving URL {idx + 1}/{len(redirect_indices)} (result index {result_idx}): {redirect_urls[idx][:80]}..."
                        )

                        # Use the link element at the same index as the result
                        if result_idx < len(all_link_elements):
                            link_element = all_link_elements[result_idx]

                            # Click the link and wait for new page/tab to open
                            try:
                                self.logger.debug(f"Clicking link element at index {result_idx}")
                                async with page.context.expect_page(timeout=8000) as new_page_info:
                                    await link_element.click(
                                        modifiers=["Meta"]
                                    )  # Cmd+Click to open in new tab

                                new_page = await new_page_info.value

                                # Wait for page to navigate away from about:blank
                                # Try multiple wait strategies to ensure we get the final URL
                                try:
                                    # Wait for navigation to complete
                                    await new_page.wait_for_load_state("networkidle", timeout=15000)
                                except Exception:
                                    # If networkidle times out, try domcontentloaded
                                    try:
                                        await new_page.wait_for_load_state(
                                            "domcontentloaded", timeout=10000
                                        )
                                    except Exception:
                                        # If that also fails, wait a bit and check URL
                                        await asyncio.sleep(2)

                                # Wait for URL to change from about:blank
                                max_wait_attempts = 10
                                wait_interval = 0.5
                                new_page_url = new_page.url
                                for attempt in range(max_wait_attempts):
                                    if new_page_url != "about:blank" and new_page_url:
                                        break
                                    await asyncio.sleep(wait_interval)
                                    new_page_url = new_page.url

                                self.logger.info(f"New page opened with URL: {new_page_url}")

                                # Check if it's a target domain
                                if (
                                    any(domain in new_page_url for domain in target_domains)
                                    and "sogou.com" not in new_page_url
                                ):
                                    resolved_urls.append(new_page_url)
                                    self.logger.info(
                                        f"Successfully resolved URL {idx + 1}: {new_page_url}"
                                    )
                                    await new_page.close()
                                else:
                                    self.logger.warning(
                                        f"New page URL doesn't match target domain. URL: {new_page_url}, target domains: {target_domains}"
                                    )
                                    resolved_urls.append(None)
                                    await new_page.close()
                            except Exception as e:
                                self.logger.error(
                                    f"Error clicking link {idx + 1}: {e}", exc_info=True
                                )
                                resolved_urls.append(None)
                        else:
                            self.logger.warning(
                                f"Could not find link element for result index {result_idx} (only {len(all_link_elements)} link elements available)"
                            )
                            resolved_urls.append(None)

                        # Small delay between clicks
                        if idx < len(redirect_urls) - 1:
                            await asyncio.sleep(0.5)

                    except Exception as e:
                        self.logger.error(f"Error resolving URL {idx + 1}: {e}", exc_info=True)
                        resolved_urls.append(None)

                # Update results with resolved URLs
                success_count = 0
                for i, resolved_url in zip(redirect_indices, resolved_urls):
                    if resolved_url:
                        results[i]["url"] = resolved_url
                        success_count += 1
                        self.logger.info(f"Updated result {i} with resolved URL: {resolved_url}")

                self.logger.info(
                    f"URL resolution completed: {success_count}/{len(redirect_indices)} URLs resolved successfully"
                )

            # Close the search page
            await page.close()

            return results

        except Exception as e:
            # Log error and return empty results
            self.logger.error(f"Search error: {e}")
            return []
        finally:
            # Ensure page is closed (may already be closed in try block)
            try:
                if not page.is_closed():
                    await page.close()
            except Exception:
                pass

    async def _extract_item(self, element: ElementHandle, index: int) -> Optional[Dict[str, str]]:
        """
        Extract a single article result from DOM element.

        This method extracts:
        - Title and URL from the link element
        - Additional metadata from parent container (if available)
        - Resolves Sogou redirect URL to real URL immediately

        Args:
            element: Playwright ElementHandle representing a search result
            index: Index of the element in the results list

        Returns:
            Dictionary containing result item data, or None if extraction fails
        """
        try:
            # Find the link element (usually an <a> tag)
            title_elem = await element.query_selector("a")
            if not title_elem:
                return None

            # Extract title and URL
            title = await title_elem.inner_text()
            link = await title_elem.get_attribute("href")

            if not title or not link:
                return None

            # Clean title
            title = self._clean_text(title)

            # Resolve relative URLs to absolute URLs
            # Note: Sogou redirect links use www.sogou.com, not weixin.sogou.com
            url = self._resolve_url_base(link, self.base_url, "www.sogou.com")

            # Note: URL resolution is done after search completion
            # to avoid slowing down the extraction process
            # Sogou redirect links will be resolved in batch after all results are collected

            # Try to extract additional metadata from parent container
            snippet = ""
            date = ""

            try:
                # Find parent container (usually <li> or similar)
                parent_handle = await element.evaluate_handle("el => el.closest('li')")
                if parent_handle:
                    parent = parent_handle.as_element()
                    if parent:
                        # Try to find snippet/description
                        snippet_elem = await parent.query_selector(".news-text, .text, .desc")
                        if snippet_elem:
                            snippet_text = await snippet_elem.inner_text()
                            snippet = self._clean_text(snippet_text)

                        # Try to find date
                        date_elem = await parent.query_selector(".news-time, .time, .date")
                        if date_elem:
                            date_text = await date_elem.inner_text()
                            date = self._clean_text(date_text)
            except Exception:
                # If metadata extraction fails, continue with basic info
                pass

            return {
                "title": title,
                "url": url,
                "source": self.config.get("metadata", {}).get("display_name", "微信公众号"),
                "date": date,
                "snippet": snippet,
            }

        except Exception:
            # If extraction fails, return None
            return None
