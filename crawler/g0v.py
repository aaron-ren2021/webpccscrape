from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from core.config import Settings
from core.models import BidRecord
from core.normalize import parse_amount, parse_bid_date

from crawler.common import build_session

SOURCE_NAME = "g0v"

# g0v API base URL (new version)
G0V_API_BASE = "https://pcc-api.openfun.app/api"
G0V_WEB_BASE = "https://pcc-api.openfun.app"


def _parse_bid_bond_text(value: str, *, preserve_plain_value: bool = False) -> str:
    """Extract bid bond amount/ratio from PCC text, excluding payment fee text."""
    text = value.replace("\u3000", " ").strip()
    if not text:
        return ""
    if _is_no_value(text):
        return "免繳"

    amount_text = text
    label_match = re.search(r"押標金額度[：:\s]*", amount_text)
    if label_match:
        amount_text = amount_text[label_match.end():]
    amount_text = re.split(r"(?:廠商線上繳納押標金)?手續費[：:：\s]*", amount_text, maxsplit=1)[0].strip()

    pct_match = re.search(r"百分之\s*([\d,.]+)", amount_text) or re.search(r"([\d,.]+)\s*[%％]", amount_text)
    if pct_match:
        return f"{pct_match.group(1).strip()}%"

    if re.search(r"[萬億]|千元", amount_text):
        normalized_amount = parse_amount(amount_text)
        if normalized_amount is not None:
            return f"{int(normalized_amount):,}"

    amount_patterns = [
        r"(?:新臺?幣|NT\$?)\s*([\d,]+)\s*元?",
        r"([\d,]+)\s*元(?:整)?",
    ]
    for pat in amount_patterns:
        amt_match = re.search(pat, amount_text)
        if amt_match:
            return amt_match.group(1)

    if preserve_plain_value and amount_text and "手續費" not in text:
        return amount_text
    if text.startswith("是"):
        return "需繳納"
    return ""


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
            records = _parse_records(records_data, logger, settings=settings)
            
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


