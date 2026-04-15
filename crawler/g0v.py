from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from core.config import Settings
from core.models import BidRecord
from core.normalize import parse_bid_date

from crawler.common import build_session

SOURCE_NAME = "g0v"

# g0v API base URL (new version)
G0V_API_BASE = "https://pcc-api.openfun.app/api"
G0V_WEB_BASE = "https://pcc-api.openfun.app"


def fetch_bids(settings: Settings, logger: Any) -> list[BidRecord]:
    """Fetch bids from g0v open data API (pcc-api.openfun.app).
    
    Uses new API format that returns paginated results in dict format:
    {"records": [...], "total_records": N, "total_pages": N}
    
    Data source: 行政院公共工程委員會「政府電子採購網」
    """
    if not settings.g0v_enabled:
        logger.info("g0v_disabled")
        return []

    session = build_session(settings)
    
    # Build date parameter: YYYYMMDD format
    now_tw = datetime.now(ZoneInfo(settings.timezone))
    
    # API may have 1-4 days delay, try multiple recent dates
    dates_to_try = []
    for days_back in range(5):  # Try today, yesterday, ...  up to 4 days ago
        date_tw = now_tw - timedelta(days=days_back)
        dates_to_try.append(date_tw.strftime("%Y%m%d"))
    
    # Try recent dates
    for date_try in dates_to_try:
        url = f"{G0V_API_BASE}/listbydate?date={date_try}&page=1"
        
        try:
            response = session.get(url, timeout=settings.request_timeout_seconds)
            response.raise_for_status()
            
            logger.info("http_request", extra={
                "url": url, 
                "status": response.status_code, 
                "method": "GET",
            })
            
            data = response.json()
            
            # New API format: dict with "records" array
            if not isinstance(data, dict):
                logger.warning("g0v_unexpected_response_type", extra={
                    "expected": "dict",
                    "got": type(data).__name__,
                    "date": date_try,
                })
                continue
            
            records_data = data.get("records", [])
            if not records_data:
                logger.info("g0v_no_records", extra={"date": date_try})
                continue
            
            total_records = data.get("total_records", len(records_data))
            total_pages = data.get("total_pages", 1)
            
            logger.info("g0v_api_response", extra={
                "date": date_try,
                "total_records": total_records,
                "total_pages": total_pages,
                "fetched_page": 1,
            })
            
            # Parse first page
            records = _parse_records(records_data, logger)
            
            if records:
                logger.info("source_parsed", extra={
                    "source": SOURCE_NAME, 
                    "count": len(records),
                    "date": date_try,
                })
                return records
            
        except Exception as exc:
            logger.warning("g0v_fetch_failed", extra={
                "error": str(exc), 
                "url": url,
                "date": date_try,
            })
            continue
    
    logger.warning("g0v_no_valid_data", extra={
        "tried_dates": dates_to_try
    })
    return []


def _parse_records(records_data: list[dict[str, Any]], logger: Any) -> list[BidRecord]:
    """Parse g0v JSON records into BidRecord objects.
    
    Record structure:
    {
      "date": 20260410,
      "job_number": "11514",
      "unit_id": "3.79.56.3",
      "unit_name": "臺北市建築管理工程處",
      "tender_api_url": "https://pcc-api.openfun.app/api/tender?...",
      "brief": {
        "type": "公開招標公告",
        "title": "115年度建築套繪圖數化暨地理資訊系統功能擴充案",
        "category": "財物類481-醫療,外科及矯形設備"
      }
    }
    """
    output: list[BidRecord] = []
    
    for item in records_data:
        try:
            brief = item.get("brief", {})
            if not isinstance(brief, dict):
                continue
            
            # Only process "公開招標公告" types (open bidding announcements)
            tender_type = brief.get("type", "")
            if "公開招標" not in tender_type:
                continue
            
            title = brief.get("title", "").strip()
            if not title:
                continue
            
            organization = (item.get("unit_name") or "").strip()
            
            # Parse announcement date (integer format YYYYMMDD)
            date_int = item.get("date")
            date_str = str(date_int) if date_int else ""
            announcement_date = parse_bid_date(date_str)
            
            # Extract category from brief
            category = brief.get("category", "")
            
            # Use tender_api_url for enrichment (machine), and openfun index URL for humans (email link).
            raw_url = str(item.get("url") or "").strip()

            tender_api_url = str(item.get("tender_api_url") or "").strip()
            if tender_api_url.startswith("/"):
                tender_api_url = f"{G0V_API_BASE}{tender_api_url}"

            # Backward compatibility: older payloads may only provide a relative API path in `url`.
            if not tender_api_url and raw_url.startswith("/api/"):
                tender_api_url = f"{G0V_WEB_BASE}{raw_url}"

            human_url = ""
            if raw_url.startswith("/index/"):
                human_url = f"{G0V_WEB_BASE}{raw_url}"
            elif tender_api_url:
                # Last resort: keep a clickable link even if it leads to JSON.
                human_url = tender_api_url
            
            # listbydate API doesn't include budget amount
            amount_text = ""
            amount_value = None
            
            output.append(
                BidRecord(
                    title=title[:300],
                    organization=organization,
                    # g0v list `date` is announcement date, not bid deadline.
                    bid_date=None,
                    amount_raw=amount_text,
                    amount_value=amount_value,
                    source=SOURCE_NAME,
                    url=human_url,
                    summary="",
                    category=category,
                    announcement_date=announcement_date,
                    metadata={
                        "raw_date": date_str,
                        "brief_type": tender_type,
                        "unit_id": item.get("unit_id", ""),
                        "job_number": item.get("job_number", ""),
                        "g0v_unit_id": item.get("unit_id", ""),
                        "g0v_job_number": item.get("job_number", ""),
                        "g0v_tender_api_url": tender_api_url,
                        "tender_api_url": tender_api_url,
                        "g0v_human_url": human_url,
                    },
                )
            )
        
        except Exception as exc:
            logger.warning("g0v_parse_item_failed", extra={
                "error": str(exc), 
                "job_number": item.get("job_number", "unknown"),
            })
            continue
    
    return output


