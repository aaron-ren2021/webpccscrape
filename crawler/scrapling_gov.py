from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from core.config import Settings
from core.models import BidRecord
from core.normalize import parse_amount, parse_bid_date
from crawler.common import normalize_url

SOURCE_NAME = "gov_pcc"

try:  # Keep module importable before scrapling is installed.
    from scrapling.fetchers import AsyncStealthySession
    from scrapling.spiders import Request, Response, Spider
except Exception:  # pragma: no cover - exercised in environments without scrapling.
    AsyncStealthySession = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    Response = Any  # type: ignore[misc, assignment]
    Spider = object  # type: ignore[assignment]


class PccGovSpider(Spider):  # type: ignore[misc]
    name = "pcc_gov"
    start_urls: list[str] = []
    allowed_domains = ["web.pcc.gov.tw"]
    concurrent_requests = 4

    def __init__(self, settings: Settings, logger: Any) -> None:
        self.settings = settings
        self.logger = logger
        self._start_url = settings.gov_url
        self._concurrent_requests = max(1, getattr(settings, "scrapling_concurrent_requests", 4))
        super().__init__()
        self.start_urls = [self._start_url]
        self.concurrent_requests = self._concurrent_requests

    def configure_sessions(self, manager: Any) -> None:
        if AsyncStealthySession is None:
            return
        manager.add(
            "stealth",
            AsyncStealthySession(
                headless=getattr(self.settings, "stealth_headless", True),
                max_pages=max(1, getattr(self.settings, "scrapling_concurrent_requests", 4)),
            ),
            lazy=True,
        )

    async def parse(self, response: Response) -> Any:
        html = _response_html(response)
        items = _parse_list_items(html, str(getattr(response, "url", self.settings.gov_url)), self.settings)
        for item in items:
            yield item
            detail_url = str(item.get("url", ""))
            if detail_url and _should_fetch_detail(item, self.settings):
                yield Request(detail_url, sid="stealth", callback=self.parse_detail, meta={"item": item})

        for next_url in _pagination_links(html, str(getattr(response, "url", self.settings.gov_url))):
            yield response.follow(next_url, sid="stealth", callback=self.parse)

    async def parse_detail(self, response: Response) -> Any:
        item = dict(getattr(response, "meta", {}).get("item", {}) or {})
        if not item:
            return
        html = _response_html(response)
        soup = BeautifulSoup(html, "html.parser")
        record = _item_to_record(item)
        try:
            from crawler.gov import _extract_detail_fields

            _extract_detail_fields(soup, record, self.logger)
            item.update(_record_detail_fields(record))
            item["detail_enriched"] = True
        except Exception as exc:
            self.logger.warning("gov_scrapling_detail_parse_failed", extra={"url": item.get("url", ""), "error": str(exc)})
        yield item


def fetch_bids_scrapling(settings: Settings, logger: Any) -> list[BidRecord]:
    if Spider is object or Request is None or AsyncStealthySession is None:
        raise RuntimeError("Scrapling fetchers are not installed. Run: pip install -r requirements.txt && scrapling install")

    spider = PccGovSpider(settings, logger)
    result = spider.start()
    items = _result_items(result)
    records = [_item_to_record(item) for item in _merge_items(items)]
    logger.info("gov_scrapling_result", extra={"items": len(items), "records": len(records)})
    return records


def _response_html(response: Any) -> str:
    for attr in ("text", "html", "content", "body"):
        value = getattr(response, attr, None)
        if callable(value):
            value = value()
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        if isinstance(value, str) and value.strip():
            return value
    return str(response)


def _result_items(result: Any) -> list[dict[str, Any]]:
    raw_items = getattr(result, "items", result)
    if hasattr(raw_items, "to_list"):
        raw_items = raw_items.to_list()
    elif hasattr(raw_items, "data"):
        raw_items = raw_items.data
    return [dict(item) for item in list(raw_items or []) if isinstance(item, dict)]


def _merge_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in sorted(items, key=lambda value: bool(value.get("detail_enriched"))):
        key = _item_key(item)
        current = merged.get(key, {})
        current.update({k: v for k, v in item.items() if v not in (None, "")})
        merged[key] = current
    return list(merged.values())


def _item_key(item: dict[str, Any]) -> str:
    pk = str(item.get("pk_pms_main", "")).strip()
    if pk:
        return f"pk:{pk}"
    url = str(item.get("url", "")).strip()
    if url:
        return f"url:{url}"
    return f"title:{item.get('organization', '')}:{item.get('title', '')}:{item.get('raw_date', '')}"


def _parse_list_items(html: str, base_url: str, settings: Settings) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = _candidate_rows(soup, settings)
    today = datetime.today().date()
    output: list[dict[str, Any]] = []

    for row in rows:
        item = _parse_row(row, base_url, settings)
        title = str(item.get("title", "")).strip()
        if not title or not _looks_like_tender_item(item):
            continue
        bid_date = parse_bid_date(str(item.get("raw_date", "")))
        if bid_date and bid_date < today:
            continue
        if any(marker in str(item.get("raw_date", "")) for marker in ["已結標", "已截止", "決標", "流標", "廢標"]):
            continue
        item["bid_date"] = bid_date
        output.append(item)
    return output


def _candidate_rows(soup: BeautifulSoup, settings: Settings) -> list[Tag]:
    selectors = [
        "table[id='row'] tr",
        "table.tb_01 tr",
        "table tr",
        *settings.gov_row_selectors,
    ]
    for selector in selectors:
        rows = [row for row in soup.select(selector) if row.find("a") and row.get_text(strip=True)]
        if rows:
            return rows
    return [anchor for anchor in soup.select("a") if anchor.get_text(strip=True)]


