"""Unified stealth Playwright runner.

Combines stealth initialization, human behaviour, session persistence,
throttle control, proxy rotation, and detection logging into a single
reusable entry-point for Playwright-based scraping.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlparse

from crawler.behavior.human_behavior import pre_navigation_delay, simulate_page_read
from crawler.behavior.throttle import ThrottleConfig, ThrottleController
from crawler.detection.detection_logger import (
    CrawlOutcome,
    DetectionLogger,
    classify_outcome,
)
from crawler.network.proxy_manager import ProxyConfig, ProxyManager
from crawler.session.session_manager import SessionManager
from crawler.stealth.browser_stealth import create_stealth_context
from crawler.stealth.fingerprint_profiles import FingerprintProfile, pick_profile

logger = logging.getLogger(__name__)


class StealthCrawlerConfig:
    """Aggregated config consumed by StealthCrawler."""

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 30000,
        wait_selector: str = "body",
        enable_human_behavior: bool = True,
        enable_session_persistence: bool = True,
        session_ttl_hours: float = 24.0,
        session_dir: str = "",
        artifact_dir: str = "",
        throttle: ThrottleConfig | None = None,
        proxy: ProxyConfig | None = None,
        max_retries: int = 2,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.wait_selector = wait_selector
        self.enable_human_behavior = enable_human_behavior
        self.enable_session_persistence = enable_session_persistence
        self.session_ttl_hours = session_ttl_hours
        self.session_dir = session_dir
        self.artifact_dir = artifact_dir
        self.throttle = throttle or ThrottleConfig()
        self.proxy = proxy or ProxyConfig()
        self.max_retries = max_retries


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.hostname or "unknown"


def stealth_fetch_html(
    url: str,
    config: StealthCrawlerConfig | None = None,
    profile: FingerprintProfile | None = None,
    log: Any | None = None,
) -> str:
    """Fetch HTML from *url* using a stealth Playwright browser.

    Orchestrates all anti-detection layers:
    1. Stealth browser context (fingerprint patching)
    2. Optional session re-use
    3. Optional proxy
    4. Human-like behavior (scroll, mouse, dwell)
    5. Throttle between requests
    6. Detection logging with screenshot on failure

    Returns the page HTML on success; raises RuntimeError on persistent failure.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: playwright install chromium") from exc

    config = config or StealthCrawlerConfig()
    log = log or logger
    domain = _domain_from_url(url)

    session_mgr = SessionManager(session_dir=config.session_dir) if config.enable_session_persistence else None
    proxy_mgr = ProxyManager(config.proxy)
    throttle = ThrottleController(config.throttle)
    det_logger = DetectionLogger(artifact_dir=config.artifact_dir)

    if profile is None:
        profile = pick_profile()

    last_error: Exception | None = None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=config.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        for attempt in range(1, config.max_retries + 1):
            context = None
            page = None
            timed_out = False
            html = ""

            try:
                # --- Throttle ---
                if attempt > 1:
                    throttle.backoff_after_detection()
                else:
                    pre_navigation_delay()

                # --- Session state ---
                storage_state = None
                if session_mgr:
                    storage_state = session_mgr.load_state(domain)

                # --- Proxy ---
                proxy_dict = proxy_mgr.get_proxy(domain)

                # --- Stealth context ---
                context, used_profile = create_stealth_context(
                    browser,
                    profile=profile,
                    proxy=proxy_dict,
                    storage_state=storage_state,
                )

                page = context.new_page()

                # --- Navigate ---
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=config.timeout_ms)
                except PwTimeout:
                    timed_out = True

                if not timed_out:
                    try:
                        page.wait_for_selector(config.wait_selector, timeout=config.timeout_ms // 2)
                    except PwTimeout:
                        pass  # selector may not exist yet; classify below

                html = page.content() if not timed_out else ""

                # --- Human behavior ---
                if config.enable_human_behavior and not timed_out:
                    simulate_page_read(page)
                    html = page.content()  # re-read after JS may have rendered more

                # --- Classify outcome ---
                selector_found = bool(
                    not timed_out and page.query_selector(config.wait_selector)
                )
                outcome = classify_outcome(
                    html=html,
                    expected_selector_found=selector_found,
                    timed_out=timed_out,
                    url=url,
                )

                det_logger.log_event(
                    url=url,
                    outcome=outcome,
                    proxy=proxy_dict.get("server", "") if proxy_dict else "",
                    user_agent=used_profile.user_agent,
                    session_id=domain,
                    extra={"attempt": attempt},
                )

                if outcome == CrawlOutcome.SUCCESS:
                    throttle.reset_failure_streak()
                    # Save session on success
                    if session_mgr and context:
                        try:
                            session_mgr.save_state(context, domain, ttl_hours=config.session_ttl_hours)
                        except Exception:
                            pass  # non-critical
                    browser.close()
                    log.info(
                        "stealth_fetch_success",
                        extra={"url": url, "attempt": attempt, "profile": used_profile.platform},
                    )
                    return html

                # --- Capture failure artifacts ---
                if page:
                    det_logger.capture_screenshot(page, url, label=outcome)
                if html:
                    det_logger.capture_html(html, url, label=outcome)

                log.warning(
                    "stealth_fetch_blocked",
                    extra={"url": url, "attempt": attempt, "outcome": outcome},
                )

                # Report proxy failure so rotation can switch
                if proxy_dict:
                    proxy_mgr.report_failure(proxy_dict.get("server", ""), domain)

            except Exception as exc:
                last_error = exc
                log.warning(
                    "stealth_fetch_error",
                    extra={"url": url, "attempt": attempt, "error": str(exc)},
                )
                det_logger.log_event(
                    url=url,
                    outcome=CrawlOutcome.UNKNOWN_FAILURE,
                    error=str(exc),
                    extra={"attempt": attempt},
                )
            finally:
                if context:
                    try:
                        context.close()
                    except Exception:
                        pass

        # All retries exhausted
        browser.close()
        summary = det_logger.summary()
        log.error(
            "stealth_fetch_all_retries_exhausted",
            extra={"url": url, "attempts": config.max_retries, "summary": summary},
        )
        raise RuntimeError(
            f"Stealth fetch failed after {config.max_retries} attempts for {url}. "
            f"Summary: {summary}"
        ) from last_error
