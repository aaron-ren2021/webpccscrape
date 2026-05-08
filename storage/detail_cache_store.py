from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.models import BidRecord
from core.normalize import parse_bid_deadline_text
from core.stable_keys import notification_keys, primary_notification_key


DETAIL_MISSING_VALUES = {
    "",
    "none",
    "null",
    "無",
    "無提供",
    "n/a",
    "詳見連結",
    "已公開（金額見詳細頁）",
}


class DetailCacheStore:
    def __init__(
        self,
        cache_path: str | Path,
        queue_path: str | Path,
        logger: Any,
        ttl_days: int = 90,
        max_attempts: int = 3,
    ) -> None:
        self.cache_path = Path(cache_path).resolve()
        self.queue_path = Path(queue_path).resolve()
        self.logger = logger
        self.ttl_days = max(ttl_days, 1)
        self.max_attempts = max(max_attempts, 1)

    def apply_to_records(self, records: list[BidRecord]) -> dict[str, int]:
        cache = self._cleanup_cache(self._load_json(self.cache_path, "detail_cache"))
        if cache.get("entries") or self.cache_path.exists():
            self._save_json(self.cache_path, cache)
        index = self._key_index(cache)
        hits = 0
        misses = 0

        for record in records:
            key = self._find_entry_key(record, index)
            entry = cache.get("entries", {}).get(key) if key else None
            if not isinstance(entry, dict) or not _entry_is_success(entry):
                record.metadata["detail_cache_status"] = "miss"
                misses += 1
                continue
            self._apply_entry(record, entry)
            hits += 1

        self.logger.info("detail_cache_summary", extra={"hit": hits, "miss": misses})
        return {"hit": hits, "miss": misses}

    def enqueue_missing(self, records: list[BidRecord]) -> int:
        queue = self._load_json(self.queue_path, "detail_backfill_queue")
        entries = queue.setdefault("entries", {})
        index = self._key_index(queue)
        queued = 0
        now = _utc_now()

        for record in records:
            if not _should_backfill(record):
                continue
            aliases = notification_keys(record)
            primary = primary_notification_key(record)
            entry_key = next((index[key] for key in aliases if key in index), primary)
            existing = entries.get(entry_key)
            if isinstance(existing, dict) and _source_attempt_count(existing, record.source) >= self.max_attempts:
                self.logger.info(
                    "detail_backfill_skipped",
                    extra={"reason": "max_attempts", "key": entry_key, "source": record.source},
                )
                continue

            entry = _record_to_entry(record, status="pending", now=now)
            entry["primary_key"] = entry_key
            entry["alias_keys"] = sorted(set([entry_key, primary, *aliases]))
            if isinstance(existing, dict):
                entry["first_seen_at"] = existing.get("first_seen_at") or entry["first_seen_at"]
                entry["attempt_count"] = int(existing.get("attempt_count") or 0)
                entry["attempt_counts"] = _attempt_counts(existing)
                entry["last_attempt_at"] = str(existing.get("last_attempt_at") or "")
                entry["failure_reason"] = str(existing.get("failure_reason") or "")
            entries[entry_key] = entry
            queued += 1

        if queued:
            queue["updated_at"] = now
            self._save_json(self.queue_path, queue)
        self.logger.info("detail_backfill_queued", extra={"count": queued})
        return queued

    def get_pending_records(self, *, limit: int, sources: set[str] | None = None) -> list[BidRecord]:
        queue = self._load_json(self.queue_path, "detail_backfill_queue")
        records: list[BidRecord] = []
        max_count = max(limit, 0)
        for key, entry in queue.get("entries", {}).items():
            if max_count and len(records) >= max_count:
                break
            if not isinstance(entry, dict):
                continue
            source = str(entry.get("source") or "")
            if sources and source not in sources:
                continue
            if _source_attempt_count(entry, source) >= self.max_attempts:
                continue
            record = _entry_to_record(entry)
            record.uid = str(entry.get("primary_key") or key)
            records.append(record)
        return records

    def mark_success(self, record: BidRecord) -> None:
        cache = self._cleanup_cache(self._load_json(self.cache_path, "detail_cache"))
        queue = self._load_json(self.queue_path, "detail_backfill_queue")
        now = _utc_now()

        cache_entries = cache.setdefault("entries", {})
        queue_entries = queue.setdefault("entries", {})
        queue_index = self._key_index(queue)
        primary = primary_notification_key(record)
        aliases = notification_keys(record)
        entry_key = next((queue_index[key] for key in aliases if key in queue_index), primary)

        entry = _record_to_entry(record, status="success", now=now)
        entry["primary_key"] = entry_key
        entry["alias_keys"] = sorted(set([entry_key, primary, *aliases]))
        entry["last_success_at"] = now
        entry["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=self.ttl_days)).isoformat()
        cache_entries[entry_key] = entry

        for alias in entry["alias_keys"]:
            queue_key = queue_index.get(alias)
            if queue_key:
                queue_entries.pop(queue_key, None)

        cache["updated_at"] = now
        queue["updated_at"] = now
        self._save_json(self.cache_path, cache)
        self._save_json(self.queue_path, queue)
        self.logger.info("detail_cache_saved", extra={"key": entry_key, "source": record.source})

    def mark_failure(self, record: BidRecord, reason: str) -> None:
        queue = self._load_json(self.queue_path, "detail_backfill_queue")
        entries = queue.setdefault("entries", {})
        index = self._key_index(queue)
        primary = primary_notification_key(record)
        aliases = notification_keys(record)
        entry_key = next((index[key] for key in aliases if key in index), primary)
        now = _utc_now()
        entry = entries.get(entry_key)
        if not isinstance(entry, dict):
            entry = _record_to_entry(record, status="failed", now=now)
            entry["primary_key"] = entry_key
            entry["alias_keys"] = sorted(set([entry_key, primary, *aliases]))
        entry["status"] = "failed"
        entry["failure_reason"] = reason[:240]
        entry["attempt_count"] = int(entry.get("attempt_count") or 0) + 1
        attempt_counts = _attempt_counts(entry)
        attempt_counts[record.source] = int(attempt_counts.get(record.source) or 0) + 1
        entry["attempt_counts"] = attempt_counts
        entry["last_attempt_at"] = now
        entries[entry_key] = entry
        queue["updated_at"] = now
        self._save_json(self.queue_path, queue)
        self.logger.warning(
            "detail_backfill_failed",
            extra={
                "key": entry_key,
                "source": record.source,
                "reason": reason[:120],
                "attempt_count": entry["attempt_count"],
            },
        )

    def _load_json(self, path: Path, event_name: str) -> dict[str, Any]:
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                parsed.setdefault("version", 1)
                parsed.setdefault("entries", {})
                return parsed
        except FileNotFoundError:
            return {"version": 1, "entries": {}}
        except json.JSONDecodeError:
            self.logger.warning(f"{event_name}_invalid_json_reset", extra={"path": str(path)})
        return {"version": 1, "entries": {}}

    def _save_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, path)

    def _cleanup_cache(self, data: dict[str, Any]) -> dict[str, Any]:
        entries = data.setdefault("entries", {})
        now = datetime.now(timezone.utc)
        kept: dict[str, Any] = {}
        removed = 0
        for key, entry in entries.items():
            if not isinstance(entry, dict) or _cache_entry_expired(entry, now):
                removed += 1
                continue
            kept[key] = entry
        data["entries"] = kept
        if removed:
            self.logger.info("detail_cache_pruned", extra={"count": removed})
        return data

    def _key_index(self, data: dict[str, Any]) -> dict[str, str]:
        index: dict[str, str] = {}
        for primary, entry in data.get("entries", {}).items():
            primary_key = str(primary)
            index[primary_key] = primary_key
            if isinstance(entry, dict):
                index[str(entry.get("primary_key") or primary_key)] = primary_key
                for alias in entry.get("alias_keys") or []:
                    if alias:
                        index[str(alias)] = primary_key
        return index

    def _find_entry_key(self, record: BidRecord, index: dict[str, str]) -> str:
        for key in notification_keys(record):
            if key in index:
                return index[key]
        return ""

    def _apply_entry(self, record: BidRecord, entry: dict[str, Any]) -> None:
        if _is_missing(record.budget_amount) and not _is_missing(str(entry.get("budget_amount") or "")):
            record.budget_amount = str(entry.get("budget_amount") or "")
        if record.amount_value is None and entry.get("amount_value") is not None:
            try:
                record.amount_value = float(entry["amount_value"])
            except (TypeError, ValueError):
                pass
        if _is_missing(record.amount_raw) and not _is_missing(str(entry.get("amount_raw") or "")):
            record.amount_raw = str(entry.get("amount_raw") or "")
        if _is_missing(record.bid_bond) and not _is_missing(str(entry.get("bid_bond") or "")):
            record.bid_bond = str(entry.get("bid_bond") or "")
        if _is_missing(record.bid_deadline) and not _is_missing(str(entry.get("bid_deadline") or "")):
            record.bid_deadline = str(entry.get("bid_deadline") or "")
        if _is_missing(record.bid_opening_time) and not _is_missing(str(entry.get("bid_opening_time") or "")):
            record.bid_opening_time = str(entry.get("bid_opening_time") or "")
        official_url = str(entry.get("official_url") or "").strip()
        if official_url:
            record.url = official_url
            record.metadata["g0v_link_resolution_state"] = str(
                entry.get("g0v_link_resolution_state") or "resolved_official"
            )
        record.metadata["detail_cache_status"] = "hit"
        record.metadata["enrichment_source"] = _append_source(
            str(record.metadata.get("enrichment_source") or ""),
            "detail_cache",
        )


