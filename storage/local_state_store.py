from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from core.models import BidRecord
from core.normalize import parse_bid_deadline_text
from core.stable_keys import notification_keys, primary_notification_key


class LocalJsonStateStore:
    def __init__(self, path: str | Path, logger: Any, retention_days: int = 90) -> None:
        self.path = Path(path).resolve()
        self.logger = logger
        self.retention_days = max(retention_days, 1)

    def get_notified_keys(self) -> set[str]:
        data = self._load()
        data = self._cleanup(data)
        self._save(data)
        keys = self._all_keys(data)
        self.logger.info("state_loaded", extra={"backend": "local_json", "count": len(keys)})
        return keys

    def mark_notified(self, records: list[BidRecord]) -> None:
        data = self._cleanup(self._load())
        entries = data.setdefault("entries", {})
        index = self._key_index(data)
        now = datetime.now(timezone.utc).isoformat()

        for record in records:
            aliases = notification_keys(record)
            primary = primary_notification_key(record)
            entry_key = next((index[key] for key in aliases if key in index), primary)
            entry = entries.setdefault(
                entry_key,
                {
                    "primary_key": entry_key,
                    "alias_keys": [],
                    "first_seen_at": now,
                    "notified_at": now,
                },
            )

            alias_set = set(entry.get("alias_keys") or [])
            alias_set.add(entry_key)
            alias_set.update(aliases)
            alias_set.add(primary)
            entry["alias_keys"] = sorted(alias_set)
            entry["title"] = record.title[:300]
            entry["org"] = record.organization[:240]
            entry["source"] = record.source
            entry["last_seen_at"] = now
            entry.setdefault("first_seen_at", now)
            entry["notified_at"] = entry.get("notified_at") or now
            entry["announcement_date"] = _date_to_str(record.announcement_date)
            entry["bid_date"] = _date_to_str(record.bid_date)
            entry["bid_deadline"] = record.bid_deadline

        data["updated_at"] = now
        self._save(data)
        self.logger.info("state_saved", extra={"backend": "local_json", "count": len(records)})

    def _load(self) -> dict[str, Any]:
        try:
            raw = self.path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return _normalize_state(parsed)
        except FileNotFoundError:
            return {"version": 2, "entries": {}}
        except json.JSONDecodeError:
            self.logger.warning("local_state_invalid_json_reset", extra={"path": str(self.path)})
        return {"version": 2, "entries": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        self.path.write_text(payload, encoding="utf-8")

    def _cleanup(self, data: dict[str, Any]) -> dict[str, Any]:
        entries = data.setdefault("entries", {})
        cutoff = datetime.now(timezone.utc).timestamp() - self.retention_days * 86400
        kept: dict[str, Any] = {}
        removed = 0
        for key, entry in entries.items():
            notified_at = _parse_datetime(str(entry.get("notified_at") or ""))
            if notified_at and notified_at.timestamp() < cutoff and _is_expired_or_missing_deadline(entry):
                removed += 1
                continue
            kept[key] = entry
        data["entries"] = kept
        if removed:
            self.logger.info("state_pruned", extra={"backend": "local_json", "count": removed})
        return data

    def _all_keys(self, data: dict[str, Any]) -> set[str]:
        keys: set[str] = set()
        for primary, entry in data.get("entries", {}).items():
            keys.add(primary)
            keys.add(str(entry.get("primary_key") or primary))
            keys.update(str(key) for key in (entry.get("alias_keys") or []) if key)
        return keys

    def _key_index(self, data: dict[str, Any]) -> dict[str, str]:
        index: dict[str, str] = {}
        for primary, entry in data.get("entries", {}).items():
            index[primary] = primary
            index[str(entry.get("primary_key") or primary)] = primary
            for key in entry.get("alias_keys") or []:
                if key:
                    index[str(key)] = primary
        return index


def _normalize_state(data: dict[str, Any]) -> dict[str, Any]:
    if "entries" in data and isinstance(data["entries"], dict):
        data.setdefault("version", 2)
        return data

    # Migrate the legacy blob format: {"keys": {"uid": {...}}}
    legacy_keys = data.get("keys")
    if isinstance(legacy_keys, dict):
        entries: dict[str, Any] = {}
        for key, value in legacy_keys.items():
            metadata = value if isinstance(value, dict) else {}
            entries[str(key)] = {
                "primary_key": str(key),
                "alias_keys": [str(key)],
                "title": str(metadata.get("title") or ""),
                "org": str(metadata.get("org") or ""),
                "source": str(metadata.get("source") or ""),
                "first_seen_at": str(metadata.get("created_at") or data.get("updated_at") or ""),
                "last_seen_at": str(metadata.get("created_at") or data.get("updated_at") or ""),
                "notified_at": str(metadata.get("created_at") or data.get("updated_at") or ""),
            }
        return {"version": 2, "entries": entries, "updated_at": data.get("updated_at", "")}

    return {"version": 2, "entries": {}}


def _date_to_str(value: date | None) -> str:
    return value.isoformat() if value else ""


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


def _is_expired_or_missing_deadline(entry: dict[str, Any]) -> bool:
    deadline = str(entry.get("bid_deadline") or "").strip()
    if not deadline:
        return True
    parsed = parse_bid_deadline_text(deadline)
    if not parsed:
        return True
    deadline_date, _deadline_time = parsed
    return deadline_date < datetime.now(timezone.utc).date()
