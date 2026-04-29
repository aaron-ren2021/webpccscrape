from __future__ import annotations

import random
import re
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


def _parse_bid_bond_value(value: str) -> str:
    """Parse bid bond amount/ratio while ignoring online payment fee text."""
    text = value.replace("\u3000", " ").strip()
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["否", "免", "不需", "無需", "不繳", "waived"]):
        return "免繳"

    amount_text = text
    label_match = re.search(r"押標金額度[：:\s]*", amount_text)
    has_amount_label = bool(label_match)
    if label_match:
        amount_text = amount_text[label_match.end():]
    amount_text = re.split(r"(?:廠商線上繳納押標金)?手續費[：:：\s]*", amount_text, maxsplit=1)[0]

    pct_match = re.search(r"百分之\s*([\d,.]+)", amount_text) or re.search(r"([\d,.]+)\s*[%％]", amount_text)
    if pct_match:
        return f"{pct_match.group(1).strip()}%"

    amount_patterns = [
        r"(?:新臺?幣|NT\$?)\s*([\d,]+)\s*元?",
        r"([\d,]+)\s*元(?:整)?",
    ]
    for pat in amount_patterns:
        amt_match = re.search(pat, amount_text)
        if amt_match:
            return f"NT$ {amt_match.group(1)} 元"
    if has_amount_label:
        amt_match = re.search(r"([\d,]+)", amount_text)
        if amt_match:
            return f"NT$ {amt_match.group(1)} 元"

    return "需繳納"


def fetch_bids(settings: Settings, logger: Any) -> list[BidRecord]:
    """Fetch bids from gov.pcc main list page.
    
    Uses Playwright+Stealth if enabled, falls back to requests if disabled or failed.
    """
    degraded_block_mode = False

    # 🔥 Phase 2: 優先使用 Playwright+Stealth
    if settings.stealth_enabled and settings.enable_playwright:
        logger.info("gov_fetch_using_stealth")
        blocked_attempts = 0
        max_blocked_attempts = max(1, settings.gov_block_circuit_breaker_threshold)
        try:
            html = optional_playwright_fetch_html(
                settings.gov_url, 
                settings, 
                wait_selector="table[id='row']",
                logger=logger
            )
            records = _parse_records(html, settings, logger)
            if records:
                logger.info("source_parsed", extra={"source": SOURCE_NAME, "count": len(records), "method": "stealth"})
                return records
        except Exception as exc:
            blocked_attempts += _rate_limited_hits(exc)
            logger.warning("gov_stealth_failed_fallback_requests", extra={"error": str(exc)})
            if blocked_attempts >= max_blocked_attempts:
                degraded_block_mode = True
                logger.warning(
                    "gov_list_circuit_breaker_triggered",
                    extra={"blocked_attempts": blocked_attempts, "threshold": max_blocked_attempts},
                )
    
    # Fallback to requests+BeautifulSoup
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
    if settings.stealth_enabled and settings.enable_playwright and degraded_block_mode:
        for record in records:
            record.metadata["detail_fetch_mode"] = "degraded_blocked"

    if not records and settings.enable_playwright:
        logger.warning("gov_requests_empty_try_playwright")
        try:
            html = optional_playwright_fetch_html(settings.gov_url, settings, logger=logger)
            records = _parse_records(html, settings, logger)
        except Exception as exc:
            logger.exception("gov_playwright_failed", extra={"error": str(exc)})

    logger.info("source_parsed", extra={"source": SOURCE_NAME, "count": len(records), "method": "requests"})
    return records


