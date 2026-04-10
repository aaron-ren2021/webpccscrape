from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default directory for failure artifacts
_DEFAULT_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".detection_logs")


class CrawlOutcome:
    """Enumeration of possible crawl result types."""

    SUCCESS = "success"
    SOFT_BLOCK = "soft_block"      # Page loaded but content hidden / challenge presented
    HARD_BLOCK = "hard_block"      # HTTP 403 / explicit deny
    CAPTCHA = "captcha"            # CAPTCHA page detected
    TIMEOUT = "timeout"            # Page load timed out
    REDIRECT_CHALLENGE = "redirect_challenge"  # Redirected to a challenge page
    EMPTY_CONTENT = "empty_content"  # Page loaded but no expected content found
    UNKNOWN_FAILURE = "unknown_failure"
    ACCESS_DENIED = "access_denied"  # Explicit access denied message
    CLOUDFLARE_CHALLENGE = "cloudflare_challenge"  # Cloudflare bot challenge
    RATE_LIMITED = "rate_limited"  # Too many requests / rate limit hit


# Common indicators for challenge / block pages
_CAPTCHA_MARKERS = [
    "驗證碼檢核",
    "請輸入驗證碼",
    "captcha",
    "recaptcha",
    "hCaptcha",
    "cf-turnstile",
    "請完成驗證",
]

_CLOUDFLARE_MARKERS = [
    "cf-browser-verification",
    "challenge-platform",
    "Just a moment",
    "Checking your browser",
    "_cf_chl_opt",
    "managed_checking_msg",
    "cf-wrapper",
    "__cf_chl_jschl_tk__",
]

_ACCESS_DENIED_MARKERS = [
    "access denied",
    "存取被拒",
    "拒絕存取",
    "403 forbidden",
    "您無權限存取",
]

_RATE_LIMIT_MARKERS = [
    "too many requests",
    "請稍後再試",
    "rate limit",
    "請求過於頻繁",
    "429",
]

_SOFT_BLOCK_MARKERS = [
    "unusual traffic",
    "異常流量",
    "suspicious activity",
    "請重新整理",
]


def classify_outcome(
    html: str,
    status_code: int = 200,
    expected_selector_found: bool = True,
    timed_out: bool = False,
    url: str = "",
) -> str:
    """Classify a crawl attempt into a standard outcome category.
    
    Classification priority (high to low):
    1. Timeout
    2. HTTP status codes (403, 429, 5xx)
    3. CAPTCHA markers
    4. Cloudflare challenge markers
    5. Access denied markers
    6. Rate limit markers
    7. Soft block markers
    8. Empty content
    9. Success
    """
    if timed_out:
        return CrawlOutcome.TIMEOUT

    # HTTP status-based classification
    if status_code == 403:
        return CrawlOutcome.HARD_BLOCK
    if status_code == 429:
        return CrawlOutcome.RATE_LIMITED
    if status_code >= 500:
        return CrawlOutcome.UNKNOWN_FAILURE

    html_lower = html.lower()

    # Check for CAPTCHA (highest priority for content-based detection)
    for marker in _CAPTCHA_MARKERS:
        if marker.lower() in html_lower:
            return CrawlOutcome.CAPTCHA

    # Check for Cloudflare challenge
    for marker in _CLOUDFLARE_MARKERS:
        if marker.lower() in html_lower:
            return CrawlOutcome.CLOUDFLARE_CHALLENGE

    # Check for explicit access denied
    for marker in _ACCESS_DENIED_MARKERS:
        if marker.lower() in html_lower:
            return CrawlOutcome.ACCESS_DENIED

    # Check for rate limiting
    for marker in _RATE_LIMIT_MARKERS:
        if marker.lower() in html_lower:
            return CrawlOutcome.RATE_LIMITED

    # Check for soft blocks
    for marker in _SOFT_BLOCK_MARKERS:
        if marker.lower() in html_lower:
            return CrawlOutcome.SOFT_BLOCK

    # Check if expected content is missing
    if not expected_selector_found:
        return CrawlOutcome.EMPTY_CONTENT

    return CrawlOutcome.SUCCESS


class DetectionLogger:
    """Log detection events and capture failure artifacts (screenshots, HTML)."""

    def __init__(self, artifact_dir: str = "") -> None:
        self._artifact_dir = Path(artifact_dir or _DEFAULT_ARTIFACT_DIR)
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        self._events: list[dict[str, Any]] = []

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def log_event(
        self,
        url: str,
        outcome: str,
        *,
        status_code: int = 0,
        proxy: str = "",
        user_agent: str = "",
        session_id: str = "",
        error: str = "",
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record a crawl outcome event and return the event dict."""
        event = {
            "timestamp": self._ts(),
            "url": url,
            "outcome": outcome,
            "status_code": status_code,
            "proxy": proxy,
            "user_agent": user_agent[:80] if user_agent else "",
            "session_id": session_id,
            "error": error,
        }
        if extra:
            event.update(extra)

        self._events.append(event)

        log_fn = logger.info if outcome == CrawlOutcome.SUCCESS else logger.warning
        log_fn("crawl_outcome", extra=event)
        return event

    def capture_screenshot(self, page: Any, url: str, label: str = "") -> str:
        """Take a screenshot of the current page. Returns the file path."""
        ts = self._ts()
        safe_label = (label or "fail").replace("/", "_")[:30]
        filename = f"{ts}_{safe_label}.png"
        path = self._artifact_dir / filename
        try:
            page.screenshot(path=str(path), full_page=True)
            logger.info("screenshot_captured", extra={"path": str(path), "url": url})
        except Exception as exc:
            logger.warning("screenshot_failed", extra={"error": str(exc), "url": url})
            return ""
        return str(path)

    def capture_html(self, html: str, url: str, label: str = "") -> str:
        """Save raw HTML snapshot for post-mortem analysis. Returns file path."""
        ts = self._ts()
        safe_label = (label or "fail").replace("/", "_")[:30]
        filename = f"{ts}_{safe_label}.html"
        path = self._artifact_dir / filename
        try:
            path.write_text(html, encoding="utf-8")
            logger.info("html_snapshot_saved", extra={"path": str(path), "url": url})
        except Exception as exc:
            logger.warning("html_snapshot_failed", extra={"error": str(exc), "url": url})
            return ""
        return str(path)

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def summary(self) -> dict[str, int]:
        """Return a counter dict of outcome -> count."""
        counts: dict[str, int] = {}
        for ev in self._events:
            outcome = ev.get("outcome", CrawlOutcome.UNKNOWN_FAILURE)
            counts[outcome] = counts.get(outcome, 0) + 1
        return counts

    def success_rate(self) -> float:
        """Return overall success rate as a float 0.0 – 1.0."""
        total = len(self._events)
        if total == 0:
            return 0.0
        successes = sum(1 for ev in self._events if ev.get("outcome") == CrawlOutcome.SUCCESS)
        return successes / total

    def export_events_json(self, output_path: str) -> None:
        """Export all logged events to a JSON file for analysis."""
        import json
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._events, f, indent=2, ensure_ascii=False)
        
        logger.info("events_exported", extra={"path": str(output_path), "count": len(self._events)})