def _parse_records(
    records_data: list[dict[str, Any]],
    logger: Any,
    settings: Settings | None = None,
) -> list[BidRecord]:
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
            tender_type = _text_or_empty(brief.get("type"))
            if "公開招標" not in tender_type:
                continue
            
            title = _text_or_empty(brief.get("title"))
            if not title:
                continue
            
            organization = _text_or_empty(item.get("unit_name"))
            
            # Parse announcement date (integer format YYYYMMDD)
            date_int = item.get("date")
            date_str = str(date_int) if date_int else ""
            announcement_date = parse_bid_date(date_str)
            
            # Extract category from brief
            category = _text_or_empty(brief.get("category"))
            
            # Use tender_api_url for enrichment (machine), and openfun index URL for humans (email link).
            raw_url = _text_or_empty(item.get("url"))

            tender_api_url = _text_or_empty(item.get("tender_api_url"))
            if tender_api_url.startswith("/"):
                tender_api_url = f"{G0V_WEB_BASE}{tender_api_url}"

            # Backward compatibility: older payloads may only provide a relative API path in `url`.
            if not tender_api_url and raw_url.startswith("/api/"):
                tender_api_url = f"{G0V_WEB_BASE}{raw_url}"

            unit_api_url = _text_or_empty(item.get("unit_api_url"))
            if unit_api_url.startswith("/"):
                unit_api_url = f"{G0V_WEB_BASE}{unit_api_url}"

            human_url_mode = _text_or_empty(getattr(settings, "g0v_human_link_mode", "safe_only")).lower() or "safe_only"
            human_url, link_resolution_state = _resolve_initial_human_url(
                raw_url=raw_url,
                tender_api_url=tender_api_url,
                human_url_mode=human_url_mode,
            )
            
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
                        "g0v_unit_api_url": unit_api_url,
                        "tender_api_url": tender_api_url,
                        "g0v_raw_url": raw_url,
                        "g0v_human_url": human_url,
                        # Keep legacy key for backward compatibility with formatter/tests.
                        "g0v_human_url_state": link_resolution_state,
                        "g0v_link_resolution_state": link_resolution_state,
                    },
                )
            )
        
        except Exception as exc:
            raw_url = _text_or_empty(item.get("url"))
            err_text = str(exc)
            error_code = "parse_error"
            if "NoneType" in err_text and "strip" in err_text:
                error_code = "field_null"
            elif raw_url and not raw_url.startswith("/index/case/") and not raw_url.startswith("/api/"):
                error_code = "url_invalid"
            logger.warning("g0v_parse_item_failed", extra={
                "error": str(exc), 
                "job_number": item.get("job_number", "unknown"),
                "error_code": error_code,
                "url": raw_url,
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
        _apply_human_url_resolution(
            record,
            resolved_url="",
            state="unresolved",
        )
        return False

    if record.metadata.get("g0v_tender_api_url") != tender_api_url:
        record.metadata["g0v_tender_api_url"] = tender_api_url

    client = session or build_session(settings)
    timeout_seconds = max(3.0, min(float(settings.request_timeout_seconds), 8.0))

    try:
        response = client.get(tender_api_url, timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        detail = _extract_detail_payload(payload)

        _extract_detail_fields(detail, record, logger)
        _resolve_human_url_from_detail(
            record=record,
            detail=detail,
            tender_api_url=tender_api_url,
            human_url_mode=_text_or_empty(getattr(settings, "g0v_human_link_mode", "safe_only")).lower() or "safe_only",
        )

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
        # Keep link clickable even when detail enrichment fails.
        _apply_human_url_resolution(
            record,
            resolved_url=tender_api_url,
            state="fallback_api",
        )
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
    
    # Try to extract budget amount. The g0v tender API mirrors PCC detail labels
    # as colon-delimited keys, e.g. "採購資料:預算金額".
    budget = _pick_text(detail, ["採購資料:預算金額", "預算金額", "budget_amount", "budget"])
    if budget:
        record.budget_amount = budget
        amount_value = parse_amount(budget)
        if amount_value is not None:
            record.amount_raw = budget
            record.amount_value = amount_value
        elif logger:
            logger.warning(
                "g0v_detail_budget_parse_failed",
                extra={
                    "title": record.title[:80],
                    "url": record.url,
                    "budget": budget[:120],
                    "existing_amount_value": record.amount_value,
                },
            )
    elif (
        detail.get("budget_public") is False
        or _is_no_value(_pick_text(detail, ["採購資料:預算金額是否公開", "預算金額是否公開"]))
    ) and not record.budget_amount:
        record.budget_amount = "未公開"
    elif not record.budget_amount:
        record.budget_amount = "無提供"
    
    # Extract bid bond (押標金). Some PCC/g0v payloads include online payment fee
    # near the bid-bond fields; never use that fee as the bond amount.
    bond = _parse_bid_bond_text(
        _pick_text(
            detail,
            [
                "領投開標:是否須繳納押標金:押標金額度",
                "押標金額度",
                "押標金額",
                "bid_bond",
                "bidBond",
            ],
        ),
        preserve_plain_value=True,
    )
    bond_status = _pick_text(
        detail,
        [
            "領投開標:是否須繳納押標金",
            "是否須繳納押標金",
        ],
    )
    if not bond or bond == "需繳納":
        bond = _parse_bid_bond_text(bond_status)
    if bond:
        record.bid_bond = bond
    elif _is_no_value(bond_status):
        record.bid_bond = "免繳"
    elif not record.bid_bond:
        record.bid_bond = "無提供"
    
    # Extract bid deadline
    deadline = _pick_text(detail, ["領投開標:截止投標", "截止投標", "bid_deadline", "deadline"])
    if deadline:
        record.bid_deadline = deadline
    elif not record.bid_deadline:
        record.bid_deadline = "無提供"
    
    # Extract opening time
    opening = _pick_text(detail, ["領投開標:開標時間", "開標時間", "bid_opening_time", "opening_time"])
    if opening:
        record.bid_opening_time = opening
    elif not record.bid_opening_time:
        record.bid_opening_time = "無提供"
    
    # Extract contact info (if available)
    contact = _pick_text(detail, ["機關資料:聯絡人", "聯絡資訊", "contact_info", "contact"])
    if contact:
        phone = _pick_text(detail, ["機關資料:聯絡電話", "聯絡電話", "phone"])
        record.metadata["contact_info"] = f"{contact} {phone}".strip()

    award_method = _pick_text(detail, ["招標資料:決標方式", "決標方式", "award_method", "awardMethod"])
    if award_method:
        record.metadata["award_method"] = award_method

    if not record.organization:
        organization = _pick_text(detail, ["機關資料:機關名稱", "機關資料:單位名稱", "unit_name"])
        if organization:
            record.organization = organization


def _extract_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize API response to the detail object used by field extraction."""
    if not isinstance(payload, dict):
        return {}

    records = payload.get("records")
    if isinstance(records, list) and records:
        first = records[0]
        if isinstance(first, dict):
            detail = first.get("detail")
            if isinstance(detail, dict):
                return detail
            return first
    return payload


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


def _is_no_value(value: str) -> bool:
    text = value.strip().lower() if value else ""
    return text.startswith("否") or text in {"no", "false", "0"}


def _text_or_empty(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _resolve_initial_human_url(
    raw_url: str,
    tender_api_url: str,
    human_url_mode: str,
) -> tuple[str, str]:
    """Resolve initial human URL from list API payload.

    `/index/case/...` is currently unreliable and can return a 404 error page with HTTP 200.
    So we do not trust it as a clickable primary link. We resolve to official link later
    via tender detail API, and keep API URL as fallback.
    """
    if tender_api_url:
        return tender_api_url, "fallback_api"

    if human_url_mode != "safe_only" and raw_url.startswith("/api/"):
        return f"{G0V_WEB_BASE}{raw_url}", "fallback_api"

    return "", "unresolved"


def _resolve_human_url_from_detail(
    *,
    record: BidRecord,
    detail: dict[str, Any],
    tender_api_url: str,
    human_url_mode: str,
) -> None:
    official_url = _text_or_empty(detail.get("url"))
    if official_url.startswith("/"):
        official_url = f"{G0V_WEB_BASE}{official_url}"

    if official_url.startswith("http://") or official_url.startswith("https://"):
        if "web.pcc.gov.tw" in official_url:
            _apply_human_url_resolution(record, resolved_url=official_url, state="resolved_official")
            return

    if tender_api_url:
        _apply_human_url_resolution(record, resolved_url=tender_api_url, state="fallback_api")
        return

    if human_url_mode != "safe_only":
        raw_url = _text_or_empty(record.metadata.get("g0v_raw_url", ""))
        if raw_url.startswith("/api/"):
            _apply_human_url_resolution(
                record,
                resolved_url=f"{G0V_WEB_BASE}{raw_url}",
                state="fallback_api",
            )
            return

    _apply_human_url_resolution(record, resolved_url="", state="unresolved")


def _apply_human_url_resolution(record: BidRecord, resolved_url: str, state: str) -> None:
    record.url = resolved_url
    record.metadata["g0v_human_url"] = resolved_url
    # Keep legacy key for compatibility.
    record.metadata["g0v_human_url_state"] = state
    record.metadata["g0v_link_resolution_state"] = state
