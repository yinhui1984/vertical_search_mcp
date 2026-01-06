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
from core.anti_crawler_detector import AntiCrawlerDetector, DetectionType
from core.config_loader import load_anti_crawler_config
from core.logger import get_logger
from playwright.async_api import ElementHandle

logger = get_logger("vertical_search.weixin_searcher")


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

        # Initialize anti-crawler detector
        try:
            anti_crawler_config = load_anti_crawler_config()
            self.detector = AntiCrawlerDetector(anti_crawler_config)
        except Exception as e:
            logger.warning(f"Failed to load anti-crawler config: {e}, continuing without detection")
            self.detector = AntiCrawlerDetector({})

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
        self, query: str, max_results: int = 10, **kwargs: Any
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

        url = f"{self.base_url}?{urlencode(params)}"
        logger.info(f"Built search URL: {url}")

        # Get page from browser pool
        page = await self.browser_pool.get_page()

        try:
            # Navigate to search page with retry mechanism for redirects
            # Use domcontentloaded for faster initial load, then wait for specific elements
            # This is faster than networkidle which waits for all network activity to stop
            max_nav_retries = 2
            nav_success = False
            
            for nav_retry in range(max_nav_retries):
                logger.debug(f"Navigating to URL (attempt {nav_retry + 1}/{max_nav_retries}): {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
                # Check actual URL after navigation (may have been redirected)
                actual_url = page.url
                
                # Check if redirected to root or base URL (without query params)
                is_root_redirect = (
                    actual_url == "https://weixin.sogou.com/" or
                    actual_url == "https://weixin.sogou.com" or
                    actual_url == self.base_url or 
                    actual_url == f"{self.base_url}/" or
                    ("query=" not in actual_url and "weixin.sogou.com" in actual_url)
                )
                
                if actual_url != url:
                    logger.warning(
                        f"URL changed after navigation. Expected: {url}, Actual: {actual_url}"
                    )
                    
                    # If redirected to base URL without params, this indicates a problem
                    if is_root_redirect:
                        logger.warning(
                            f"Page was redirected to base/root URL. This may indicate: "
                            f"1) Invalid query parameters, 2) Anti-crawler redirect, "
                            f"3) Search service unavailable"
                        )
                        
                        if nav_retry < max_nav_retries - 1:
                            logger.info(f"Retrying navigation after {2 * (nav_retry + 1)} seconds...")
                            await asyncio.sleep(2 * (nav_retry + 1))  # Exponential backoff
                            continue
                        else:
                            # Last retry, return empty
                            logger.error("All navigation retries exhausted, returning empty results")
                            return []
                
                # Wait a bit for any redirects to complete
                await asyncio.sleep(1.0)
                
                # Check actual URL again after waiting
                final_url = page.url
                
                # Check if we successfully reached search results
                has_query_param = "query=" in final_url
                is_valid_url = (
                    final_url == url or 
                    has_query_param or
                    (final_url.startswith("https://weixin.sogou.com/weixin") and has_query_param)
                )
                
                if is_valid_url:
                    # Successfully reached search results page
                    logger.info(f"Successfully navigated to search results: {final_url[:100]}")
                    nav_success = True
                    break
                
                # Still redirected after waiting
                logger.error(
                    f"Page still redirected after wait. "
                    f"Original URL: {url}, Final URL: {final_url}"
                )
                
                if nav_retry < max_nav_retries - 1:
                    logger.info(f"Retrying navigation after {2 * (nav_retry + 1)} seconds...")
                    await asyncio.sleep(2 * (nav_retry + 1))
                    continue
                
                # Last retry failed, check for common issues
                try:
                    page_content = await page.content()
                    if "验证码" in page_content or "captcha" in page_content.lower():
                        logger.warning("CAPTCHA page detected after all retries")
                        return []
                    elif "登录" in page_content and "需要登录" in page_content:
                        logger.warning("Login required page detected after all retries")
                        return []
                except Exception as e:
                    logger.debug(f"Could not check page content: {e}")
                
                logger.error("Failed all retries, returning empty results")
                return []
            
            if not nav_success:
                logger.error("Failed to navigate to search results page after all retries")
                return []

            # Check for anti-crawler responses
            detection = await self.detector.detect(page, platform="weixin")
            if detection.detected:
                logger.warning(
                    f"Anti-crawler detected: {detection.detection_type.value}, "
                    f"confidence: {detection.confidence}, details: {detection.details}"
                )

                if detection.detection_type == DetectionType.LOGIN_WALL:
                    logger.warning("Login wall detected, returning empty results")
                    return []
                elif detection.detection_type == DetectionType.CAPTCHA:
                    logger.warning("CAPTCHA detected, returning empty results")
                    return []
                elif detection.detection_type == DetectionType.IP_BAN:
                    logger.error("IP ban detected, returning empty results")
                    return []

            # Wait for search results to load
            # Try multiple selectors in order with shorter timeout per selector
            # This prevents long waits if first selector doesn't match
            selectors = self.config.get("selectors", {}).get("article_list", [])
            page_loaded = False
            selector_errors = []

            # Use shorter timeout per selector (2 seconds) to fail fast
            # This way if first selector doesn't work, we quickly try the next one
            # Total max wait time: 2s * number of selectors (much better than 10s each)
            for selector in selectors:
                try:
                    # Wait with reasonable timeout for reliable loading
                    # state="visible" ensures element is actually visible, not just in DOM
                    await page.wait_for_selector(selector, timeout=5000, state="visible")
                    page_loaded = True
                    logger.info(f"Successfully matched selector: {selector}")
                    break
                except Exception as e:
                    # Try next selector immediately (don't wait full timeout)
                    selector_errors.append(f"{selector}: {str(e)}")
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue

            # If no selector matched, the page might still be loading
            # Give it one more chance with a slightly longer wait
            if not page_loaded:
                try:
                    # Try the first selector again with a bit more time
                    # Sometimes results load just after domcontentloaded
                    first_selector = selectors[0] if selectors else None
                    if first_selector:
                        logger.info(f"Retrying first selector with longer timeout: {first_selector}")
                        await page.wait_for_selector(first_selector, timeout=8000, state="visible")
                        page_loaded = True
                        logger.info(f"Successfully matched selector on retry: {first_selector}")
                except Exception as e:
                    # No results found or page structure changed
                    logger.warning(f"First selector retry also failed: {e}")
                    selector_errors.append(f"{first_selector} (retry): {str(e)}")

            # If still not loaded, log diagnostic information
            if not page_loaded:
                # Get page URL and title for debugging
                page_url = page.url
                page_title = await page.title()
                logger.warning(
                    f"No search results found. URL: {page_url}, Title: {page_title}, "
                    f"Selectors tried: {len(selectors)}, Errors: {selector_errors}"
                )

                # Check if page contains common error indicators
                try:
                    page_content = await page.content()
                    if "验证码" in page_content or "captcha" in page_content.lower():
                        logger.warning("Page may contain CAPTCHA (found '验证码' or 'captcha' in content)")
                    if "登录" in page_content and "需要登录" in page_content:
                        logger.warning("Page may require login (found login indicators)")
                    if "没有找到" in page_content or "no results" in page_content.lower():
                        logger.info("Page indicates no results found (legitimate empty result)")
                except Exception as e:
                    logger.debug(f"Could not check page content: {e}")

                # No results found or page structure changed
                # This could indicate:
                # 1. Anti-bot detection (captcha or block)
                # 2. Page structure changed
                # 3. Network issues
                # 4. Legitimate empty search results
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

                # Track current page to avoid unnecessary navigation
                current_page_num: int = 0  # 0 means unknown
                
                # Helper function to navigate to a specific page
                async def navigate_to_page(page_num: int) -> bool:
                    """Navigate to a specific page number (1-based)."""
                    nonlocal current_page_num
                    
                    # If already on the target page, no need to navigate
                    if current_page_num == page_num:
                        return True
                    
                    if page_num == 1:
                        # Navigate to first page
                        try:
                            first_page_selectors = [
                                "a#sogou_page_1",
                                "a[href*='page=1']",
                                ".page a:has-text('1')",
                            ]
                            for selector in first_page_selectors:
                                try:
                                    first_page_btn = await page.query_selector(selector)
                                    if first_page_btn:
                                        await first_page_btn.click()
                                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                                        # Wait for results to load
                                        selectors_list = self.config.get("selectors", {}).get("article_list", [])
                                        for sel in selectors_list:
                                            try:
                                                await page.wait_for_selector(sel, timeout=2000, state="visible")
                                                current_page_num = 1
                                                return True
                                            except Exception:
                                                continue
                                        current_page_num = 1
                                        return True
                                except Exception:
                                    continue
                            
                            # If no first page button found, reload the search URL
                            self.logger.debug("No first page button found, reloading search URL")
                            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                            selectors_list = self.config.get("selectors", {}).get("article_list", [])
                            for sel in selectors_list:
                                try:
                                    await page.wait_for_selector(sel, timeout=2000, state="visible")
                                    current_page_num = 1
                                    return True
                                except Exception:
                                    continue
                            current_page_num = 1
                            return True
                        except Exception as e:
                            self.logger.warning(f"Failed to navigate to first page: {e}, reloading URL")
                            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                            selectors_list = self.config.get("selectors", {}).get("article_list", [])
                            for sel in selectors_list:
                                try:
                                    await page.wait_for_selector(sel, timeout=2000, state="visible")
                                    current_page_num = 1
                                    return True
                                except Exception:
                                    continue
                            current_page_num = 1
                            return True
                    else:
                        # Navigate to specific page number
                        # First ensure we're on page 1, then navigate forward
                        if not await navigate_to_page(1):
                            return False
                        
                        # Navigate forward to target page
                        for _ in range(page_num - 1):
                            next_page_selector = self.config.get("selectors", {}).get("next_page")
                            if not next_page_selector:
                                return False
                            
                            try:
                                next_button = await page.query_selector(next_page_selector)
                                if not next_button:
                                    return False
                                
                                is_disabled = await next_button.get_attribute("disabled")
                                class_name = await next_button.get_attribute("class") or ""
                                if is_disabled or "disabled" in class_name.lower() or "nop" in class_name.lower():
                                    return False
                                
                                await next_button.click()
                                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                                # Wait for results to load
                                selectors_list = self.config.get("selectors", {}).get("article_list", [])
                                for sel in selectors_list:
                                    try:
                                        await page.wait_for_selector(sel, timeout=2000, state="visible")
                                        break
                                    except Exception:
                                        continue
                                # Update current page number (we're moving forward one page at a time)
                                current_page_num += 1
                            except Exception as e:
                                self.logger.warning(f"Error navigating to page {page_num}: {e}")
                                return False
                        
                        # Update current page number to target page
                        current_page_num = page_num
                        return True
                
                # Helper function to get link element by result index
                async def get_link_element_by_index(result_idx: int) -> Optional[ElementHandle]:
                    """Get link element for a specific result index by navigating to the correct page."""
                    # Calculate which page this result is on (0-based page index)
                    page_index = result_idx // RESULTS_PER_PAGE  # 0-based
                    page_num = page_index + 1  # 1-based
                    page_result_idx = result_idx % RESULTS_PER_PAGE  # Index within the page
                    
                    # Navigate to the correct page
                    if not await navigate_to_page(page_num):
                        self.logger.warning(f"Failed to navigate to page {page_num} for result index {result_idx}")
                        return None
                    
                    # Find the link element on current page
                    selectors_list = self.config.get("selectors", {}).get("article_list", [])
                    for selector in selectors_list:
                        try:
                            elements = await page.query_selector_all(selector)
                            if elements and page_result_idx < len(elements):
                                element = elements[page_result_idx]
                                link_elem = await element.query_selector("a")
                                if link_elem:
                                    return link_elem
                        except Exception as e:
                            self.logger.debug(f"Error with selector {selector} on page {page_num}: {e}")
                            continue
                    
                    return None

                # Resolve URLs by clicking links on the search results page
                # We navigate to the correct page for each link to avoid stale element references
                resolved_urls: List[Optional[str]] = []
                for idx, result_idx in enumerate(redirect_indices):
                    try:
                        self.logger.info(
                            f"Resolving URL {idx + 1}/{len(redirect_indices)} (result index {result_idx}): {redirect_urls[idx][:80]}..."
                        )

                        # Get link element by navigating to the correct page
                        link_element = await get_link_element_by_index(result_idx)
                        
                        if not link_element:
                            self.logger.warning(
                                f"Could not find link element for result index {result_idx}"
                            )
                            resolved_urls.append(None)
                            continue

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
