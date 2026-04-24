"""Unified stealth Playwright runner.

Combines stealth initialization, human behaviour, session persistence,
throttle control, proxy rotation, and detection logging into a single
reusable entry-point for Playwright-based scraping.
"""
from __future__ import annotations

import logging
import random
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse

from crawler.behavior.human_behavior import pre_navigation_delay, simulate_page_read
from crawler.behavior.throttle import ThrottleConfig, ThrottleController
from crawler.detection.detection_logger import (
    CrawlOutcome,
    DetectionLogger,
    classify_outcome_with_page,
)
from crawler.detection.strategies import get_retry_strategy
from crawler.network.proxy_manager import ProxyConfig, ProxyManager
from crawler.session.session_manager import SessionManager
from crawler.stealth.browser_stealth import create_stealth_context
from crawler.stealth.fingerprint_profiles import (
    FingerprintProfile,
    apply_profile_overrides,
    pick_profile,
)

logger = logging.getLogger(__name__)


class CrawlStrategy(str, Enum):
    """Pre-defined crawl strategy profiles for adaptive anti-detection."""

    STEALTH = "stealth"        # Maximum stealth: long delays, full behavior simulation
    BALANCED = "balanced"      # Balanced approach: moderate delays and behavior
    AGGRESSIVE = "aggressive"  # Fast crawling: shorter delays, basic behavior


def _create_strategy_config(strategy: CrawlStrategy) -> dict[str, Any]:
    """Create a configuration dict based on the selected strategy."""
    if strategy == CrawlStrategy.STEALTH:
        return {
            "throttle": ThrottleConfig(
                delay_min=3.0,
                delay_max=9.0,
                cooldown_after_n=4,
                cooldown_min=15.0,
                cooldown_max=35.0,
                jitter_factor=0.5,
            ),
            "max_retries": 2,
            "enable_human_behavior": True,
            "max_requests_per_identity": 3,  # More conservative in stealth mode
        }
    elif strategy == CrawlStrategy.AGGRESSIVE:
        return {
            "throttle": ThrottleConfig(
                delay_min=0.8,
                delay_max=4.0,
                cooldown_after_n=8,
                cooldown_min=5.0,
                cooldown_max=12.0,
                jitter_factor=0.3,
            ),
            "max_retries": 3,
            "enable_human_behavior": True,
            "max_requests_per_identity": 6,  # More aggressive = more requests per identity
        }
    else:  # BALANCED (default)
        return {
            "throttle": ThrottleConfig(
                delay_min=1.5,
                delay_max=7.5,
                cooldown_after_n=5,
                cooldown_min=10.0,
                cooldown_max=25.0,
                jitter_factor=0.4,
            ),
            "max_retries": 2,
            "enable_human_behavior": True,
            "max_requests_per_identity": 4,  # Balanced approach
        }


def pick_strategy(seed: Optional[int] = None) -> CrawlStrategy:
    """Randomly select a crawl strategy. Optionally seed for reproducibility."""
    strategies = list(CrawlStrategy)
    if seed is not None:
        rng = random.Random(seed)
        return rng.choice(strategies)
    return random.choice(strategies)


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
        max_requests_per_identity: int = 4,  # New: identity rotation threshold
        locale_pool: list[str] | None = None,
        timezone_pool: list[str] | None = None,
        align_locale_timezone_with_proxy: bool = False,
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
        self.max_requests_per_identity = max_requests_per_identity
        self.locale_pool = list(locale_pool or [])
        self.timezone_pool = list(timezone_pool or [])
        self.align_locale_timezone_with_proxy = align_locale_timezone_with_proxy


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.hostname or "unknown"


