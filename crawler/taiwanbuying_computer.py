from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

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
    request_html,
)

SOURCE_NAME = "taiwanbuying_today_computer"
COMPUTER_CATEGORY_URL = "https://www.taiwanbuying.com.tw/Query_TypeAction.ASP?Category=102"
COMPUTER_CATEGORY_NAME = "採購-電腦類"
UPDATE_DATE_PATTERN = re.compile(
    r"\(?\s*(?P<date>\d{4}\s*[/-]\s*\d{1,2}\s*[/-]\s*\d{1,2})\s*(?:更新)?\s*\)?"
)


def fetch_bids(settings: Settings, logger: Any) -> list[BidRecord]:
    today = datetime.now(ZoneInfo(settings.timezone)).date()

    session = build_session(settings)
    records: list[BidRecord] = []
    try:
        html = request_html(
            session=session,
            url=COMPUTER_CATEGORY_URL,
            method="GET",
            timeout_seconds=settings.request_timeout_seconds,
            logger=logger,
            settings=settings,
        )
        records = _parse_records(html, settings, today=today)
    except Exception as exc:
        logger.warning("taiwanbuying_computer_requests_failed_try_playwright", extra={"error": str(exc)})

    if not records and settings.enable_playwright:
        try:
            html = optional_playwright_fetch_html(
                COMPUTER_CATEGORY_URL,
                settings,
                wait_selector="body",
                logger=logger,
            )
            records = _parse_records(html, settings, today=today)
        except Exception as exc:
            logger.exception("taiwanbuying_computer_playwright_failed", extra={"error": str(exc)})

    logger.info(
        "source_parsed",
        extra={
            "source": SOURCE_NAME,
            "count": len(records),
            "today_update_count": len(records),
            "category": COMPUTER_CATEGORY_NAME,
        },
    )
    return records


def _parse_records(html: str, settings: Settings, today: date) -> list[BidRecord]:
    soup = parse_html(html)
    rows = _find_rows(soup)

    output: list[BidRecord] = []
    for row in rows:
        row_text = row.get_text(" ", strip=True)
        update_date, raw_update_text = _extract_update_date(row_text)
        if update_date != today:
            continue

        title = pick_first_text(row, settings.taiwanbuying_title_selectors)
        link = pick_first_attr(row, settings.taiwanbuying_link_selectors, "href")
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td, th")]

        if not title:
            title = _title_from_cells(cells, row_text, raw_update_text)
        title = title[:300].strip()
        if not title:
            continue

        org = pick_first_text(row, settings.taiwanbuying_org_selectors)
        if not org:
            org = _org_from_cells(cells, title)

        amount_text = pick_first_text(row, settings.taiwanbuying_amount_selectors)
        if not amount_text:
            amount_text = _extract_amount_text(row_text)

        summary = pick_first_text(row, settings.taiwanbuying_summary_selectors)
        if not summary:
            summary = _clean_summary(row_text, title, org)

        url = normalize_url(COMPUTER_CATEGORY_URL, link)
        taiwanbuying_id = _extract_taiwanbuying_id(url)

        output.append(
            BidRecord(
                title=title,
                organization=org,
                bid_date=update_date,
                amount_raw=amount_text,
                amount_value=parse_amount(amount_text),
                source=SOURCE_NAME,
                url=url,
                summary=summary,
                category=COMPUTER_CATEGORY_NAME,
                metadata={
                    "recall_source": SOURCE_NAME,
                    "update_date": update_date.isoformat(),
                    "raw_update_text": raw_update_text,
                    "category": COMPUTER_CATEGORY_NAME,
                    "taiwanbuying_category": "102",
                    "taiwanbuying_url": url,
                    "taiwanbuying_id": taiwanbuying_id,
                },
                announcement_date=update_date,
            )
        )
    return output


def _find_rows(soup: Any) -> list[Tag]:
    for selector in ["table tbody tr", "table tr", ".result-item", ".list-group-item"]:
        rows = [row for row in soup.select(selector) if row.get_text(strip=True)]
        if rows:
            return rows
    return [anchor for anchor in soup.select("a") if anchor.get_text(strip=True)]


def _extract_update_date(text: str) -> tuple[date | None, str]:
    for match in UPDATE_DATE_PATTERN.finditer(text):
        raw = match.group(0).strip()
        parsed = _parse_update_date(match.group("date"))
        if parsed:
            return parsed, raw
    return None, ""


def _parse_update_date(value: str) -> date | None:
    match = re.search(r"(\d{4})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{1,2})", value)
    if not match:
        return parse_bid_date(value)
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _title_from_cells(cells: list[str], row_text: str, raw_update_text: str) -> str:
    for cell in cells:
        cleaned = cell.replace(raw_update_text, "").strip()
        if cleaned and not _looks_like_date_or_amount(cleaned):
            return cleaned
    return row_text.replace(raw_update_text, "").strip()


def _org_from_cells(cells: list[str], title: str) -> str:
    for cell in cells:
        if cell == title:
            continue
        if any(keyword in cell for keyword in ["大學", "學校", "國小", "國中", "高中", "高職", "教育"]):
            return cell
    return ""


def _extract_amount_text(text: str) -> str:
    match = re.search(r"(?:NT\$|新臺幣|新台幣)\s*[\d,]+|[\d,]+\s*(?:元|萬|億)", text)
    return match.group(0).strip() if match else ""


def _clean_summary(text: str, title: str, org: str) -> str:
    summary = text.replace(title, " ").replace(org, " ")
    summary = re.sub(r"\s+", " ", summary).strip()
    return summary[:500]


def _looks_like_date_or_amount(text: str) -> bool:
    return bool(parse_bid_date(text) or parse_amount(text))


def _extract_taiwanbuying_id(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for name in ["TBN", "tbn", "RecNo", "recno", "JobNo", "jobno", "PK", "pk"]:
        values = query.get(name)
        if values and values[0].strip():
            return values[0].strip()

    filename = parsed.path.rsplit("/", 1)[-1]
    match = re.search(r"([A-Za-z]{0,4}\d{5,}[A-Za-z0-9_-]*)", filename)
    return match.group(1) if match else ""
