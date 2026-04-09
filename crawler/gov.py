from __future__ import annotations

import random
import time
from typing import Any

from bs4 import Tag

from core.config import Settings
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

SOURCE_NAME = "gov_pcc"


def fetch_bids(settings: Settings, logger: Any) -> list[BidRecord]:
    session = build_session(settings)
    html = request_html(
        session=session,
        url=settings.gov_url,
        method=settings.gov_method,
        params=settings.gov_params,
        timeout_seconds=settings.request_timeout_seconds,
        logger=logger,
        settings=settings,
    )
    records = _parse_records(html, settings, logger)

    if not records and settings.enable_playwright_fallback:
        logger.warning("gov_requests_empty_try_playwright")
        try:
            html = optional_playwright_fetch_html(settings.gov_url, settings, logger=logger)
            records = _parse_records(html, settings, logger)
        except Exception as exc:
            logger.exception("gov_playwright_failed", extra={"error": str(exc)})

    logger.info("source_parsed", extra={"source": SOURCE_NAME, "count": len(records)})
    return records


def enrich_detail(records: list[BidRecord], settings: Settings, logger: Any) -> None:
    """Fetch detail pages for gov_pcc records and extract budget_amount / bid_bond."""
    session = build_session(settings)
    delay = settings.gov_detail_delay_seconds
    captcha_count = 0

    for idx, record in enumerate(records):
        if record.source != SOURCE_NAME or not record.url:
            continue

        # Throttle requests with random delay to avoid triggering gov.pcc CAPTCHA
        if idx > 0:
            random_delay(settings, logger)

        try:
            html = request_html(
                session=session,
                url=record.url,
                method="GET",
                timeout_seconds=settings.request_timeout_seconds,
                logger=logger,
                settings=settings,
            )

            if _is_captcha_page(html):
                captcha_count += 1
                logger.warning(
                    "gov_detail_captcha_detected",
                    extra={"url": record.url, "attempt": 1},
                )
                # Reset session and wait longer before retrying
                session = build_session(settings)
                time.sleep(delay * 3 + random.uniform(1, 3))

                html = request_html(
                    session=session,
                    url=record.url,
                    method="GET",
                    timeout_seconds=settings.request_timeout_seconds,
                    logger=logger,
                    settings=settings,
                )
                if _is_captcha_page(html):
                    logger.warning(
                        "gov_detail_captcha_persistent",
                        extra={"url": record.url},
                    )
                    continue

            soup = parse_html(html)
            _extract_detail_fields(soup, record)
        except Exception as exc:
            logger.warning("gov_detail_fetch_failed", extra={"url": record.url, "error": str(exc)})

    if captcha_count:
        logger.warning(
            "gov_detail_captcha_summary",
            extra={"captcha_hits": captcha_count, "total": len(records)},
        )


def _is_captcha_page(html: str) -> bool:
    """Detect gov.pcc CAPTCHA (card-matching verification) page."""
    return "驗證碼檢核" in html


def _extract_detail_fields(soup: Any, record: BidRecord) -> None:
    """Extract 預算金額, 押標金, 截止投標, 開標時間 from a gov.pcc detail page."""
    import re

    for td in soup.find_all("td"):
        text = td.get_text(strip=True)

        # --- 預算金額（精確匹配，排除「是否公開」） ---
        if text == "預算金額":
            nxt = td.find_next_sibling("td")
            if nxt:
                val = nxt.get_text(strip=True)
                amount_match = re.search(r"[\d,]+", val)
                if amount_match:
                    record.budget_amount = f"NT$ {amount_match.group()} 元"

        elif text == "預算金額是否公開":
            nxt = td.find_next_sibling("td")
            if nxt:
                val = nxt.get_text(strip=True)
                if val.startswith("否"):
                    record.budget_amount = "未公開"
                elif not record.budget_amount:
                    # 公開但沒有獨立的預算金額列
                    record.budget_amount = "已公開（金額見詳細頁）"

        # --- 押標金 ---
        elif text == "是否須繳納押標金":
            nxt = td.find_next_sibling("td")
            if nxt:
                val = nxt.get_text(" ", strip=True)
                if val.startswith("否"):
                    record.bid_bond = "免繳"
                else:
                    pct_match = re.search(r"押標金額度[：:]\s*([\d,.]+%)", val)
                    if pct_match:
                        record.bid_bond = pct_match.group(1)
                    else:
                        amt_match = re.search(r"押標金額度[：:]\s*([\d,]+)", val)
                        if amt_match:
                            record.bid_bond = f"NT$ {amt_match.group(1)} 元"
                        else:
                            record.bid_bond = "需繳納"

        # --- 截止投標 ---
        elif text == "截止投標":
            nxt = td.find_next_sibling("td")
            if nxt:
                val = nxt.get_text(strip=True)
                # 格式通常是 "115/04/07 17:00"
                record.bid_deadline = val

        # --- 開標時間 ---
        elif text == "開標時間":
            nxt = td.find_next_sibling("td")
            if nxt:
                val = nxt.get_text(strip=True)
                # 格式通常是 "115/04/08 10:00"
                record.bid_opening_time = val


def _parse_records(html: str, settings: Settings, logger: Any) -> list[BidRecord]:
    soup = parse_html(html)

    rows: list[Tag] = []
    for selector in settings.gov_row_selectors:
        rows = soup.select(selector)
        if rows:
            break

    # TODO: 政府採購頁面常調整 DOM，建議優先以 GOV_*_SELECTORS 環境變數調整。
    if not rows:
        rows = [anchor for anchor in soup.select("a") if anchor.get_text(strip=True)]

    output: list[BidRecord] = []
    for row in rows:
        title = pick_first_text(row, settings.gov_title_selectors) or row.get_text(" ", strip=True)
        title = title[:300].strip()
        if not title:
            continue

        org = pick_first_text(row, settings.gov_org_selectors)
        date_text = pick_first_text(row, settings.gov_date_selectors)
        amount_text = pick_first_text(row, settings.gov_amount_selectors)
        summary = pick_first_text(row, settings.gov_summary_selectors)
        link = pick_first_attr(row, settings.gov_link_selectors, "href")

        bid_date = parse_bid_date(date_text)
        amount_value = parse_amount(amount_text)

        output.append(
            BidRecord(
                title=title,
                organization=org,
                bid_date=bid_date,
                amount_raw=amount_text,
                amount_value=amount_value,
                source=SOURCE_NAME,
                url=normalize_url(settings.gov_url, link),
                summary=summary,
                metadata={
                    "raw_date": date_text,
                },
            )
        )
    
    return output