def enrich_detail(records: list[BidRecord], settings: Settings, logger: Any) -> None:
    """Fetch detail pages for gov_pcc records and extract budget_amount / bid_bond.
    
    🔥 Uses batch_stealth_fetch with identity rotation if stealth is enabled,
    otherwise falls back to traditional requests approach.
    """
    # Filter records that need enrichment
    gov_records = [r for r in records if r.source == SOURCE_NAME and r.url]
    if not gov_records:
        return

    degraded_records = [r for r in gov_records if str(r.metadata.get("detail_fetch_mode", "")).strip() == "degraded_blocked"]
    if degraded_records:
        logger.warning(
            "gov_detail_skip_degraded_blocked",
            extra={"count": len(degraded_records), "reason": "list_fetch_blocked_circuit_breaker"},
        )
        gov_records = [r for r in gov_records if r not in degraded_records]
        if not gov_records:
            return
    
    # 🔥 Phase 1: 優先使用 Playwright+Stealth 批次抓取
    if settings.stealth_enabled and settings.enable_playwright:
        try:
            enrich_detail_stealth(gov_records, settings, logger)
            return
        except Exception as exc:
            logger.warning("gov_detail_stealth_failed", extra={"error": str(exc)})
            # If stealth fails (CAPTCHA), requests won't fare better — skip fallback
            logger.info("gov_detail_skip_requests_fallback",
                        extra={"reason": "detail page CAPTCHA persists across methods"})
            return
    
    # Fallback to traditional requests approach (only when stealth is disabled)
    enrich_detail_requests(gov_records, settings, logger)


def enrich_detail_stealth(records: list[BidRecord], settings: Settings, logger: Any) -> None:
    """🔥 NEW: Enrich detail using batch_stealth_fetch with identity rotation.
    
    This is the PRIMARY method to avoid CAPTCHA. Uses identity rotation every N requests
    to prevent cumulative detection (gov.pcc typically blocks after 5-6 requests).
    """
    from crawler.batch_crawler import batch_stealth_fetch
    from crawler.behavior.throttle import ThrottleConfig
    
    # Collect URLs to fetch
    urls = [r.url for r in records if r.url]
    if not urls:
        return
    
    logger.info(
        "gov_detail_enriching_stealth",
        extra={
            "count": len(urls),
            "max_per_identity": settings.gov_detail_max_per_identity,
        }
    )
    
    # Configure throttle for gov.pcc (conservative settings to avoid CAPTCHA)
    throttle_config = ThrottleConfig(
        delay_min=settings.stealth_throttle_delay_min,
        delay_max=settings.stealth_throttle_delay_max,
        cooldown_after_n=settings.stealth_throttle_cooldown_after,
        cooldown_min=settings.stealth_throttle_cooldown_min,
        cooldown_max=settings.stealth_throttle_cooldown_max,
        backoff_base=settings.stealth_throttle_backoff_base,
    )
    
    # 🔥 Batch fetch with identity rotation
    # Only attempt first 2 URLs; if both fail with CAPTCHA, skip the rest
    probe_urls = urls[:2]
    result = batch_stealth_fetch(
        probe_urls,
        max_requests_per_identity=settings.gov_detail_max_per_identity,
        headless=settings.stealth_headless,
        timeout_ms=settings.playwright_timeout_ms,
        wait_selector="table.tb_01",  # Wait for detail table
        enable_human_behavior=settings.stealth_human_behavior,
        enable_session_persistence=settings.stealth_session_persistence,
        session_dir=settings.stealth_session_dir,
        artifact_dir=settings.stealth_artifact_dir,
        throttle_config=throttle_config,
        proxy_list=settings.proxy_list if settings.proxy_enabled else None,
        log=logger,
    )
    
    # If probe succeeded on any URL, fetch the rest
    if result.success_count > 0 and len(urls) > 2:
        remaining_result = batch_stealth_fetch(
            urls[2:],
            max_requests_per_identity=settings.gov_detail_max_per_identity,
            headless=settings.stealth_headless,
            timeout_ms=settings.playwright_timeout_ms,
            wait_selector="table.tb_01",
            enable_human_behavior=settings.stealth_human_behavior,
            enable_session_persistence=settings.stealth_session_persistence,
            session_dir=settings.stealth_session_dir,
            artifact_dir=settings.stealth_artifact_dir,
            throttle_config=throttle_config,
            proxy_list=settings.proxy_list if settings.proxy_enabled else None,
            log=logger,
        )
        result.successful.extend(remaining_result.successful)
        result.failed.extend(remaining_result.failed)
        result.total = len(urls)
    elif result.success_count == 0:
        # All probes failed — skip remaining to save time
        logger.warning(
            "gov_detail_stealth_probe_all_failed",
            extra={
                "probed": len(probe_urls),
                "skipped": max(0, len(urls) - 2),
                "reason": "detail page CAPTCHA block, falling back to list-page data",
            },
        )
        for record in records:
            record.metadata["detail_fetch_mode"] = "degraded_blocked"
        # Still mark the remaining as failed for logging
        for url in urls[2:]:
            result.failed.append((url, "skipped_after_probe_failure"))
    
    # Parse successful results
    url_to_record = {r.url: r for r in records if r.url}
    
    for url, html in result.successful:
        record = url_to_record.get(url)
        if not record:
            continue
        
        try:
            soup = parse_html(html)
            _extract_detail_fields(soup, record)
        except Exception as exc:
            logger.warning("gov_detail_parse_failed", extra={"url": url, "error": str(exc)})
    
    # Log failures
    for url, reason in result.failed:
        logger.warning("gov_detail_fetch_failed", extra={"url": url, "reason": reason})
    
    logger.info(
        "gov_detail_enriched_stealth",
        extra={
            "total": len(urls),
            "successful": result.success_count,
            "failed": result.failure_count,
            "success_rate": f"{result.success_rate * 100:.1f}%",
        }
    )