def stealth_fetch_html(
    url: str,
    config: StealthCrawlerConfig | None = None,
    profile: FingerprintProfile | None = None,
    strategy: CrawlStrategy | None = None,
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

    If *strategy* is provided but *config* is None, a config will be
    auto-generated from the strategy. If both are None, a random strategy
    is selected.

    Returns the page HTML on success; raises RuntimeError on persistent failure.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: playwright install chromium") from exc

    # Strategy-based config generation
    if config is None:
        if strategy is None:
            strategy = pick_strategy()
        strategy_params = _create_strategy_config(strategy)
        config = StealthCrawlerConfig(**strategy_params)
        logger.info("crawl_strategy_selected", extra={"url": url, "strategy": strategy})
    
    log = log or logger
    domain = _domain_from_url(url)

    session_mgr = SessionManager(session_dir=config.session_dir) if config.enable_session_persistence else None
    proxy_mgr = ProxyManager(config.proxy)
    throttle = ThrottleController(config.throttle)
    det_logger = DetectionLogger(artifact_dir=config.artifact_dir)

    if profile is None:
        profile = pick_profile(
            locale_pool=config.locale_pool,
            timezone_pool=config.timezone_pool,
            align_with_proxy=False,
        )

    last_error: Exception | None = None
    behavior_intensity = "normal"

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
            proxy_dict: dict[str, str] | None = None
            used_profile = profile

            try:
                # --- Throttle ---
                if attempt > 1:
                    throttle.backoff_after_detection()
                    if behavior_intensity == "elevated":
                        pre_navigation_delay()
                else:
                    pre_navigation_delay()

                # --- Session state ---
                storage_state = None
                if session_mgr:
                    storage_state = session_mgr.load_state(domain)

                # --- Proxy ---
                proxy_dict = proxy_mgr.get_proxy(domain)

                # --- Stealth context ---
                active_profile = apply_profile_overrides(
                    profile,
                    locale_pool=config.locale_pool,
                    timezone_pool=config.timezone_pool,
                    align_with_proxy=config.align_locale_timezone_with_proxy,
                    proxy_server=(proxy_dict or {}).get("server", ""),
                )

                context, used_profile = create_stealth_context(
                    browser,
                    profile=active_profile,
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
                    if behavior_intensity == "elevated":
                        simulate_page_read(page)
                    html = page.content()  # re-read after JS may have rendered more

                # --- Classify outcome ---
                selector_found = bool(
                    not timed_out and page.query_selector(config.wait_selector)
                )
                outcome = classify_outcome_with_page(
                    page=page,
                    html=html,
                    expected_selector_found=selector_found,
                    timed_out=timed_out,
                    url=url,
                )

                strategy_plan = get_retry_strategy(
                    outcome,
                    attempt,
                    context={"runner": "single", "max_retries": config.max_retries},
                )
                event = det_logger.log_failure(
                    page=page,
                    html=html,
                    url=url,
                    outcome=outcome,
                    proxy=proxy_dict.get("server", "") if proxy_dict else "",
                    user_agent=used_profile.user_agent,
                    session_id=domain,
                    extra={
                        "attempt": attempt,
                        "actions": list(strategy_plan.actions),
                        "human_behavior_intensity": strategy_plan.human_behavior_intensity,
                    },
                )

                if outcome == CrawlOutcome.SUCCESS:
                    throttle.reset_failure_streak()
                    behavior_intensity = "normal"
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

                log.warning(
                    "stealth_fetch_blocked",
                    extra={
                        "url": url,
                        "attempt": attempt,
                        "outcome": outcome,
                        "actions": event.get("actions", []),
                    },
                )

                behavior_intensity = strategy_plan.human_behavior_intensity
                throttle.record_failure()

                if "abort" in strategy_plan.actions or not strategy_plan.retry:
                    log.error(
                        "stealth_fetch_terminal_failure",
                        extra={
                            "url": url,
                            "outcome": outcome,
                            "failure_reason": "Aborting retries for terminal failure",
                        },
                    )
                    browser.close()
                    raise RuntimeError(
                        f"Terminal failure detected ({outcome}) for {url}. Not retrying."
                    )

                if "rotate_profile" in strategy_plan.actions:
                    profile = pick_profile(
                        locale_pool=config.locale_pool,
                        timezone_pool=config.timezone_pool,
                        align_with_proxy=False,
                    )
                    log.info(
                        "stealth_fetch_rotating_fingerprint",
                        extra={
                            "url": url,
                            "outcome": outcome,
                            "new_platform": profile.platform,
                        },
                    )

                if "rotate_proxy" in strategy_plan.actions and proxy_dict:
                    proxy_mgr.report_failure(proxy_dict.get("server", ""), domain)

            except RuntimeError:
                raise
            except Exception as exc:
                last_error = exc
                log.warning(
                    "stealth_fetch_error",
                    extra={"url": url, "attempt": attempt, "error": str(exc)},
                )
                det_logger.log_failure(
                    page=page,
                    html=html,
                    url=url,
                    outcome=CrawlOutcome.UNKNOWN_FAILURE,
                    proxy=proxy_dict.get("server", "") if proxy_dict else "",
                    user_agent=used_profile.user_agent if used_profile else "",
                    session_id=domain,
                    error=str(exc),
                    extra={
                        "attempt": attempt,
                        "actions": ["backoff", "rotate_proxy"],
                        "human_behavior_intensity": "elevated",
                    },
                )
                throttle.record_failure()
                behavior_intensity = "elevated"
                if proxy_dict:
                    proxy_mgr.report_failure(proxy_dict.get("server", ""), domain)
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
