"""
URL resolver for extracting real URLs from Sogou redirect links.

This module implements URL resolution using Chrome DevTools Protocol (CDP)
to track network traffic and redirects, extracting the final target URLs
from Sogou redirect links.

The resolver uses CDP Network domain events to track:
- HTTP redirects (301/302)
- JavaScript redirects (window.location)
- Meta Refresh redirects
- Frame navigation events
"""

import asyncio
import logging
import time
from typing import List, Optional, Dict, Tuple, Any
from playwright.async_api import Page, CDPSession


class URLResolver:
    """
    URL resolver using Chrome DevTools Protocol.

    This class tracks network traffic and page navigation to extract
    the final target URL from Sogou redirect links.

    Attributes:
        logger: Logger instance for debugging
        target_domains: List of target domain patterns to validate
        redirect_timeout: Maximum time to wait for redirects (seconds)
        cache: In-memory cache for resolved URLs (url -> (resolved_url, timestamp))
        cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
    """

    def __init__(
        self,
        target_domains: List[str],
        redirect_timeout: float = 8.0,
        cache_ttl: int = 3600,
    ) -> None:
        """
        Initialize URL resolver.

        Args:
            target_domains: List of target domain patterns
                (e.g., ["mp.weixin.qq.com", "zhihu.com"])
            redirect_timeout: Maximum time to wait for redirects (default: 5.0s)
            cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
        """
        self.logger = logging.getLogger(__name__)
        self.target_domains = target_domains
        self.redirect_timeout = redirect_timeout
        self.cache: Dict[str, Tuple[str, float]] = {}
        self.cache_ttl = cache_ttl

    def _get_cached_url(self, sogou_url: str) -> Optional[str]:
        """
        Get cached resolved URL if available and not expired.

        Args:
            sogou_url: Sogou redirect URL

        Returns:
            Cached resolved URL if available and not expired, None otherwise
        """
        if sogou_url in self.cache:
            resolved_url, timestamp = self.cache[sogou_url]
            if time.time() - timestamp < self.cache_ttl:
                self.logger.debug(f"Cache hit for URL: {sogou_url}")
                return resolved_url
            else:
                # Cache expired, remove it
                del self.cache[sogou_url]

        return None

    def _cache_url(self, sogou_url: str, resolved_url: str) -> None:
        """
        Cache resolved URL.

        Args:
            sogou_url: Sogou redirect URL
            resolved_url: Resolved target URL
        """
        self.cache[sogou_url] = (resolved_url, time.time())
        self.logger.debug(f"Cached URL resolution: {sogou_url} -> {resolved_url}")

    async def resolve_url(self, page: Page, sogou_url: str) -> Optional[str]:
        """
        Resolve Sogou redirect URL to final target URL using CDP.

        This method:
        1. Checks cache first
        2. Creates a CDP session for the page
        3. Enables Network and Page domains
        4. Sets up event listeners for redirects
        5. Navigates to the Sogou redirect URL
        6. Tracks all redirects until reaching target domain
        7. Returns the final URL and caches it

        Args:
            page: Playwright Page instance
            sogou_url: Sogou redirect URL to resolve

        Returns:
            Final target URL if resolution succeeds, None otherwise
        """
        if not sogou_url or "sogou.com/link" not in sogou_url:
            self.logger.debug(f"Invalid Sogou URL: {sogou_url}")
            return None

        # Check cache first
        cached_url = self._get_cached_url(sogou_url)
        if cached_url:
            return cached_url

        # Create CDP session
        cdp_session: Optional[CDPSession] = None
        try:
            cdp_session = await page.context.new_cdp_session(page)

            # Enable Network and Page domains
            await cdp_session.send("Network.enable")
            await cdp_session.send("Page.enable")

            # Track redirects
            redirect_chain: List[str] = [sogou_url]
            final_url: Optional[str] = None
            navigation_complete = asyncio.Event()

            # Network event handlers
            async def on_request_will_be_sent(params: Dict[str, Any]) -> None:
                """Track request URLs."""
                request_url = params.get("request", {}).get("url", "")
                if request_url and request_url not in redirect_chain:
                    redirect_chain.append(request_url)
                    self.logger.debug(f"Request: {request_url}")

            async def on_response_received(params: Dict[str, Any]) -> None:
                """Track response URLs and check for redirects."""
                nonlocal final_url
                response = params.get("response", {})
                response_url = response.get("url", "")
                status = response.get("status", 0)

                # Check for HTTP redirects (301, 302, etc.)
                if status in [301, 302, 303, 307, 308]:
                    location = response.get("headers", {}).get("location", "")
                    if location:
                        redirect_chain.append(location)
                        self.logger.debug(f"HTTP redirect {status}: {location}")

                # Check if we reached target domain
                if response_url:
                    for target_domain in self.target_domains:
                        if target_domain in response_url and "sogou.com" not in response_url:
                            final_url = response_url
                            navigation_complete.set()
                            self.logger.info(
                                f"Reached target domain {target_domain}: {response_url}"
                            )
                            return

            async def on_frame_navigated(params: Dict[str, Any]) -> None:
                """Track frame navigation events."""
                nonlocal final_url
                frame = params.get("frame", {})
                frame_url = frame.get("url", "")

                if frame_url and frame_url not in redirect_chain:
                    redirect_chain.append(frame_url)
                    self.logger.debug(f"Frame navigated: {frame_url}")

                    # Check if we reached target domain
                    for target_domain in self.target_domains:
                        if target_domain in frame_url and "sogou.com" not in frame_url:
                            final_url = frame_url
                            navigation_complete.set()
                            self.logger.info(f"Frame navigated to target: {frame_url}")
                            return

            # Register event listeners
            cdp_session.on("Network.requestWillBeSent", on_request_will_be_sent)
            cdp_session.on("Network.responseReceived", on_response_received)
            cdp_session.on("Page.frameNavigated", on_frame_navigated)

            # Set appropriate headers
            referer_url = sogou_url.split("/link")[0] if "/link" in sogou_url else sogou_url
            await page.set_extra_http_headers(
                {
                    "Referer": referer_url,
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                }
            )

            # Navigate to Sogou redirect URL
            # Some Sogou links open in new tabs, so we need to track both
            # the current page navigation and potential new page opens
            self.logger.debug(f"Navigating to Sogou redirect: {sogou_url}")

            # Set up listener for new pages (tabs) that might open
            new_page_url: Optional[str] = None
            new_page_event = asyncio.Event()
            new_page_obj: Optional[Page] = None

            async def on_page_created(new_page: Page) -> None:
                """Track when a new page/tab is created."""
                nonlocal new_page_url, final_url, new_page_obj
                try:
                    new_page_obj = new_page
                    # Wait for the new page to load
                    await new_page.wait_for_load_state("domcontentloaded", timeout=5000)
                    new_page_url = new_page.url
                    self.logger.debug(f"New page/tab opened: {new_page_url}")

                    # Check if it's a target domain
                    for target_domain in self.target_domains:
                        if target_domain in new_page_url and "sogou.com" not in new_page_url:
                            final_url = new_page_url
                            navigation_complete.set()
                            self.logger.info(
                                f"New page reached target domain {target_domain}: {final_url}"
                            )
                            new_page_event.set()
                            return
                    new_page_event.set()
                except Exception as e:
                    self.logger.debug(f"Error tracking new page: {e}")

            # Listen for new pages BEFORE navigation
            page.context.on("page", on_page_created)

            try:
                # Use networkidle to wait for all network activity including redirects
                await page.goto(sogou_url, wait_until="networkidle", timeout=15000)
            except Exception as e:
                self.logger.debug(
                    f"Navigation with networkidle failed: {e}, trying domcontentloaded"
                )
                try:
                    await page.goto(sogou_url, wait_until="domcontentloaded", timeout=10000)
                except Exception as e2:
                    self.logger.debug(f"Navigation error: {e2}")

            # After navigation, check if we need to click a link to get to target
            # Some Sogou pages require clicking a link to reach the final destination
            if not final_url and "sogou.com" in page.url:
                self.logger.debug("Still on Sogou page, looking for target domain links to click")
                try:
                    # Wait a bit for page to fully load
                    await asyncio.sleep(1.0)

                    # Look for links containing target domains
                    for target_domain in self.target_domains:
                        # Try to find a link with target domain
                        link_selector = f"a[href*='{target_domain}']"
                        link_element = await page.query_selector(link_selector)

                        if link_element:
                            self.logger.debug(
                                f"Found link with target domain {target_domain}, clicking..."
                            )
                            # Click the link and wait for new page/tab to open
                            async with page.context.expect_page(timeout=5000) as new_page_info:
                                await link_element.click()

                            try:
                                new_page = await new_page_info.value
                                await new_page.wait_for_load_state("domcontentloaded", timeout=5000)
                                new_page_url = new_page.url
                                self.logger.debug(f"New page/tab opened: {new_page_url}")

                                if (
                                    target_domain in new_page_url
                                    and "sogou.com" not in new_page_url
                                ):
                                    final_url = new_page_url
                                    navigation_complete.set()
                                    self.logger.info(f"New page reached target domain: {final_url}")
                                    await new_page.close()  # Close new page after getting URL
                                    break
                            except Exception as e:
                                self.logger.debug(f"Error handling new page: {e}")
                                # If new page didn't open, try regular navigation
                                try:
                                    async with page.expect_navigation(
                                        timeout=5000, wait_until="domcontentloaded"
                                    ):
                                        await link_element.click()
                                    await asyncio.sleep(1.0)
                                except Exception:
                                    pass
                except Exception as e:
                    self.logger.debug(f"Error clicking link: {e}")

            # Wait for redirect to complete or timeout
            # Also wait for new page event (in case link opens in new tab)
            try:
                # Wait for either navigation complete or new page event
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(navigation_complete.wait()),
                        asyncio.create_task(new_page_event.wait()),
                    ],
                    timeout=self.redirect_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()

                # If new page was created, use its URL
                if new_page_url and not final_url:
                    for target_domain in self.target_domains:
                        if target_domain in new_page_url and "sogou.com" not in new_page_url:
                            final_url = new_page_url
                            self.logger.info(f"Using new page URL: {final_url}")
                            break

            except asyncio.TimeoutError:
                self.logger.debug(f"Redirect timeout after {self.redirect_timeout}s")

            # Check all pages in context (in case new tabs were opened)
            # This is important because Sogou links often open in new tabs
            if not final_url:
                all_pages = page.context.pages
                self.logger.debug(f"Checking {len(all_pages)} pages in context")
                for p in all_pages:
                    try:
                        page_url = p.url
                        self.logger.debug(f"Found page with URL: {page_url}")
                        for target_domain in self.target_domains:
                            if target_domain in page_url and "sogou.com" not in page_url:
                                final_url = page_url
                                self.logger.info(f"Found target domain in page: {final_url}")
                                break
                        if final_url:
                            break
                    except Exception as e:
                        self.logger.debug(f"Error checking page URL: {e}")

            # Check final page URL with multiple attempts
            if not final_url:
                max_checks = 5
                check_interval = 0.5
                for check_num in range(max_checks):
                    current_url = page.url
                    self.logger.debug(
                        f"Check {check_num + 1}/{max_checks}: Current URL: {current_url}"
                    )

                    # Check if we reached target domain
                    for target_domain in self.target_domains:
                        if target_domain in current_url and "sogou.com" not in current_url:
                            final_url = current_url
                            self.logger.info(f"Reached target domain {target_domain}: {final_url}")
                            break

                    if final_url:
                        break

                    # Wait a bit before next check (except for last check)
                    if check_num < max_checks - 1:
                        await asyncio.sleep(check_interval)

            # Final check of page URL
            if not final_url:
                current_url = page.url
                self.logger.debug(f"Final page URL check: {current_url}")
                for target_domain in self.target_domains:
                    if target_domain in current_url and "sogou.com" not in current_url:
                        final_url = current_url
                        self.logger.info(f"Using final page URL: {final_url}")
                        break

            # Log redirect chain for debugging
            if len(redirect_chain) > 1:
                self.logger.debug(f"Redirect chain ({len(redirect_chain)} hops):")
                for i, url in enumerate(redirect_chain):
                    self.logger.debug(f"  {i + 1}. {url}")

            # Use resolved URL or fallback to original
            resolved = final_url if final_url else sogou_url

            # Cache the result (even if it's the original URL)
            self._cache_url(sogou_url, resolved)

            return resolved

        except Exception as e:
            self.logger.error(f"Error resolving URL {sogou_url}: {e}")
            return None
        finally:
            # Clean up CDP session
            if cdp_session:
                try:
                    await cdp_session.detach()
                except Exception as e:
                    self.logger.debug(f"Error detaching CDP session: {e}")

            # Close new page if it was opened (to avoid resource leaks)
            # Note: We don't close it here as it might be needed by the caller
            # The caller should manage page lifecycle

    async def resolve_urls_batch(self, page: Page, sogou_urls: List[str]) -> List[Optional[str]]:
        """
        Resolve multiple Sogou redirect URLs in batch.

        This method processes multiple URLs sequentially using the same page
        to improve performance. Each URL resolution is independent.

        Args:
            page: Playwright Page instance (reused for all URLs)
            sogou_urls: List of Sogou redirect URLs to resolve

        Returns:
            List of resolved URLs (None for failed resolutions)
        """
        resolved_urls: List[Optional[str]] = []

        for idx, sogou_url in enumerate(sogou_urls):
            self.logger.debug(f"Resolving URL {idx + 1}/{len(sogou_urls)}: {sogou_url}")

            try:
                resolved_url = await self.resolve_url(page, sogou_url)
                resolved_urls.append(resolved_url)

                # Small delay between requests to avoid rate limiting
                if idx < len(sogou_urls) - 1:
                    await asyncio.sleep(0.5)

            except Exception as e:
                self.logger.warning(f"Failed to resolve URL {sogou_url}: {e}")
                resolved_urls.append(None)

        return resolved_urls
