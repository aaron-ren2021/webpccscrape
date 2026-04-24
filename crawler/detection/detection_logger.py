from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default directory for failure artifacts
_DEFAULT_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".detection_logs")


# ---------------------------------------------------------------------------
# CrawlOutcome – StrEnum for type safety & ergonomic string comparison
# ---------------------------------------------------------------------------

class CrawlOutcome(StrEnum):
    """Enumeration of possible crawl result types."""

    SUCCESS = "success"
    SOFT_BLOCK = "soft_block"
    HARD_BLOCK = "hard_block"
    CAPTCHA = "captcha"
    TIMEOUT = "timeout"
    REDIRECT_CHALLENGE = "redirect_challenge"
    EMPTY_CONTENT = "empty_content"
    UNKNOWN_FAILURE = "unknown_failure"
    ACCESS_DENIED = "access_denied"
    CLOUDFLARE_CHALLENGE = "cloudflare_challenge"
    RATE_LIMITED = "rate_limited"


# ---------------------------------------------------------------------------
# DetectionRule – data-driven rule engine
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DetectionRule:
    """A single content-based detection rule.

    Attributes:
        outcome:  The CrawlOutcome to return when this rule matches.
        patterns: Compiled regex patterns – *any* match triggers the rule.
        priority: Higher values are evaluated first.
        locators: Optional Playwright CSS selectors for DOM-level detection.
    """

    outcome: CrawlOutcome
    patterns: list[re.Pattern[str]]
    priority: int
    locators: list[str] = field(default_factory=list)


# Rules are ordered by priority descending at module load time.
DETECTION_RULES: list[DetectionRule] = sorted(
    [
        DetectionRule(
            outcome=CrawlOutcome.CAPTCHA,
            patterns=[
                re.compile(
                    r"驗證碼檢核|請輸入驗證碼|captcha|recaptcha|hcaptcha"
                    r"|cf-turnstile|請完成驗證",
                    re.IGNORECASE,
                ),
            ],
            priority=100,
            locators=[
                "form[action*='captcha']",
                "#captcha",
                ".g-recaptcha",
                ".h-captcha",
                "[class*='cf-turnstile']",
            ],
        ),
        DetectionRule(
            outcome=CrawlOutcome.CLOUDFLARE_CHALLENGE,
            patterns=[
                re.compile(
                    r"cf-browser-verification|challenge-platform"
                    r"|Just a moment|Checking your browser"
                    r"|_cf_chl_opt|managed_checking_msg"
                    r"|cf-wrapper|__cf_chl_jschl_tk__|__cf_chl_",
                    re.IGNORECASE,
                ),
            ],
            priority=90,
            locators=[
                "div#challenge-running",
                "form#challenge-form",
                "#cf-wrapper",
            ],
        ),
        DetectionRule(
            outcome=CrawlOutcome.ACCESS_DENIED,
            patterns=[
                re.compile(
                    r"access\s*denied|存取被拒|拒絕存取"
                    r"|403\s*forbidden|您無權限存取",
                    re.IGNORECASE,
                ),
            ],
            priority=80,
        ),
        DetectionRule(
            outcome=CrawlOutcome.RATE_LIMITED,
            patterns=[
                re.compile(
                    r"too\s*many\s*requests|請稍後再試"
                    r"|rate\s*limit|請求過於頻繁",
                    re.IGNORECASE,
                ),
            ],
            priority=70,
        ),
        DetectionRule(
            outcome=CrawlOutcome.SOFT_BLOCK,
            patterns=[
                re.compile(
                    r"unusual\s*traffic|異常流量"
                    r"|suspicious\s*activity|請重新整理",
                    re.IGNORECASE,
                ),
            ],
            priority=60,
        ),
    ],
    key=lambda r: r.priority,
    reverse=True,
)


# ---------------------------------------------------------------------------
# classify_outcome – synchronous, regex-based
# ---------------------------------------------------------------------------

