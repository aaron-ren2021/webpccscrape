"""Batch crawler with identity rotation for cumulative risk mitigation.

This module provides batch URL processing with automatic identity rotation
to prevent cumulative detection. Each identity (fingerprint + session + proxy)
is used for a limited number of requests before rotation.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Callable, Optional

from playwright.sync_api import BrowserContext, Page, sync_playwright, TimeoutError as PwTimeout

from crawler.behavior.human_behavior import pre_navigation_delay, simulate_page_read, simulate_idle_reading
from crawler.behavior.throttle import ThrottleConfig, ThrottleController
from crawler.detection.detection_logger import (
    CrawlOutcome,
    DetectionLogger,
    classify_outcome,
)
from crawler.identity_manager import IdentityManager
from crawler.session.session_manager import SessionManager
from crawler.stealth.browser_stealth import create_stealth_context

logger = logging.getLogger(__name__)


class BatchCrawlResult:
    """Container for batch crawl results."""

    def __init__(self) -> None:
        self.successful: list[tuple[str, str]] = []  # (url, html)
        self.failed: list[tuple[str, str]] = []  # (url, reason)
        self.total: int = 0

    @property
    def success_count(self) -> int:
        return len(self.successful)

    @property
    def failure_count(self) -> int:
        return len(self.failed)

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.success_count / self.total


def batch_stealth_fetch(
    urls: list[str],
    *,
    max_requests_per_identity: int = 4,
    headless: bool = True,
    timeout_ms: int = 30000,
    wait_selector: str = "body",
    enable_human_behavior: bool = True,
    enable_session_persistence: bool = True,
    session_dir: str = "",
    artifact_dir: str = "",
    throttle_config: Optional[ThrottleConfig] = None,
    proxy_list: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    log: Any = None,
) -> BatchCrawlResult:
    """Batch fetch URLs with automatic identity rotation.

    This function processes multiple URLs while automatically rotating
    identities (fingerprint + session + proxy) every N requests to avoid
    cumulative detection.

    Args:
        urls: List of URLs to fetch
        max_requests_per_identity: Max requests per identity before rotation
        headless: Run browser in headless mode
        timeout_ms: Page load timeout in milliseconds
        wait_selector: CSS selector to wait for
        enable_human_behavior: Enable human-like behavior simulation
        enable_session_persistence: Enable session state persistence
        session_dir: Directory for session storage
        artifact_dir: Directory for failure artifacts
        throttle_config: Throttle configuration (uses default if None)
        proxy_list: List of proxies to rotate through
        progress_callback: Callback function(current, total) for progress updates
        log: Logger instance

    Returns:
        BatchCrawlResult with successful and failed fetches
    """
    log = log or logger
    result = BatchCrawlResult()
    result.total = len(urls)

    if not urls:
        log.warning("batch_stealth_fetch_empty_urls")
        return result

    # Initialize managers
    identity_mgr = IdentityManager(
        max_requests_per_identity=max_requests_per_identity,
        enable_proxy_rotation=bool(proxy_list),
        proxy_list=proxy_list or [],
    )
    session_mgr = SessionManager(session_dir=session_dir) if enable_session_persistence else None
    throttle = ThrottleController(throttle_config or ThrottleConfig())
    det_logger = DetectionLogger(artifact_dir=artifact_dir)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        current_context: Optional[BrowserContext] = None
        current_page: Optional[Page] = None
        current_domain: str = ""

        try:
            for idx, url in enumerate(urls):
                # Get current or new identity
                identity = identity_mgr.get_identity()

                # Extract domain for session management
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain = parsed.netloc or parsed.hostname or "unknown"

                # Create new context if:
                # 1. No context exists yet
                # 2. Identity changed (rotation occurred)
                # 3. Domain changed (need different session)
                should_create_context = (
                    current_context is None
                    or domain != current_domain
                )

                if should_create_context:
                    # Close previous context
                    if current_context:
                        try:
                            current_context.close()
                        except Exception:
                            pass
                        current_context = None
                        current_page = None

                    # Load session state if available
                    storage_state = None
                    if session_mgr:
                        storage_state = session_mgr.load_state(domain)

                    # Create proxy dict
                    proxy_dict = None
                    if identity.proxy:
                        proxy_dict = {"server": identity.proxy}

                    # Create new context with current identity
                    current_context, _ = create_stealth_context(
                        browser,
                        profile=identity.fingerprint,
                        proxy=proxy_dict,
                        storage_state=storage_state,
                    )
                    current_page = current_context.new_page()
                    current_domain = domain

                    log.info(
                        "batch_context_created",
                        extra={
                            "identity_id": identity.id,
                            "domain": domain,
                            "platform": identity.fingerprint.platform,
                        },
                    )

                # Throttle before request
                if idx > 0:
                    throttle.wait_before_request()
                else:
                    pre_navigation_delay()

                # Navigate to URL
                timed_out = False
                html = ""

                try:
                    current_page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                    # Wait for selector
                    try:
                        current_page.wait_for_selector(wait_selector, timeout=timeout_ms // 2)
                    except PwTimeout:
                        pass

                    html = current_page.content()

                    # Human behavior simulation (with pattern-breaking variety)
                    if enable_human_behavior:
                        # 🎲 30% chance of idle reading (less interaction)
                        # 70% chance of active reading (scroll + mouse)
                        if random.random() < 0.3:
                            simulate_idle_reading(current_page)
                        else:
                            simulate_page_read(current_page)
                        html = current_page.content()  # Re-read after JS rendering

                except PwTimeout:
                    timed_out = True
                except Exception as exc:
                    log.warning("batch_fetch_error", extra={"url": url, "error": str(exc)})
                    result.failed.append((url, f"error: {exc}"))
                    identity_mgr.record_request(success=False)
                    continue

                # Classify outcome
                selector_found = bool(current_page.query_selector(wait_selector)) if not timed_out else False
                outcome = classify_outcome(
                    html=html,
                    expected_selector_found=selector_found,
                    timed_out=timed_out,
                    url=url,
                )

                det_logger.log_event(
                    url=url,
                    outcome=outcome,
                    proxy=identity.proxy or "",
                    user_agent=identity.fingerprint.user_agent,
                    session_id=domain,
                    extra={"identity_id": identity.id, "batch_index": idx},
                )

                # Handle outcome
                if outcome == CrawlOutcome.SUCCESS:
                    result.successful.append((url, html))
                    identity_mgr.record_request(success=True)
                    throttle.reset_failure_streak()

                    # Save session on success
                    if session_mgr and current_context:
                        try:
                            session_mgr.save_state(current_context, domain, ttl_hours=24.0)
                        except Exception:
                            pass

                    log.info(
                        "batch_fetch_success",
                        extra={
                            "url": url,
                            "identity_id": identity.id,
                            "progress": f"{idx + 1}/{len(urls)}",
                        },
                    )
                else:
                    result.failed.append((url, outcome))
                    identity_mgr.record_request(success=False)
                    throttle.record_failure()  # Record for adaptive throttling

                    # Capture artifacts
                    det_logger.capture_screenshot(current_page, url, label=outcome)
                    if html:
                        det_logger.capture_html(html, url, label=outcome)

                    log.warning(
                        "batch_fetch_failed",
                        extra={
                            "url": url,
                            "outcome": outcome,
                            "identity_id": identity.id,
                        },
                    )

                    # 🔥 FAIL FAST + RESET: Terminal failures trigger immediate reset
                    if outcome in (
                        CrawlOutcome.CAPTCHA,
                        CrawlOutcome.HARD_BLOCK,
                        CrawlOutcome.ACCESS_DENIED,
                        CrawlOutcome.CLOUDFLARE_CHALLENGE,
                    ):
                        # Force identity rotation
                        identity_mgr.force_rotation()
                        
                        # Close context immediately (fail fast)
                        if current_context:
                            try:
                                current_context.close()
                            except Exception:
                                pass
                            current_context = None
                            current_page = None
                        
                        # Long cooldown: 60-180 seconds
                        import random
                        import time
                        cooldown = random.uniform(60, 180)
                        log.warning(
                            "fail_fast_reset",
                            extra={
                                "outcome": outcome,
                                "cooldown_seconds": round(cooldown, 1),
                                "message": "Terminal failure detected. Closing context and cooling down.",
                            },
                        )
                        time.sleep(cooldown)
                    
                    # Recoverable failures: moderate cooldown
                    elif outcome in (
                        CrawlOutcome.RATE_LIMITED,
                        CrawlOutcome.SOFT_BLOCK,
                    ):
                        # Moderate cooldown: 20-60 seconds
                        import random
                        import time
                        cooldown = random.uniform(20, 60)
                        log.info(
                            "recoverable_failure_cooldown",
                            extra={
                                "outcome": outcome,
                                "cooldown_seconds": round(cooldown, 1),
                            },
                        )
                        time.sleep(cooldown)

                # Progress callback
                if progress_callback:
                    progress_callback(idx + 1, len(urls))

        finally:
            # Cleanup
            if current_context:
                try:
                    current_context.close()
                except Exception:
                    pass
            browser.close()

    # Log final statistics
    stats = identity_mgr.get_statistics()
    log.info(
        "batch_crawl_complete",
        extra={
            "total_urls": len(urls),
            "successful": result.success_count,
            "failed": result.failure_count,
            "success_rate": f"{result.success_rate * 100:.1f}%",
            "identities_used": stats["total_identities"],
        },
    )

    return result
