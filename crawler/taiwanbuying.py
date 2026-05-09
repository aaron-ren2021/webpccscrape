from __future__ import annotations

import unicodedata
from typing import Any

from bs4 import Tag

from core.config import Settings
from core.filters import is_educational_org
from core.models import BidRecord
from core.normalize import parse_amount, parse_bid_date

from crawler.common import (
    build_session,
    normalize_url,
    optional_playwright_fetch_html,
    parse_html,
    pick_first_attr,
    pick_first_text,
    random_delay,
    request_html,
)

SOURCE_NAME = "taiwanbuying"
COMPUTER_CATEGORY_HINT = "電腦類"


def fetch_bids(settings: Settings, logger: Any) -> list[BidRecord]:
    """Fetch bids from taiwanbuying main page.
    
    Uses Playwright+Stealth if enabled, falls back to requests if disabled or failed.
    """
    # 🔥 優先使用 Playwright+Stealth
    if settings.stealth_enabled and settings.enable_playwright:
        logger.info("taiwanbuying_fetch_using_stealth")
        try:
            html = optional_playwright_fetch_html(
                settings.taiwanbuying_url, 
                settings, 
                wait_selector="body",
                logger=logger
            )
            records = _parse_records(html, settings)
            if records:
                logger.info("source_parsed", extra={"source": SOURCE_NAME, "count": len(records), "method": "stealth"})
                return records
        except Exception as exc:
            logger.warning("taiwanbuying_stealth_failed_fallback_requests", extra={"error": str(exc)})
    
    # Fallback to requests+BeautifulSoup
    session = build_session(settings)
    html = request_html(
        session=session,
        url=settings.taiwanbuying_url,
        method=settings.taiwanbuying_method,
        params=settings.taiwanbuying_params,
        timeout_seconds=settings.request_timeout_seconds,
        logger=logger,
        settings=settings,
    )
    records = _parse_records(html, settings)

    if not records and settings.enable_playwright:
        logger.warning("taiwanbuying_requests_empty_try_playwright")
        try:
            html = optional_playwright_fetch_html(settings.taiwanbuying_url, settings, logger=logger)
            records = _parse_records(html, settings)
        except Exception as exc:
            logger.exception("taiwanbuying_playwright_failed", extra={"error": str(exc)})

    logger.info("source_parsed", extra={"source": SOURCE_NAME, "count": len(records), "method": "requests"})
    return records


def _parse_records(html: str, settings: Settings) -> list[BidRecord]:
    soup = parse_html(html)

    rows: list[Tag] = []
    for selector in settings.taiwanbuying_row_selectors:
        rows = soup.select(selector)
        if rows:
            break

    # TODO: If source HTML changes, update selector env vars first instead of changing code.
    if not rows:
        rows = [anchor for anchor in soup.select("a") if anchor.get_text(strip=True)]

    output: list[BidRecord] = []
    for row in rows:
        title = pick_first_text(row, settings.taiwanbuying_title_selectors) or row.get_text(" ", strip=True)
        title = title[:300].strip()
        if not title:
            continue

        org = pick_first_text(row, settings.taiwanbuying_org_selectors)
        date_text = pick_first_text(row, settings.taiwanbuying_date_selectors)
        amount_text = pick_first_text(row, settings.taiwanbuying_amount_selectors)
        summary = pick_first_text(row, settings.taiwanbuying_summary_selectors)
        category = pick_first_text(row, settings.taiwanbuying_category_selectors)
        link = pick_first_attr(row, settings.taiwanbuying_link_selectors, "href")

        bid_date = parse_bid_date(date_text)
        amount_value = parse_amount(amount_text)
        url = normalize_url(settings.taiwanbuying_url, link)
        normalized_category = normalize_taiwanbuying_category(category)
        metadata: dict[str, Any] = {
            "raw_date": date_text,
            "taiwanbuying_category": category,
            "taiwanbuying_category_normalized": normalized_category,
        }
        if is_taiwanbuying_computer_category(category) and is_educational_org(org):
            metadata.update(
                {
                    "candidate_only": True,
                    "category_hint": "computer_edu",
                    "category_hint_source": SOURCE_NAME,
                }
            )

        output.append(
            BidRecord(
                title=title,
                organization=org,
                bid_date=bid_date,
                amount_raw=amount_text,
                amount_value=amount_value,
                source=SOURCE_NAME,
                url=url,
                summary=summary,
                category=category,
                metadata=metadata,
            )
        )
    return output


def normalize_taiwanbuying_category(category: str) -> str:
    normalized = unicodedata.normalize("NFKC", category or "")
    return "".join(normalized.split()).lower()


def is_taiwanbuying_computer_category(category: str) -> bool:
    return COMPUTER_CATEGORY_HINT in normalize_taiwanbuying_category(category)
