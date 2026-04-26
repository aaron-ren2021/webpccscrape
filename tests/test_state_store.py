from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

from core.config import Settings
from core.models import BidRecord
from core.pipeline import InMemoryStateStore, _resolve_state_store
from storage.blob_store import BlobStateStore
from storage.table_store import TableStateStore


class ResourceNotFoundError(Exception):
    pass


class FakeBlob:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def readall(self) -> bytes:
        return self.payload


class FakeContainer:
    def __init__(self, data_store: dict[str, bytes]) -> None:
        self.data_store = data_store
        self.created = 0

    def create_container(self) -> None:
        self.created += 1

    def download_blob(self, blob_name: str) -> FakeBlob:
        if blob_name not in self.data_store:
            raise ResourceNotFoundError("missing blob")
        return FakeBlob(self.data_store[blob_name])

    def upload_blob(self, name: str, data: bytes, overwrite: bool) -> None:
        self.data_store[name] = data


def _make_blob_service(data_store: dict[str, bytes]):
    class FakeBlobServiceClient:
        def __init__(self) -> None:
            self.container = FakeContainer(data_store)

        @classmethod
        def from_connection_string(cls, connection_string: str) -> "FakeBlobServiceClient":
            return cls()

        def get_container_client(self, container: str) -> FakeContainer:
            return self.container

    return FakeBlobServiceClient


class FakeTableClient:
    def __init__(self, entities: list[dict[str, object]]) -> None:
        self.entities = list(entities)
        self.upserts: list[dict[str, object]] = []

    def query_entities(self, query: str) -> list[dict[str, object]]:
        return list(self.entities)

    def upsert_entity(self, mode: str, entity: dict[str, object]) -> None:
        self.upserts.append(entity)
        self.entities.append(entity)


def _make_table_service(entities: list[dict[str, object]]):
    class FakeTableServiceClient:
        def __init__(self) -> None:
            self.client = FakeTableClient(entities)
            self.created_tables: list[str] = []

        @classmethod
        def from_connection_string(cls, conn_str: str) -> "FakeTableServiceClient":
            return cls()

        def create_table(self, table_name: str) -> None:
            self.created_tables.append(table_name)

        def get_table_client(self, table_name: str) -> FakeTableClient:
            return self.client

    return FakeTableServiceClient


def _record(uid: str, title: str = "測試案", org: str = "某某大學") -> BidRecord:
    return BidRecord(
        title=title,
        organization=org,
        bid_date=date(2026, 4, 26),
        amount_raw="100萬",
        amount_value=1_000_000,
        source="gov_pcc",
        url=f"https://example.com/{uid}",
        uid=uid,
    )


def test_blob_store_reads_existing_keys(monkeypatch) -> None:
    data_store = {
        "state.json": json.dumps({"keys": {"a": {}, "b": {}}}).encode("utf-8"),
    }
    monkeypatch.setattr(
        "storage.blob_store._import_azure_blob", lambda: _make_blob_service(data_store)
    )
    logger = MagicMock()
    store = BlobStateStore("conn", "container", "state.json", logger)

    assert store.get_notified_keys() == {"a", "b"}
    logger.info.assert_any_call("state_loaded", extra={"backend": "blob", "count": 2})


def test_blob_store_invalid_json_resets(monkeypatch) -> None:
    data_store = {"state.json": b"{invalid json"}
    monkeypatch.setattr(
        "storage.blob_store._import_azure_blob", lambda: _make_blob_service(data_store)
    )
    logger = MagicMock()
    store = BlobStateStore("conn", "container", "state.json", logger)

    assert store.get_notified_keys() == set()
    logger.warning.assert_called_once_with("blob_state_invalid_json_reset")


def test_blob_store_mark_notified_uploads_payload(monkeypatch) -> None:
    data_store: dict[str, bytes] = {}
    monkeypatch.setattr(
        "storage.blob_store._import_azure_blob", lambda: _make_blob_service(data_store)
    )
    logger = MagicMock()
    store = BlobStateStore("conn", "container", "state.json", logger)

    store.mark_notified([_record("uid-1")])

    payload = json.loads(data_store["state.json"].decode("utf-8"))
    assert payload["keys"]["uid-1"]["title"] == "測試案"
    assert payload["keys"]["uid-1"]["org"] == "某某大學"
    assert payload["keys"]["uid-1"]["source"] == "gov_pcc"
    assert "updated_at" in payload


def test_table_store_reads_keys(monkeypatch) -> None:
    entities = [{"RowKey": "a"}, {"RowKey": "b"}, {"Other": "ignore"}]
    FakeTableServiceClient = _make_table_service(entities)
    monkeypatch.setattr(
        "storage.table_store._import_azure_tables",
        lambda: (FakeTableServiceClient, Exception),
    )
    logger = MagicMock()
    store = TableStateStore("conn", "BidNotifyState", logger)

    assert store.get_notified_keys() == {"a", "b"}
    logger.info.assert_any_call("state_loaded", extra={"backend": "table", "count": 2})


def test_table_store_mark_notified_truncates_fields(monkeypatch) -> None:
    FakeTableServiceClient = _make_table_service([])
    monkeypatch.setattr(
        "storage.table_store._import_azure_tables",
        lambda: (FakeTableServiceClient, Exception),
    )
    logger = MagicMock()
    store = TableStateStore("conn", "BidNotifyState", logger)

    long_title = "T" * 250
    long_org = "O" * 250
    store.mark_notified([_record("uid-2", title=long_title, org=long_org)])

    entity = store.client.upserts[0]
    assert entity["PartitionKey"] == "notified"
    assert entity["RowKey"] == "uid-2"
    assert len(entity["title"]) == 240
    assert len(entity["org"]) == 240


def test_resolve_state_store_defaults_to_memory() -> None:
    settings = Settings(azure_storage_connection_string="")
    logger = MagicMock()

    store = _resolve_state_store(settings, logger)

    assert isinstance(store, InMemoryStateStore)
    logger.warning.assert_called_once_with("state_store_selected", extra={"backend": "memory"})


def test_resolve_state_store_falls_back_to_blob(monkeypatch) -> None:
    class ExplodingTableStore:
        def __init__(self, **_kwargs: object) -> None:
            raise RuntimeError("boom")

    class DummyBlobStore:
        def __init__(self, **_kwargs: object) -> None:
            self.marker = "blob"

    settings = Settings(azure_storage_connection_string="conn")
    logger = MagicMock()

    monkeypatch.setattr("core.pipeline.TableStateStore", ExplodingTableStore)
    monkeypatch.setattr("core.pipeline.BlobStateStore", DummyBlobStore)

    store = _resolve_state_store(settings, logger)

    assert isinstance(store, DummyBlobStore)


def test_resolve_state_store_falls_back_to_memory(monkeypatch) -> None:
    class ExplodingTableStore:
        def __init__(self, **_kwargs: object) -> None:
            raise RuntimeError("boom")

    class ExplodingBlobStore:
        def __init__(self, **_kwargs: object) -> None:
            raise RuntimeError("boom")

    settings = Settings(azure_storage_connection_string="conn")
    logger = MagicMock()

    monkeypatch.setattr("core.pipeline.TableStateStore", ExplodingTableStore)
    monkeypatch.setattr("core.pipeline.BlobStateStore", ExplodingBlobStore)

    store = _resolve_state_store(settings, logger)

    assert isinstance(store, InMemoryStateStore)
