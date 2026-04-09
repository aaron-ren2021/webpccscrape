from __future__ import annotations

import random
import time
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.config import Settings

# --- User-Agent rotation pool ---
_UA_POOL: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _pick_ua(settings: Settings) -> str:
    """Return a random UA from the pool, or the configured one if pool is bypassed."""
    if settings.user_agent != Settings.user_agent:
        # User explicitly set a custom UA via env; respect it.
        return settings.user_agent
    return random.choice(_UA_POOL)


def build_session(settings: Settings) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=settings.request_retry_total,
        connect=settings.request_retry_total,
        read=settings.request_retry_total,
        backoff_factor=settings.request_backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": _pick_ua(settings),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    })
    return session


def random_delay(settings: Settings, logger: Any = None) -> None:
    """Sleep for a random interval between request_delay_min and request_delay_max."""
    lo = settings.request_delay_min
    hi = settings.request_delay_max
    if hi <= 0:
        return
    wait = random.uniform(lo, hi)
    if logger:
        logger.debug("request_delay", extra={"wait_seconds": round(wait, 2)})
    time.sleep(wait)


def request_html(
    session: requests.Session,
    url: str,
    method: str,
    timeout_seconds: int,
    params: Optional[dict[str, Any]] = None,
    logger: Any = None,
    settings: Optional[Settings] = None,
) -> str:
    # Rotate User-Agent per request for extra stealth
    if settings:
        session.headers["User-Agent"] = _pick_ua(settings)

    if method == "POST":
        response = session.post(url, data=params or {}, timeout=timeout_seconds)
    else:
        response = session.get(url, params=params or {}, timeout=timeout_seconds)

    if logger:
        logger.info("http_request", extra={"url": url, "status": response.status_code, "method": method})

    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def optional_playwright_fetch_html(
    url: str,
    settings: Settings,
    wait_selector: str = "body",
    logger: Any = None,
) -> str:
    """Fetch HTML via Playwright. Uses stealth runner when stealth is enabled."""
    if not settings.enable_playwright_fallback:
        raise RuntimeError("Playwright fallback is disabled")

    if settings.stealth_enabled:
        return _stealth_playwright_fetch(url, settings, wait_selector, logger)

    # Legacy non-stealth path
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Playwright is not installed. Run: playwright install chromium") from exc

    with sync_playwright() as playwright:  # pragma: no cover
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(user_agent=settings.user_agent)
        page.goto(url, wait_until="networkidle", timeout=settings.playwright_timeout_ms)
        page.wait_for_selector(wait_selector, timeout=settings.playwright_timeout_ms)
        html = page.content()
        browser.close()
        return html


def _stealth_playwright_fetch(
    url: str,
    settings: Settings,
    wait_selector: str,
    logger: Any = None,
) -> str:
    """Delegate to the stealth runner with full anti-detection stack."""
    from crawler.behavior.throttle import ThrottleConfig
    from crawler.network.proxy_manager import ProxyConfig, ProxyEntry
    from crawler.stealth_runner import StealthCrawlerConfig, stealth_fetch_html

    throttle_cfg = ThrottleConfig(
        delay_min=settings.stealth_throttle_delay_min,
        delay_max=settings.stealth_throttle_delay_max,
        cooldown_after_n=settings.stealth_throttle_cooldown_after,
        cooldown_min=settings.stealth_throttle_cooldown_min,
        cooldown_max=settings.stealth_throttle_cooldown_max,
        backoff_base=settings.stealth_throttle_backoff_base,
    )

    proxy_entries = [ProxyEntry(server=s) for s in settings.proxy_list if s]
    proxy_cfg = ProxyConfig(
        enabled=settings.proxy_enabled and bool(proxy_entries),
        proxies=proxy_entries,
        strategy=settings.proxy_strategy,
    )

    cfg = StealthCrawlerConfig(
        headless=settings.stealth_headless,
        timeout_ms=settings.playwright_timeout_ms,
        wait_selector=wait_selector,
        enable_human_behavior=settings.stealth_human_behavior,
        enable_session_persistence=settings.stealth_session_persistence,
        session_ttl_hours=settings.stealth_session_ttl_hours,
        session_dir=settings.stealth_session_dir,
        artifact_dir=settings.stealth_artifact_dir,
        throttle=throttle_cfg,
        proxy=proxy_cfg,
        max_retries=settings.stealth_max_retries,
    )

    return stealth_fetch_html(url, config=cfg, log=logger)


def pick_first_text(node: Tag, selectors: list[str]) -> str:
    for selector in selectors:
        hit = node.select_one(selector)
        if hit and hit.get_text(strip=True):
            return hit.get_text(" ", strip=True)
    return ""


def pick_first_attr(node: Tag, selectors: list[str], attr: str) -> str:
    for selector in selectors:
        hit = node.select_one(selector)
        if hit and hit.has_attr(attr):
            value = hit.get(attr)
            if value:
                return str(value)
    return ""


def normalize_url(base: str, candidate: str) -> str:
    if not candidate:
        return ""
    return urljoin(base, candidate)


def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")
