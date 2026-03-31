from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.models import BidRecord


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
        keys = {entity["RowKey"] for entity in entities if entity.get("RowKey")}
        self.logger.info("state_loaded", extra={"backend": "table", "count": len(keys)})
        return keys

    def mark_notified(self, records: list[BidRecord]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for record in records:
            entity = {
                "PartitionKey": "notified",
                "RowKey": record.uid,
                "title": record.title[:240],
                "org": record.organization[:240],
                "source": record.source,
                "created_at": now,
            }
            self.client.upsert_entity(mode="Merge", entity=entity)
        self.logger.info("state_saved", extra={"backend": "table", "count": len(records)})
