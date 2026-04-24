"""Batch crawler with identity rotation for cumulative risk mitigation.

This module provides batch URL processing with automatic identity rotation
to prevent cumulative detection. Each identity (fingerprint + session + proxy)
is used for a limited number of requests before rotation.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Optional

from playwright.sync_api import BrowserContext, Page, sync_playwright, TimeoutError as PwTimeout

from crawler.behavior.human_behavior import pre_navigation_delay, simulate_page_read, simulate_idle_reading
from crawler.behavior.throttle import ThrottleConfig, ThrottleController
from crawler.detection.detection_logger import (
    CrawlOutcome,
    DetectionLogger,
    classify_outcome_with_page,
)
from crawler.detection.strategies import get_retry_strategy
from crawler.identity_manager import IdentityManager
from crawler.session.session_manager import SessionManager
from crawler.stealth.browser_stealth import create_stealth_context
from crawler.stealth.fingerprint_profiles import FingerprintProfile, apply_profile_overrides

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
    locale_pool: Optional[list[str]] = None,
    timezone_pool: Optional[list[str]] = None,
    align_locale_timezone_with_proxy: bool = False,
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
        current_identity_id: str = ""
        current_profile: Optional[FingerprintProfile] = None
        behavior_intensity = "normal"

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
                    or identity.id != current_identity_id
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

                    active_profile = apply_profile_overrides(
                        identity.fingerprint,
                        locale_pool=list(locale_pool or []),
                        timezone_pool=list(timezone_pool or []),
                        align_with_proxy=align_locale_timezone_with_proxy,
                        proxy_server=identity.proxy or "",
                    )

                    # Create new context with current identity
                    current_context, _ = create_stealth_context(
                        browser,
                        profile=active_profile,
                        proxy=proxy_dict,
                        storage_state=storage_state,
                    )
                    current_page = current_context.new_page()
                    current_domain = domain
                    current_identity_id = identity.id
                    current_profile = active_profile

                    log.info(
                        "batch_context_created",
                        extra={
                            "identity_id": identity.id,
                            "domain": domain,
                            "platform": active_profile.platform,
                        },
                    )

                # Throttle before request
                if idx > 0:
                    throttle.wait_before_request()
                    if behavior_intensity == "elevated":
                        pre_navigation_delay()
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
                        if behavior_intensity == "elevated":
                            simulate_page_read(current_page)
                        html = current_page.content()  # Re-read after JS rendering

                except PwTimeout:
                    timed_out = True
                except Exception as exc:
                    log.warning("batch_fetch_error", extra={"url": url, "error": str(exc)})
                    det_logger.log_failure(
                        page=current_page,
                        html=html,
                        url=url,
                        outcome=CrawlOutcome.UNKNOWN_FAILURE,
                        proxy=identity.proxy or "",
                        user_agent=(current_profile.user_agent if current_profile else identity.fingerprint.user_agent),
                        session_id=domain,
                        error=str(exc),
                        extra={
                            "identity_id": identity.id,
                            "batch_index": idx,
                            "actions": ["backoff", "rotate_identity"],
                            "human_behavior_intensity": "elevated",
                        },
                    )
                    result.failed.append((url, f"unknown_failure: {exc}"))
                    identity_mgr.record_request(success=False)
                    throttle.record_failure()
                    behavior_intensity = "elevated"

                    # Context may be stale/crashed — close it so next iteration recreates
                    if current_context:
                        try:
                            current_context.close()
                        except Exception:
                            pass
                        current_context = None
                        current_page = None
                    continue

                # Classify outcome
                selector_found = bool(current_page.query_selector(wait_selector)) if not timed_out else False
                outcome = classify_outcome_with_page(
                    page=current_page,
                    html=html,
                    expected_selector_found=selector_found,
                    timed_out=timed_out,
                    url=url,
                )

                strategy_plan = get_retry_strategy(
                    outcome,
                    1,
                    context={"runner": "batch"},
                )

                det_logger.log_failure(
                    page=current_page,
                    html=html,
                    url=url,
                    outcome=outcome,
                    proxy=identity.proxy or "",
                    user_agent=(current_profile.user_agent if current_profile else identity.fingerprint.user_agent),
                    session_id=domain,
                    extra={
                        "identity_id": identity.id,
                        "batch_index": idx,
                        "actions": list(strategy_plan.actions),
                        "human_behavior_intensity": strategy_plan.human_behavior_intensity,
                    },
                )

                # Handle outcome
                if outcome == CrawlOutcome.SUCCESS:
                    result.successful.append((url, html))
                    identity_mgr.record_request(success=True)
                    throttle.reset_failure_streak()
                    behavior_intensity = "normal"

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
                    result.failed.append((url, str(outcome)))
                    identity_mgr.record_request(success=False)
                    throttle.record_failure()  # Record for adaptive throttling
                    behavior_intensity = strategy_plan.human_behavior_intensity

                    log.warning(
                        "batch_fetch_failed",
                        extra={
                            "url": url,
                            "outcome": outcome,
                            "identity_id": identity.id,
                            "actions": list(strategy_plan.actions),
                        },
                    )

                    if "rotate_identity" in strategy_plan.actions or "rotate_proxy" in strategy_plan.actions:
                        # Force identity rotation
                        identity_mgr.force_rotation()

                        # Close context immediately for identity reset
                        if current_context:
                            try:
                                current_context.close()
                            except Exception:
                                pass
                            current_context = None
                            current_page = None

                    if "backoff" in strategy_plan.actions and strategy_plan.cooldown_range:
                        low, high = strategy_plan.cooldown_range
                        cooldown = random.uniform(low, high)
                        log.info(
                            "batch_failure_cooldown",
                            extra={
                                "outcome": outcome,
                                "cooldown_seconds": round(cooldown, 1),
                                "actions": list(strategy_plan.actions),
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