def enrich_detail(records: list[BidRecord], settings: Settings, logger: Any) -> None:
    """Enrich g0v records from /api/tender endpoint (budget/bond/deadline).
    
    This is optional enhancement. If it fails, records still have basic info.
    """
    session = build_session(settings)

    for record in records:
        if record.source != SOURCE_NAME:
            continue
        enrich_record(record, settings, logger, session=session)


def enrich_record(
    record: BidRecord,
    settings: Settings,
    logger: Any,
    session: Any | None = None,
) -> bool:
    """Enrich a single record using g0v tender detail API.

    Returns True when budget_amount or bid_bond is successfully enriched.
    """
    tender_api_url, lookup_mode = _resolve_tender_api_url(record)
    if not tender_api_url:
        return False

    if record.metadata.get("g0v_tender_api_url") != tender_api_url:
        record.metadata["g0v_tender_api_url"] = tender_api_url

    client = session or build_session(settings)
    timeout_seconds = max(3.0, min(float(settings.request_timeout_seconds), 8.0))

    try:
        response = client.get(tender_api_url, timeout=timeout_seconds)
        response.raise_for_status()
        detail = response.json()

        _extract_detail_fields(detail, record, logger)

        enriched = _has_budget_or_bond(record)
        if enriched:
            current_source = str(record.metadata.get("enrichment_source", "")).strip()
            if current_source and current_source != "g0v_api":
                record.metadata["enrichment_source"] = f"{current_source}+g0v_api"
            else:
                record.metadata["enrichment_source"] = "g0v_api"
            record.metadata["enrichment_note"] = f"g0v_tender_lookup:{lookup_mode}"
        return enriched
    except Exception as exc:
        logger.warning(
            "g0v_detail_fetch_failed",
            extra={
                "url": tender_api_url,
                "error": str(exc),
                "job_number": record.metadata.get("g0v_job_number")
                or record.metadata.get("job_number", ""),
                "lookup_mode": lookup_mode,
            },
        )
    return False


def _extract_detail_fields(
    detail: dict[str, Any],
    record: BidRecord,
    logger: Any | None = None,
) -> None:
    """Extract budget, bond, deadline from tender detail API response."""
    if not isinstance(detail, dict):
        return
    
    # Try to extract budget amount
    budget = _pick_text(detail, ["預算金額", "budget_amount", "budget"])
    if budget:
        record.amount_raw = budget
        record.budget_amount = budget
    elif detail.get("budget_public") is False and not record.budget_amount:
        record.budget_amount = "未公開"
    elif not record.budget_amount:
        record.budget_amount = "無提供"
    
    # Extract bid bond (押標金)
    bond = _pick_text(detail, ["押標金額", "bid_bond", "bidBond"])
    if bond:
        record.bid_bond = bond
    elif not record.bid_bond:
        record.bid_bond = "無提供"
    
    # Extract bid deadline
    deadline = _pick_text(detail, ["截止投標", "bid_deadline", "deadline"])
    if deadline:
        record.bid_deadline = deadline
    elif not record.bid_deadline:
        record.bid_deadline = "無提供"
    
    # Extract opening time
    opening = _pick_text(detail, ["開標時間", "bid_opening_time", "opening_time"])
    if opening:
        record.bid_opening_time = opening
    elif not record.bid_opening_time:
        record.bid_opening_time = "無提供"
    
    # Extract contact info (if available)
    contact = _pick_text(detail, ["聯絡資訊", "contact_info", "contact"])
    if contact:
        record.metadata["contact_info"] = contact

    award_method = _pick_text(detail, ["決標方式", "award_method", "awardMethod"])
    if award_method:
        record.metadata["award_method"] = award_method


def _pick_text(data: dict[str, Any], keys: list[str]) -> str:
    """Pick first non-empty text value from dict by trying multiple keys."""
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def _resolve_tender_api_url(record: BidRecord) -> tuple[str, str]:
    metadata = record.metadata or {}

    metadata_url = str(metadata.get("g0v_tender_api_url") or "").strip()
    if metadata_url and "/api/tender" in metadata_url:
        return metadata_url, "metadata_g0v_tender_api_url"

    metadata_url = str(metadata.get("tender_api_url") or "").strip()
    if metadata_url and "/api/tender" in metadata_url:
        return metadata_url, "metadata_tender_api_url"

    if record.url and "/api/tender" in record.url:
        return record.url, "record_url"

    unit_id = str(metadata.get("g0v_unit_id") or metadata.get("unit_id") or "").strip()
    job_number = str(metadata.get("g0v_job_number") or metadata.get("job_number") or "").strip()
    if unit_id and job_number:
        return (
            f"{G0V_API_BASE}/tender?unit_id={quote(unit_id, safe='')}&job_number={quote(job_number, safe='')}",
            "unit_id_job_number",
        )
    return "", "missing_lookup_key"


def _has_budget_or_bond(record: BidRecord) -> bool:
    return (not _is_missing_value(record.budget_amount)) or (not _is_missing_value(record.bid_bond))


def _is_missing_value(value: str) -> bool:
    text = value.strip().lower() if value else ""
    return text in {"", "none", "null", "無", "無提供", "n/a"}
