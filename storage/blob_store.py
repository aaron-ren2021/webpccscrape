from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.models import BidRecord


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
        keys = set((data.get("keys") or {}).keys())
        self.logger.info("state_loaded", extra={"backend": "blob", "count": len(keys)})
        return keys

    def mark_notified(self, records: list[BidRecord]) -> None:
        data = self._load()
        keys = data.setdefault("keys", {})
        now = datetime.now(timezone.utc).isoformat()
        for record in records:
            keys[record.uid] = {
                "title": record.title,
                "org": record.organization,
                "source": record.source,
                "created_at": now,
            }
        data["updated_at"] = now
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        self.container_client.upload_blob(name=self.blob_name, data=payload.encode("utf-8"), overwrite=True)
        self.logger.info("state_saved", extra={"backend": "blob", "count": len(records)})

    def _load(self) -> dict[str, Any]:
        try:
            blob = self.container_client.download_blob(self.blob_name)
            raw = blob.readall().decode("utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            self.logger.warning("blob_state_invalid_json_reset")
        except Exception as exc:
            if type(exc).__name__ == "ResourceNotFoundError":
                return {"keys": {}}
            raise
        return {"keys": {}}
