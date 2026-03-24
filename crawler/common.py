from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.config import Settings


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
    session.headers.update({"User-Agent": settings.user_agent})
    return session


def request_html(
    session: requests.Session,
    url: str,
    method: str,
    timeout_seconds: int,
    params: Optional[dict[str, Any]] = None,
    logger: Any = None,
) -> str:
    if method == "POST":
        response = session.post(url, data=params or {}, timeout=timeout_seconds)
    else:
        response = session.get(url, params=params or {}, timeout=timeout_seconds)

    if logger:
        logger.info("http_request", extra={"url": url, "status": response.status_code, "method": method})

    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def optional_playwright_fetch_html(url: str, settings: Settings, wait_selector: str = "body") -> str:
    if not settings.enable_playwright_fallback:
        raise RuntimeError("Playwright fallback is disabled")

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
