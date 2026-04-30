from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.models import BidRecord
from core.stable_keys import notification_keys, primary_notification_key


def _import_azure_blob():
    try:
        from azure.storage.blob import BlobServiceClient
        return BlobServiceClient
    except ImportError as exc:
        raise RuntimeError(
            "azure-storage-blob is not installed. "
            "Run: pip install azure-storage-blob"
        ) from exc


class BlobStateStore:
    def __init__(self, connection_string: str, container: str, blob_name: str, logger: Any) -> None:
        if not connection_string:
            raise ValueError("missing storage connection string")
        self.logger = logger
        self.blob_name = blob_name

        BlobServiceClient = _import_azure_blob()
        service = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = service.get_container_client(container)
        try:
            self.container_client.create_container()
        except Exception:
            pass  # container already exists or ResourceExistsError

    def get_notified_keys(self) -> set[str]:
        data = self._load()
        keys = _all_keys(data)
        self.logger.info("state_loaded", extra={"backend": "blob", "count": len(keys)})
        return keys

    def mark_notified(self, records: list[BidRecord]) -> None:
        data = self._load()
        entries = data.setdefault("entries", {})
        key_index = _key_index(data)
        now = datetime.now(timezone.utc).isoformat()
        for record in records:
            aliases = notification_keys(record)
            primary = primary_notification_key(record)
            entry_key = next((key_index[key] for key in aliases if key in key_index), primary)
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
            alias_set.add(primary)
            alias_set.update(aliases)
            entry.update({
                "title": record.title,
                "org": record.organization,
                "source": record.source,
                "last_seen_at": now,
                "announcement_date": record.announcement_date.isoformat() if record.announcement_date else "",
                "bid_date": record.bid_date.isoformat() if record.bid_date else "",
                "bid_deadline": record.bid_deadline,
            })
            entry.setdefault("first_seen_at", now)
            entry.setdefault("notified_at", now)
            entry["alias_keys"] = sorted(alias_set)
        data["updated_at"] = now
        data["version"] = 2
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        self.container_client.upload_blob(name=self.blob_name, data=payload.encode("utf-8"), overwrite=True)
        self.logger.info("state_saved", extra={"backend": "blob", "count": len(records)})

    def _load(self) -> dict[str, Any]:
        try:
            blob = self.container_client.download_blob(self.blob_name)
            raw = blob.readall().decode("utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return _normalize_state(parsed)
        except json.JSONDecodeError:
            self.logger.warning("blob_state_invalid_json_reset")
        except Exception as exc:
            if type(exc).__name__ == "ResourceNotFoundError":
                return {"version": 2, "entries": {}}
            raise
        return {"version": 2, "entries": {}}


def _normalize_state(data: dict[str, Any]) -> dict[str, Any]:
    if "entries" in data and isinstance(data["entries"], dict):
        data.setdefault("version", 2)
        return data

    legacy = data.get("keys")
    if isinstance(legacy, dict):
        entries: dict[str, Any] = {}
        for key, value in legacy.items():
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


def _all_keys(data: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for primary, entry in data.get("entries", {}).items():
        keys.add(str(primary))
        keys.add(str(entry.get("primary_key") or primary))
        keys.update(str(key) for key in (entry.get("alias_keys") or []) if key)
    return keys


def _key_index(data: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for primary, entry in data.get("entries", {}).items():
        primary_key = str(primary)
        index[primary_key] = primary_key
        index[str(entry.get("primary_key") or primary_key)] = primary_key
        for key in entry.get("alias_keys") or []:
            if key:
                index[str(key)] = primary_key
    return index
