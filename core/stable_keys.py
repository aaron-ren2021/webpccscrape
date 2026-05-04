from __future__ import annotations

import hashlib
from datetime import date
from urllib.parse import parse_qs, urlparse

from core.models import BidRecord
from core.normalize import amount_key, build_bid_uid, normalize_org, normalize_text


def notification_keys(record: BidRecord) -> list[str]:
    keys: list[str] = []

    for key in _source_identity_keys(record):
        _append_unique(keys, key)

    url_key = _url_key(record.url)
    if url_key:
        _append_unique(keys, url_key)

    for fallback in _fallback_keys(record):
        _append_unique(keys, fallback)

    for legacy in _legacy_uid_keys(record):
        _append_unique(keys, legacy)

    if record.uid:
        _append_unique(keys, record.uid)

    return keys


def primary_notification_key(record: BidRecord) -> str:
    keys = notification_keys(record)
    if keys:
        return keys[0]
    return _hash_key("fallback:empty", "")


def effective_record_date(record: BidRecord) -> date | None:
    return record.announcement_date or record.bid_date


def _source_identity_keys(record: BidRecord) -> list[str]:
    metadata = record.metadata or {}
    keys: list[str] = []

    pk = _first_non_empty(
        metadata.get("pkPmsMain"),
        metadata.get("pk_pms_main"),
        _query_value(record.url, "pkPmsMain"),
        _query_value(str(metadata.get("g0v_human_url") or ""), "pkPmsMain"),
    )
    if pk:
        keys.append(f"source:gov_pcc:pkPmsMain:{normalize_text(pk)}")

    unit_id = _first_non_empty(
        metadata.get("g0v_unit_id"),
        metadata.get("unit_id"),
        _query_value(str(metadata.get("g0v_tender_api_url") or ""), "unit_id"),
        _query_value(str(metadata.get("tender_api_url") or ""), "unit_id"),
        _query_value(record.url, "unit_id"),
    )
    job_number = _first_non_empty(
        metadata.get("g0v_job_number"),
        metadata.get("job_number"),
        _query_value(str(metadata.get("g0v_tender_api_url") or ""), "job_number"),
        _query_value(str(metadata.get("tender_api_url") or ""), "job_number"),
        _query_value(record.url, "job_number"),
    )
    if unit_id and job_number:
        keys.append(f"source:g0v:{normalize_text(unit_id)}:{normalize_text(job_number)}")

    taiwanbuying_id = _first_non_empty(
        metadata.get("taiwanbuying_id"),
        metadata.get("tbn"),
        metadata.get("TBN"),
        _query_value(record.url, "TBN"),
        _query_value(record.url, "tbn"),
        _query_value(str(metadata.get("taiwanbuying_url") or ""), "TBN"),
        _query_value(str(metadata.get("taiwanbuying_url") or ""), "tbn"),
    )
    if taiwanbuying_id:
        keys.append(f"source:taiwanbuying:{normalize_text(taiwanbuying_id)}")

    return keys


def _fallback_keys(record: BidRecord) -> list[str]:
    title = normalize_text(record.title)
    org = normalize_org(record.organization)
    amount = amount_key(record.amount_value, record.amount_raw)
    if not title and not org:
        return []

    base = "|".join([title, org, amount])
    keys = [_hash_key("fallback:title_org_amount", base)]

    for value in [record.announcement_date, record.bid_date]:
        if value:
            keys.append(_hash_key("fallback:title_org_amount_date", f"{base}|{value.isoformat()}"))
    return keys


def _legacy_uid_keys(record: BidRecord) -> list[str]:
    keys: list[str] = []
    for value in [record.bid_date, record.announcement_date, None]:
        keys.append(
            build_bid_uid(
                title=record.title,
                org=record.organization,
                bid_date=value,
                amount=record.amount_value,
                amount_raw=record.amount_raw,
            )
        )
    return keys


def _url_key(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return _hash_key("url", text.lower())


def _query_value(url: str, name: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    values = parse_qs(parsed.query).get(name)
    if not values:
        return ""
    return str(values[0]).strip()


def _hash_key(prefix: str, payload: str) -> str:
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _first_non_empty(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)