def _record_to_entry(record: BidRecord, *, status: str, now: str) -> dict[str, Any]:
    metadata = record.metadata or {}
    official_url = record.url
    if str(metadata.get("g0v_link_resolution_state") or "") == "fallback_api":
        official_url = str(metadata.get("g0v_human_url") or record.url)
    return {
        "primary_key": primary_notification_key(record),
        "alias_keys": notification_keys(record),
        "title": record.title[:300],
        "org": record.organization[:240],
        "source": record.source,
        "url": record.url,
        "official_url": official_url,
        "metadata": metadata,
        "amount_raw": record.amount_raw,
        "amount_value": record.amount_value,
        "budget_amount": record.budget_amount,
        "bid_bond": record.bid_bond,
        "bid_deadline": record.bid_deadline,
        "bid_opening_time": record.bid_opening_time,
        "announcement_date": _date_to_str(record.announcement_date),
        "bid_date": _date_to_str(record.bid_date),
        "status": status,
        "failure_reason": "",
        "attempt_count": 0,
        "attempt_counts": {},
        "first_seen_at": now,
        "last_attempt_at": "",
        "last_success_at": now if status == "success" else "",
        "expires_at": "",
    }


def _entry_to_record(entry: dict[str, Any]) -> BidRecord:
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    record = BidRecord(
        title=str(entry.get("title") or ""),
        organization=str(entry.get("org") or ""),
        bid_date=_parse_date(str(entry.get("bid_date") or "")),
        amount_raw=str(entry.get("amount_raw") or ""),
        amount_value=_parse_float_or_none(entry.get("amount_value")),
        source=str(entry.get("source") or ""),
        url=str(entry.get("url") or ""),
        metadata=dict(metadata),
        announcement_date=_parse_date(str(entry.get("announcement_date") or "")),
    )
    record.budget_amount = str(entry.get("budget_amount") or "")
    record.bid_bond = str(entry.get("bid_bond") or "")
    record.bid_deadline = str(entry.get("bid_deadline") or "")
    record.bid_opening_time = str(entry.get("bid_opening_time") or "")
    return record


