from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from core.config import Settings
from core.models import BidRecord
from core.normalize import parse_amount, parse_bid_date

from crawler.common import build_session, normalize_url, random_delay

SOURCE_NAME = "g0v"


def fetch_bids(settings: Settings, logger: Any) -> list[BidRecord]:
    """Fetch bids from g0v open data API (JSON format, no HTML parsing needed)."""
    if not settings.g0v_enabled:
        logger.info("g0v_disabled")
        return []

    session = build_session(settings)
    
    # Build date parameter: YYYYMMDD format
    now_tw = datetime.now(ZoneInfo(settings.timezone))
    date_param = now_tw.strftime("%Y%m%d")
    
    url = f"{settings.g0v_api_url}?date={date_param}"
    
    try:
        response = session.get(url, timeout=settings.request_timeout_seconds)
        response.raise_for_status()
        
        logger.info("http_request", extra={"url": url, "status": response.status_code, "method": "GET"})
        
        data = response.json()
        
        # API may return {} when no data available
        if not isinstance(data, list):
            logger.info("g0v_no_data_today", extra={"response_type": type(data).__name__})
            return []
        
        records = _parse_records(data, logger)
        logger.info("source_parsed", extra={"source": SOURCE_NAME, "count": len(records)})
        return records
        
    except Exception as exc:
        logger.exception("g0v_fetch_failed", extra={"error": str(exc), "url": url})
        return []


def _parse_records(data: list[dict[str, Any]], logger: Any) -> list[BidRecord]:
    """Parse g0v JSON data into BidRecord objects."""
    output: list[BidRecord] = []
    
    for item in data:
        try:
            brief = item.get("brief", {})
            if not isinstance(brief, dict):
                continue
            
            # Only process "公開招標公告" types
            tender_type = brief.get("type", "")
            if not tender_type.startswith("公開招標"):
                continue
            
            title = brief.get("title", "").strip()
            if not title:
                continue
            
            # unit_name might be null in g0v data
            organization = item.get("unit_name") or ""
            
            # Parse date (integer format YYYYMMDD)
            date_int = item.get("date")
            date_str = str(date_int) if date_int else ""
            bid_date = parse_bid_date(date_str)
            
            # Extract category from brief
            category = brief.get("category", "")
            
            # Build URL from item's url field
            base_url = "https://pcc-api.openfun.app"
            relative_url = item.get("url", "")
            url = normalize_url(base_url, relative_url) if relative_url else ""
            
            # No amount data in listbydate API
            amount_text = ""
            amount_value = None
            
            output.append(
                BidRecord(
                    title=title[:300],
                    organization=organization,
                    bid_date=bid_date,
                    amount_raw=amount_text,
                    amount_value=amount_value,
                    source=SOURCE_NAME,
                    url=url,
                    summary="",
                    category=category,
                    metadata={
                        "raw_date": date_str,
                        "brief_type": tender_type,
                        "unit_id": item.get("unit_id", ""),
                        "job_number": item.get("job_number", ""),
                    },
                )
            )
        
        except Exception as exc:
            logger.warning("g0v_parse_item_failed", extra={"error": str(exc), "item": item.get("job_number", "")})
            continue
    
    return output
