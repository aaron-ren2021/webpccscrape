from __future__ import annotations

from dataclasses import replace
from datetime import date
from difflib import SequenceMatcher
from typing import Optional

from core.models import BidRecord
from core.normalize import amount_key, normalize_org, normalize_text

SOURCE_PRIORITY = {
    "gov_pcc": 3,
    "taiwanbuying": 2,
    "g0v": 1,
}

KEYWORD_CONFIDENCE_PRIORITY = {
    "high_confidence": 2,
    "boundary": 1,
    "excluded_low_score": 0,
    "excluded_strong": 0,
}


def deduplicate_bids(records: list[BidRecord]) -> list[BidRecord]:
    if not records:
        return []

    exact_map: dict[str, BidRecord] = {}
    for record in records:
        key = _exact_key(record)
        if key not in exact_map:
            exact_map[key] = record
            continue
        exact_map[key] = _merge_records(exact_map[key], record)

    first_pass = list(exact_map.values())
    grouped: dict[tuple[str, str], list[BidRecord]] = {}

    for record in first_pass:
        date_key = record.bid_date.isoformat() if record.bid_date else ""
        group_key = (normalize_org(record.organization), date_key)
        bucket = grouped.setdefault(group_key, [])

        merged = False
        for idx, existing in enumerate(bucket):
            if _is_approx_duplicate(existing, record):
                bucket[idx] = _merge_records(existing, record)
                merged = True
                break
        if not merged:
            bucket.append(record)

    result: list[BidRecord] = []
    for bucket in grouped.values():
        result.extend(bucket)
    return result


def _exact_key(record: BidRecord) -> str:
    date_key = record.bid_date.isoformat() if record.bid_date else ""
    return "|".join(
        [
            normalize_text(record.title),
            normalize_org(record.organization),
            date_key,
            amount_key(record.amount_value, record.amount_raw),
        ]
    )


def _is_approx_duplicate(a: BidRecord, b: BidRecord) -> bool:
    if not _same_date(a.bid_date, b.bid_date):
        return False

    if normalize_org(a.organization) != normalize_org(b.organization):
        return False

    title_a = normalize_text(a.title)
    title_b = normalize_text(b.title)
    similarity = SequenceMatcher(a=title_a, b=title_b).ratio()
    if similarity < 0.90:
        return False

    return _amount_close(a.amount_value, b.amount_value)


def _same_date(a: Optional[date], b: Optional[date]) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a == b


def _amount_close(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return True

    diff = abs(a - b)
    if diff <= 5000:
        return True
    baseline = max(abs(a), abs(b), 1.0)
    return diff / baseline <= 0.05


def _merge_records(a: BidRecord, b: BidRecord) -> BidRecord:
    keep, drop = _choose_preferred(a, b)

    merged_backup = _merge_backup_sources(keep, drop)
    merged_tags = sorted(set(keep.tags + drop.tags))
    merged_summary = keep.summary if len(keep.summary) >= len(drop.summary) else drop.summary
    merged_metadata = _merge_metadata(keep, drop)

    merged = replace(
        keep,
        backup_source=merged_backup,
        tags=merged_tags,
        summary=merged_summary,
        metadata=merged_metadata,
    )
    return merged


def _choose_preferred(a: BidRecord, b: BidRecord) -> tuple[BidRecord, BidRecord]:
    pa = SOURCE_PRIORITY.get(a.source, 1)
    pb = SOURCE_PRIORITY.get(b.source, 1)
    if pa > pb:
        return a, b
    if pb > pa:
        return b, a

    score_a = len(a.title) + len(a.organization) + (10 if a.amount_value is not None else 0)
    score_b = len(b.title) + len(b.organization) + (10 if b.amount_value is not None else 0)
    if score_a >= score_b:
        return a, b
    return b, a


def _merge_backup_sources(keep: BidRecord, drop: BidRecord) -> Optional[str]:
    sources: list[str] = []
    for value in [keep.backup_source, drop.backup_source, drop.source]:
        if not value:
            continue
        for s in value.split(","):
            ss = s.strip()
            if ss and ss != keep.source and ss not in sources:
                sources.append(ss)
    return ",".join(sources) if sources else None


def _merge_metadata(keep: BidRecord, drop: BidRecord) -> dict[str, object]:
    merged: dict[str, object] = dict(keep.metadata or {})
    for key, value in (drop.metadata or {}).items():
        if key not in merged or _is_missing_metadata_value(merged.get(key)):
            merged[key] = value

    _promote_g0v_lookup_metadata(merged, keep)
    _promote_g0v_lookup_metadata(merged, drop)
    _merge_keyword_metadata(merged, keep)
    _merge_keyword_metadata(merged, drop)
    return merged


def _promote_g0v_lookup_metadata(merged: dict[str, object], record: BidRecord) -> None:
    metadata = record.metadata or {}
    unit_id = _first_non_empty(metadata.get("g0v_unit_id"), metadata.get("unit_id"))
    job_number = _first_non_empty(metadata.get("g0v_job_number"), metadata.get("job_number"))
    tender_api_url = _first_non_empty(
        metadata.get("g0v_tender_api_url"),
        metadata.get("tender_api_url"),
        record.url if "/api/tender" in record.url else "",
    )

    if unit_id and _is_missing_metadata_value(merged.get("g0v_unit_id")):
        merged["g0v_unit_id"] = unit_id
    if job_number and _is_missing_metadata_value(merged.get("g0v_job_number")):
        merged["g0v_job_number"] = job_number
    if tender_api_url and _is_missing_metadata_value(merged.get("g0v_tender_api_url")):
        merged["g0v_tender_api_url"] = tender_api_url


def _merge_keyword_metadata(merged: dict[str, object], record: BidRecord) -> None:
    metadata = record.metadata or {}
    confidence = str(metadata.get("keyword_confidence") or "").strip()
    current_confidence = str(merged.get("keyword_confidence") or "").strip()
    if KEYWORD_CONFIDENCE_PRIORITY.get(confidence, -1) > KEYWORD_CONFIDENCE_PRIORITY.get(current_confidence, -1):
        merged["keyword_confidence"] = confidence

    score = metadata.get("keyword_score")
    if isinstance(score, (int, float)):
        current_score = merged.get("keyword_score")
        if not isinstance(current_score, (int, float)) or score > current_score:
            merged["keyword_score"] = score

    matched_terms = metadata.get("keyword_matched_terms")
    if isinstance(matched_terms, list):
        merged_terms = list(merged.get("keyword_matched_terms") or [])
        for term in matched_terms:
            if term not in merged_terms:
                merged_terms.append(term)
        if merged_terms:
            merged["keyword_matched_terms"] = merged_terms

    reasons = metadata.get("keyword_reasons")
    if isinstance(reasons, list):
        merged_reasons = list(merged.get("keyword_reasons") or [])
        for reason in reasons:
            if reason not in merged_reasons:
                merged_reasons.append(reason)
        if merged_reasons:
            merged["keyword_reasons"] = merged_reasons

    filter_source = str(metadata.get("filter_source") or "").strip()
    current_filter_source = str(merged.get("filter_source") or "").strip()
    if KEYWORD_CONFIDENCE_PRIORITY.get(confidence, -1) > KEYWORD_CONFIDENCE_PRIORITY.get(current_confidence, -1) and filter_source:
        merged["filter_source"] = filter_source


def _first_non_empty(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _is_missing_metadata_value(value: object | None) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False