def _should_backfill(record: BidRecord) -> bool:
    if record.source not in {"gov_pcc", "g0v"}:
        return False
    if record.source == "gov_pcc" and not record.url:
        return False
    if record.source == "g0v" and not (
        record.url
        or record.metadata.get("g0v_tender_api_url")
        or (record.metadata.get("g0v_unit_id") and record.metadata.get("g0v_job_number"))
    ):
        return False
    return (
        _amount_missing(record)
        or _is_missing(record.budget_amount)
        or _is_missing(record.bid_bond)
        or _is_missing(record.bid_opening_time)
        or _is_missing(record.bid_deadline)
    )


def _entry_is_success(entry: dict[str, Any]) -> bool:
    if str(entry.get("status") or "") != "success":
        return False
    return (
        entry.get("amount_value") is not None
        or not _is_missing(str(entry.get("budget_amount") or ""))
        or not _is_missing(str(entry.get("bid_bond") or ""))
        or not _is_missing(str(entry.get("bid_opening_time") or ""))
        or not _is_missing(str(entry.get("bid_deadline") or ""))
        or bool(str(entry.get("official_url") or "").strip())
    )


def _cache_entry_expired(entry: dict[str, Any], now: datetime) -> bool:
    expires_at = _parse_datetime(str(entry.get("expires_at") or ""))
    if expires_at and expires_at < now:
        return True
    deadline = str(entry.get("bid_deadline") or "").strip()
    if not deadline:
        return False
    parsed_deadline = parse_bid_deadline_text(deadline)
    if not parsed_deadline:
        return False
    deadline_date, _deadline_time = parsed_deadline
    return deadline_date < now.date() - timedelta(days=1)


def _is_missing(value: str) -> bool:
    return str(value or "").strip().lower() in DETAIL_MISSING_VALUES


def _amount_missing(record: BidRecord) -> bool:
    return record.amount_value is None and str(record.budget_amount or "").strip() != "未公開"


def _append_source(current: str, source: str) -> str:
    parts = [part for part in current.split("+") if part]
    if source not in parts:
        parts.append(source)
    return "+".join(parts)


def _attempt_counts(entry: dict[str, Any]) -> dict[str, int]:
    raw = entry.get("attempt_counts")
    if not isinstance(raw, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in raw.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return counts


def _source_attempt_count(entry: dict[str, Any], source: str) -> int:
    counts = _attempt_counts(entry)
    if source in counts:
        return counts[source]
    return int(entry.get("attempt_count") or 0)


def _date_to_str(value: date | None) -> str:
    return value.isoformat() if value else ""


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
