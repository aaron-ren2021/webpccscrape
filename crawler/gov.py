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

    normalized_amount = parse_amount(amount_text)
    if normalized_amount is not None:
        return f"NT$ {int(normalized_amount):,} 元"

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
    """Fetch gov.pcc bids through the configured backend.

    Hybrid mode is deliberately fail-open to the legacy implementation so the
    worst case remains the previous Playwright/requests behavior.
    """
    backend = str(getattr(settings, "crawler_backend", "hybrid") or "hybrid").strip().lower()
    if backend not in {"hybrid", "scrapling", "playwright_legacy"}:
        logger.warning("gov_unknown_backend_fallback_legacy", extra={"backend": backend})
        backend = "playwright_legacy"

    if backend == "playwright_legacy" or not getattr(settings, "enable_firsthand_gov", True):
        return fetch_bids_legacy(settings, logger)

    fallback_error = ""
    try:
        from crawler.scrapling_gov import fetch_bids_scrapling

        records = fetch_bids_scrapling(settings, logger)
        if records:
            logger.info("source_parsed", extra={"source": SOURCE_NAME, "count": len(records), "method": "scrapling"})
            return records
        logger.warning("gov_scrapling_empty_fallback_legacy", extra={"backend": backend})
    except Exception as exc:
        fallback_error = str(exc)
        logger.warning(
            "gov_scrapling_failed_fallback_legacy",
            extra={"backend": backend, "error": str(exc)},
        )

    if backend == "scrapling":
        raise RuntimeError(f"Scrapling gov backend failed: {fallback_error or 'no records parsed'}")
    return fetch_bids_legacy(settings, logger)


def fetch_bids_legacy(settings: Settings, logger: Any) -> list[BidRecord]:
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
            _extract_detail_fields(soup, record, logger)
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
            _extract_detail_fields(soup, record, logger)
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


def _extract_detail_fields(soup: Any, record: BidRecord, logger: Any | None = None) -> None:
    """Extract stable detail fields from gov.pcc detail HTML without erasing list data."""
    values = _extract_labeled_values(soup)
    logged_missing_fields: set[str] = set()

    budget = _pick_labeled_value(values, ["預算金額"], exclude_labels=["預算金額是否公開"])
    if budget:
        amount_value = parse_amount(budget)
        if amount_value is not None:
            if float(amount_value).is_integer():
                amount_number = f"{int(amount_value):,}"
            else:
                amount_number = f"{amount_value:,.2f}"
            formatted = f"NT$ {amount_number} 元"
            record.budget_amount = formatted
            record.amount_raw = formatted
            record.amount_value = amount_value
        else:
            _log_detail_extract_miss(logger, record, "預算金額", "parse_amount_failed", budget)
            logged_missing_fields.add("預算金額")

    budget_public = _pick_labeled_value(values, ["預算金額是否公開"])
    if budget_public:
        if budget_public.startswith("否") and record.amount_value is None and not record.budget_amount:
            record.budget_amount = "未公開"
        elif (
            budget_public.startswith("是")
            and not record.budget_amount
            and record.amount_value is None
            and not str(record.amount_raw or "").strip()
        ):
            record.budget_amount = "已公開（金額見詳細頁）"

    bond = _pick_labeled_value(
        values,
        ["是否須繳納押標金", "押標金額度", "押標金"],
        exclude_labels=["履約", "保固", "手續費"],
    )
    if bond:
        record.metadata["bid_bond_raw"] = bond[:100]
        parsed_bond = _parse_bid_bond_value(bond)
        if not record.bid_bond or record.bid_bond in ("需繳納", "未公開", "無提供"):
            record.bid_bond = parsed_bond

    deadline = _pick_labeled_value(values, ["截止投標"])
    if deadline:
        record.bid_deadline = deadline

    opening = _pick_labeled_value(values, ["開標時間"])
    if opening:
        record.bid_opening_time = opening

    organization = _pick_labeled_value(values, ["機關名稱", "招標機關", "洽辦機關"])
    if organization and not record.organization:
        record.organization = organization

    contact = _pick_labeled_value(values, ["聯絡人", "聯絡資訊", "承辦人"])
    phone = _pick_labeled_value(values, ["聯絡電話", "電話"])
    if contact:
        record.metadata["contact_info"] = f"{contact} {phone}".strip()

    award_method = _pick_labeled_value(values, ["決標方式"])
    if award_method:
        record.metadata["award_method"] = award_method

    if logger:
        for field, current in [
            ("預算金額", record.budget_amount),
            ("押標金", record.bid_bond),
            ("截止投標", record.bid_deadline),
            ("開標時間", record.bid_opening_time),
        ]:
            if field in logged_missing_fields:
                continue
            if not str(current or "").strip():
                _log_detail_extract_miss(logger, record, field, "label_not_found_or_empty", _html_snippet(soup))


def _extract_labeled_values(soup: Any) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}

    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        for idx, cell in enumerate(cells[:-1]):
            label = _clean_detail_text(cell.get_text(" ", strip=True))
            value = _clean_detail_text(cells[idx + 1].get_text(" ", strip=True))
            if label and value:
                _add_labeled_value(values, label, value)

    for node in soup.find_all(["td", "th", "label", "legend"]):
        text = _clean_detail_text(node.get_text(" ", strip=True))
        if not text:
            continue
        match = re.match(r"^([^：:]{2,24})[：:]\s*(.+)$", text)
        if match:
            _add_labeled_value(values, match.group(1), match.group(2))

    return values


def _pick_labeled_value(
    values: dict[str, list[str]],
    labels: list[str],
    *,
    exclude_labels: list[str] | None = None,
) -> str:
    excludes = exclude_labels or []
    for raw_label, candidates in values.items():
        label = _normalize_detail_label(raw_label)
        if any(_normalize_detail_label(exclude) in label for exclude in excludes):
            continue
        if not any(_normalize_detail_label(expected) in label for expected in labels):
            continue
        for value in candidates:
            cleaned = _strip_repeated_label(value, labels)
            if cleaned:
                return cleaned
    return ""


def _add_labeled_value(values: dict[str, list[str]], label: str, value: str) -> None:
    clean_label = _clean_detail_text(label)
    clean_value = _clean_detail_text(value)
    if clean_label and clean_value and clean_label != clean_value:
        values.setdefault(clean_label, []).append(clean_value)


def _strip_repeated_label(value: str, labels: list[str]) -> str:
    cleaned = _clean_detail_text(value)
    for label in labels:
        cleaned = re.sub(rf"^{re.escape(label)}[：:\s]*", "", cleaned).strip()
    return cleaned


def _clean_detail_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u3000", " ")).strip(" ：:")


def _normalize_detail_label(value: str) -> str:
    return re.sub(r"[\s：:]", "", _clean_detail_text(value))


def _html_snippet(soup: Any, limit: int = 240) -> str:
    text = _clean_detail_text(soup.get_text(" ", strip=True) if hasattr(soup, "get_text") else str(soup))
    return text[:limit]


def _log_detail_extract_miss(
    logger: Any | None,
    record: BidRecord,
    field: str,
    reason: str,
    snippet: str,
) -> None:
    if not logger:
        return
    logger.warning(
        "gov_detail_field_missing",
        extra={
            "field": field,
            "reason": reason,
            "title": record.title[:80],
            "url": record.url,
            "snippet": snippet[:240],
        },
    )


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