def classify_outcome(
    html: str,
    status_code: int = 200,
    expected_selector_found: bool = True,
    timed_out: bool = False,
    url: str = "",
) -> CrawlOutcome:
    """Classify a crawl attempt into a standard outcome category.

    Classification priority (high → low):
      1. Timeout
      2. HTTP status codes (403, 429, 5xx)
      3. Content-based rules via ``DETECTION_RULES`` (regex, ordered by priority)
      4. Empty content (expected selector not found)
      5. Success
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

    # Content-based detection via rule engine (any() short-circuits early)
    for rule in DETECTION_RULES:
        if any(p.search(html) for p in rule.patterns):
            return rule.outcome

    # Expected DOM element was not found
    if not expected_selector_found:
        return CrawlOutcome.EMPTY_CONTENT

    return CrawlOutcome.SUCCESS


# ---------------------------------------------------------------------------
# classify_outcome_with_page – synchronous, Playwright locator + regex fallback
# ---------------------------------------------------------------------------

def classify_outcome_with_page(
    page: Any,
    html: str,
    status_code: int = 200,
    expected_selector_found: bool = True,
    timed_out: bool = False,
    url: str = "",
) -> CrawlOutcome:
    """Enhanced sync classification using Playwright locators + regex fallback."""
    if timed_out:
        return CrawlOutcome.TIMEOUT

    if status_code == 403:
        return CrawlOutcome.HARD_BLOCK
    if status_code == 429:
        return CrawlOutcome.RATE_LIMITED
    if status_code >= 500:
        return CrawlOutcome.UNKNOWN_FAILURE

    if page is not None:
        for rule in DETECTION_RULES:
            if not rule.locators:
                continue
            combined = ", ".join(rule.locators)
            try:
                if page.locator(combined).count() > 0:
                    return rule.outcome
            except Exception:
                pass

        try:
            verify_btn = page.get_by_role(
                "button",
                name=re.compile(r"驗證|Verify|Continue|Submit", re.IGNORECASE),
            )
            if verify_btn.count() > 0:
                return CrawlOutcome.CAPTCHA
        except Exception:
            pass

    for rule in DETECTION_RULES:
        if any(p.search(html) for p in rule.patterns):
            return rule.outcome

    if not expected_selector_found:
        return CrawlOutcome.EMPTY_CONTENT

    return CrawlOutcome.SUCCESS


# ---------------------------------------------------------------------------
# classify_outcome_advanced – async, Playwright locator + regex fallback
# ---------------------------------------------------------------------------

async def classify_outcome_advanced(
    page: Any,
    html: str,
    status_code: int = 200,
    expected_selector_found: bool = True,
    timed_out: bool = False,
    url: str = "",
) -> CrawlOutcome:
    """Enhanced classification using Playwright locators with regex fallback.

    When a Playwright *page* object is available, DOM-level inspection is
    performed first (more accurate than text matching).  Falls back to the
    same regex rules used by :func:`classify_outcome`.
    """
    if timed_out:
        return CrawlOutcome.TIMEOUT

    if status_code == 403:
        return CrawlOutcome.HARD_BLOCK
    if status_code == 429:
        return CrawlOutcome.RATE_LIMITED
    if status_code >= 500:
        return CrawlOutcome.UNKNOWN_FAILURE

    # DOM-level detection via Playwright locators (highest accuracy)
    if page is not None:
        for rule in DETECTION_RULES:
            if rule.locators:
                combined = ", ".join(rule.locators)
                try:
                    if await page.locator(combined).count() > 0:
                        return rule.outcome
                except Exception:
                    pass  # locator evaluation failed; fall through to regex

        # Generic verify / continue button → CAPTCHA indicator
        try:
            verify_btn = page.get_by_role(
                "button",
                name=re.compile(r"驗證|Verify|Continue|Submit", re.IGNORECASE),
            )
            if await verify_btn.count() > 0:
                return CrawlOutcome.CAPTCHA
        except Exception:
            pass

    # Fallback: regex-based content detection
    for rule in DETECTION_RULES:
        if any(p.search(html) for p in rule.patterns):
            return rule.outcome

    if not expected_selector_found:
        return CrawlOutcome.EMPTY_CONTENT

    return CrawlOutcome.SUCCESS


# ---------------------------------------------------------------------------
# DetectionLogger – event logging & failure artifact capture
# ---------------------------------------------------------------------------

class DetectionLogger:
    """Log detection events and capture failure artifacts (screenshots, HTML)."""

    def __init__(self, artifact_dir: str = "") -> None:
        self._artifact_dir = Path(artifact_dir or _DEFAULT_ARTIFACT_DIR)
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        self._events: list[dict[str, Any]] = []

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # --- event recording ---------------------------------------------------

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

    # --- sync artifact capture ---------------------------------------------

    def capture_screenshot(self, page: Any, url: str, label: str = "") -> str:
        """Take a screenshot of the current page (sync). Returns file path."""
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

    # --- async artifact capture --------------------------------------------

    async def async_capture_screenshot(self, page: Any, url: str, label: str = "") -> str:
        """Take a screenshot of the current page (async). Returns file path."""
        ts = self._ts()
        safe_label = (label or "fail").replace("/", "_")[:30]
        filename = f"{ts}_{safe_label}.png"
        path = self._artifact_dir / filename
        try:
            await page.screenshot(path=str(path), full_page=True)
            logger.info("screenshot_captured", extra={"path": str(path), "url": url})
        except Exception as exc:
            logger.warning("screenshot_failed", extra={"error": str(exc), "url": url})
            return ""
        return str(path)

    # --- convenience: auto-capture on failure ------------------------------

    def log_failure(
        self,
        page: Any,
        html: str,
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
        """Log a failure event and auto-capture screenshot + HTML artifacts."""
        event = self.log_event(
            url=url,
            outcome=outcome,
            status_code=status_code,
            proxy=proxy,
            user_agent=user_agent,
            session_id=session_id,
            error=error,
            extra=extra,
        )
        if outcome != CrawlOutcome.SUCCESS:
            if page:
                self.capture_screenshot(page, url, label=outcome)
            if html:
                self.capture_html(html, url, label=outcome)
        return event

    async def async_log_failure(
        self,
        page: Any,
        html: str,
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
        """Async version: log failure event and auto-capture artifacts."""
        event = self.log_event(
            url=url,
            outcome=outcome,
            status_code=status_code,
            proxy=proxy,
            user_agent=user_agent,
            session_id=session_id,
            error=error,
            extra=extra,
        )
        if outcome != CrawlOutcome.SUCCESS:
            if page:
                await self.async_capture_screenshot(page, url, label=outcome)
            if html:
                self.capture_html(html, url, label=outcome)
        return event

    # --- statistics --------------------------------------------------------

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def summary(self) -> dict[str, int]:
        """Return a counter dict of outcome → count."""
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