def _parse_row(row: Tag, base_url: str, settings: Settings) -> dict[str, Any]:
    cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"], recursive=False)]
    link_node = _best_link(row)
    link = str(link_node.get("href", "")) if link_node else ""
    title = _clean_text(link_node.get_text(" ", strip=True) if link_node else "")
    if not title:
        title = _pick_by_selectors(row, settings.gov_title_selectors) or _clean_text(row.get_text(" ", strip=True))

    org = _pick_by_selectors(row, settings.gov_org_selectors) or _cell_near_label(cells, ["機關", "招標機關"])
    date_text = _pick_by_selectors(row, settings.gov_date_selectors) or _first_date_text(cells)
    amount_text = _pick_by_selectors(row, settings.gov_amount_selectors) or _first_amount_text(cells)
    summary = _pick_by_selectors(row, settings.gov_summary_selectors)
    url = normalize_url(base_url, link)

    return {
        "title": title[:300],
        "organization": org,
        "raw_date": date_text,
        "amount_raw": amount_text,
        "amount_value": parse_amount(amount_text),
        "source": SOURCE_NAME,
        "url": url,
        "summary": summary,
        "pk_pms_main": _pk_pms_main(url),
        "detail_fetch_mode": "full",
    }


def _best_link(row: Tag) -> Tag | None:
    links = row.find_all("a", href=True)
    for link in links:
        href = str(link.get("href", ""))
        if "readTenderBasic" in href or "pkPmsMain" in href:
            return link
    return links[0] if links else None


def _looks_like_tender_item(item: dict[str, Any]) -> bool:
    url = str(item.get("url", ""))
    has_detail_link = bool(item.get("pk_pms_main")) or "searchTenderDetail" in url or "readTenderBasic" in url
    has_bid_date = parse_bid_date(str(item.get("raw_date", ""))) is not None
    return has_detail_link or has_bid_date


def _pick_by_selectors(row: Tag, selectors: list[str]) -> str:
    for selector in selectors:
        hit = row.select_one(selector)
        if hit and hit.get_text(strip=True):
            return _clean_text(hit.get_text(" ", strip=True))
    return ""


def _cell_near_label(cells: list[str], labels: list[str]) -> str:
    for idx, cell in enumerate(cells[:-1]):
        if any(label in cell for label in labels):
            return cells[idx + 1]
    return ""


def _first_date_text(cells: list[str]) -> str:
    for cell in cells:
        if parse_bid_date(cell):
            return cell
    return ""


def _first_amount_text(cells: list[str]) -> str:
    for cell in cells:
        if parse_amount(cell) is not None:
            return cell
    return ""


def _pagination_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for link in soup.select("a[href]"):
        text = _clean_text(link.get_text(" ", strip=True))
        href = str(link.get("href", ""))
        if text in {"下一頁", "下頁", ">", "Next"} or "pageIndex" in href:
            links.append(normalize_url(base_url, href))
    return links[:3]


def _should_fetch_detail(item: dict[str, Any], settings: Settings) -> bool:
    text = " ".join(str(item.get(key, "")) for key in ("title", "organization", "summary"))
    keywords = ["學校", "教育", "大學", "國中", "國小", "高中", "AI", "AICG", "GPU", "伺服器", "資訊", "電腦"]
    if any(keyword.lower() in text.lower() for keyword in keywords):
        return True
    amount = item.get("amount_value")
    return isinstance(amount, (int, float)) and amount >= settings.high_amount_threshold


def _item_to_record(item: dict[str, Any]) -> BidRecord:
    bid_date = item.get("bid_date")
    if isinstance(bid_date, str):
        bid_date = parse_bid_date(bid_date)
    amount_raw = str(item.get("amount_raw", ""))
    amount_value = item.get("amount_value")
    if amount_value is None:
        amount_value = parse_amount(amount_raw)

    record = BidRecord(
        title=str(item.get("title", "")),
        organization=str(item.get("organization", "")),
        bid_date=bid_date,
        amount_raw=amount_raw,
        amount_value=amount_value,
        source=SOURCE_NAME,
        url=str(item.get("url", "")),
        summary=str(item.get("summary", "")),
        metadata={
            "raw_date": str(item.get("raw_date", "")),
            "detail_fetch_mode": str(item.get("detail_fetch_mode", "full")),
            "scrapling_detail_enriched": bool(item.get("detail_enriched", False)),
        },
    )
    if item.get("pk_pms_main"):
        record.metadata["pkPmsMain"] = str(item["pk_pms_main"])
    if item.get("budget_amount"):
        record.budget_amount = str(item["budget_amount"])
    if item.get("bid_bond"):
        record.bid_bond = str(item["bid_bond"])
    if item.get("bid_deadline"):
        record.bid_deadline = str(item["bid_deadline"])
    elif item.get("raw_date"):
        record.bid_deadline = str(item["raw_date"])
    if item.get("bid_opening_time"):
        record.bid_opening_time = str(item["bid_opening_time"])
    return record


def _record_detail_fields(record: BidRecord) -> dict[str, Any]:
    return {
        "amount_raw": record.amount_raw,
        "amount_value": record.amount_value,
        "budget_amount": record.budget_amount,
        "bid_bond": record.bid_bond,
        "bid_deadline": record.bid_deadline,
        "bid_opening_time": record.bid_opening_time,
    }


def _pk_pms_main(url: str) -> str:
    parsed = urlparse(url)
    values = parse_qs(parsed.query).get("pkPmsMain", [])
    return values[0] if values else ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u3000", " ")).strip()
