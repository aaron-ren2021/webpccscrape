from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.models import BidRecord
from core.stable_keys import notification_keys, primary_notification_key


def _import_azure_tables():
    try:
        from azure.core.exceptions import ResourceExistsError
        from azure.data.tables import TableServiceClient
        return TableServiceClient, ResourceExistsError
    except ImportError as exc:
        raise RuntimeError(
            "azure-data-tables is not installed. "
            "Run: pip install azure-data-tables"
        ) from exc


class TableStateStore:
    def __init__(self, connection_string: str, table_name: str, logger: Any) -> None:
        if not connection_string:
            raise ValueError("missing storage connection string")
        self.logger = logger
        self.table_name = table_name
        TableServiceClient, ResourceExistsError = _import_azure_tables()
        service = TableServiceClient.from_connection_string(conn_str=connection_string)
        try:
            service.create_table(table_name)
        except Exception:
            pass  # table already exists or ResourceExistsError
        self.client = service.get_table_client(table_name)

    def get_notified_keys(self) -> set[str]:
        entities = self.client.query_entities("PartitionKey eq 'notified'")
        keys: set[str] = set()
        for entity in entities:
            row_key = entity.get("RowKey")
            if row_key:
                keys.add(str(row_key))
            try:
                aliases = json.loads(str(entity.get("alias_keys_json") or "[]"))
            except json.JSONDecodeError:
                aliases = []
            if isinstance(aliases, list):
                keys.update(str(key) for key in aliases if key)
        self.logger.info("state_loaded", extra={"backend": "table", "count": len(keys)})
        return keys

    def mark_notified(self, records: list[BidRecord]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for record in records:
            aliases = notification_keys(record)
            primary = primary_notification_key(record)
            alias_set = sorted(set(aliases + [primary, record.uid]))
            entity = {
                "PartitionKey": "notified",
                "RowKey": primary,
                "primary_key": primary,
                "alias_keys_json": json.dumps(alias_set, ensure_ascii=False),
                "title": record.title[:240],
                "org": record.organization[:240],
                "source": record.source,
                "first_seen_at": now,
                "last_seen_at": now,
                "notified_at": now,
                "announcement_date": record.announcement_date.isoformat() if record.announcement_date else "",
                "bid_date": record.bid_date.isoformat() if record.bid_date else "",
                "bid_deadline": record.bid_deadline[:240],
            }
            self.client.upsert_entity(mode="Merge", entity=entity)
        self.logger.info("state_saved", extra={"backend": "table", "count": len(records)})