def enrich_detail_requests(records: list[BidRecord], settings: Settings, logger: Any) -> None:
    """Traditional requests-based detail enrichment (legacy fallback).
    
    Aborts early if first 2 consecutive requests hit CAPTCHA (gov.pcc blocks entire /tps/ path).
    """
    session = build_session(settings)
    delay = settings.gov_detail_delay_seconds
    captcha_count = 0
    consecutive_captcha = 0

    for idx, record in enumerate(records):
        if not record.url:
            continue

        # Early abort: if first 2 consecutive requests all hit CAPTCHA, stop wasting time
        if consecutive_captcha >= 2:
            logger.warning(
                "gov_detail_captcha_abort",
                extra={"reason": "consecutive CAPTCHA detected, aborting detail enrichment",
                       "consecutive": consecutive_captcha, "remaining": len(records) - idx},
            )
            break

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
                consecutive_captcha += 1
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
            consecutive_captcha = 0  # Reset on success
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
    for td in soup.find_all(["td", "th"]):
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

        # --- 押標金（寬鬆匹配，並排除其他保證金類型） ---
        elif "押標金" in text and "履約" not in text and "保固" not in text:
            nxt = td.find_next_sibling("td")
            is_label_cell = text == "是否須繳納押標金"
            if is_label_cell and nxt:
                val = nxt.get_text(" ", strip=True).replace("\u3000", " ")
            else:
                val = text.replace("\u3000", " ")
            if val:
                record.metadata["bid_bond_raw"] = val[:100]

                parsed_bond = _parse_bid_bond_value(val)
                if not record.bid_bond or record.bid_bond in ("需繳納", "未公開"):
                    record.bid_bond = parsed_bond

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

    from datetime import datetime
    output: list[BidRecord] = []
    today = datetime.today().date()
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

        # 判斷是否已結標：bid_date 存在且早於今天，或 date_text 有明顯結標字樣
        is_closed = False
        if bid_date and bid_date < today:
            is_closed = True
        if date_text and any(x in date_text for x in ["已結標", "已截止", "決標", "流標", "廢標"]):
            is_closed = True
        if is_closed:
            continue

        record = BidRecord(
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
                "detail_fetch_mode": "full",
            },
        )

        # 列表頁的截止投標日期作為 bid_deadline 的 fallback
        if date_text:
            record.bid_deadline = date_text

        output.append(record)
    
    return output


def _rate_limited_hits(exc: Exception) -> int:
    import re

    text = str(exc).lower()
    if "rate_limited" not in text and "captcha" not in text:
        return 0
    match = re.search(r"rate_limited['\"]?\s*:\s*(\d+)", text)
    if match:
        return max(1, int(match.group(1)))
    return 1
