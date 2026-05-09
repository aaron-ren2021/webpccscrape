from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from core.models import BidRecord
from storage.detail_cache_store import DetailCacheStore


def _record(source: str = "gov_pcc") -> BidRecord:
    url = "https://web.pcc.gov.tw/tps/QueryTender/query/searchTenderDetail?pkPmsMain=AAA"
    if source == "g0v":
        url = "https://pcc-api.openfun.app/api/tender?unit_id=UNIT001&job_number=JOB001"
    return BidRecord(
        title="測試詳情案",
        organization="測試機關",
        bid_date=date(2026, 5, 10),
        amount_raw="",
        amount_value=None,
        source=source,
        url=url,
        metadata={"g0v_unit_id": "UNIT001", "g0v_job_number": "JOB001"} if source == "g0v" else {},
    )


def test_detail_cache_hit_applies_fields(tmp_path) -> None:
    store = DetailCacheStore(
        cache_path=tmp_path / "detail_cache.json",
        queue_path=tmp_path / "detail_queue.json",
        logger=MagicMock(),
    )
    record = _record()
    record.budget_amount = "NT$ 1,000,000 元"
    record.bid_bond = "免繳"
    record.bid_deadline = "115/05/10 17:00"
    store.mark_success(record)

    fresh = _record()
    fresh.budget_amount = ""
    fresh.bid_bond = ""
    fresh.bid_deadline = ""
    summary = store.apply_to_records([fresh])

    assert summary == {"hit": 1, "miss": 0}
    assert fresh.budget_amount == "NT$ 1,000,000 元"
    assert fresh.bid_bond == "免繳"
    assert fresh.bid_deadline == "115/05/10 17:00"
    assert fresh.metadata["detail_cache_status"] == "hit"


def test_detail_cache_miss_queues_by_dict_key_and_deduplicates(tmp_path) -> None:
    store = DetailCacheStore(
        cache_path=tmp_path / "detail_cache.json",
        queue_path=tmp_path / "detail_queue.json",
        logger=MagicMock(),
    )
    record = _record()

    assert store.enqueue_missing([record]) == 1
    assert store.enqueue_missing([record]) == 1

    data = json.loads((tmp_path / "detail_queue.json").read_text(encoding="utf-8"))
    assert isinstance(data["entries"], dict)
    assert len(data["entries"]) == 1
    assert next(iter(data["entries"].values()))["title"] == "測試詳情案"


def test_detail_cache_queues_when_amount_is_still_missing(tmp_path) -> None:
    store = DetailCacheStore(
        cache_path=tmp_path / "detail_cache.json",
        queue_path=tmp_path / "detail_queue.json",
        logger=MagicMock(),
    )
    record = _record()
    record.budget_amount = "已公開（金額見詳細頁）"
    record.bid_bond = "免繳"
    record.bid_deadline = "115/05/10 17:00"
    record.bid_opening_time = "115/05/11 10:00"

    assert store.enqueue_missing([record]) == 1


def test_detail_cache_queues_placeholder_detail_values(tmp_path) -> None:
    store = DetailCacheStore(
        cache_path=tmp_path / "detail_cache.json",
        queue_path=tmp_path / "detail_queue.json",
        logger=MagicMock(),
    )
    record = _record()
    record.amount_value = 1_000_000
    record.budget_amount = "NT$ 1,000,000 元"
    record.bid_bond = "免繳"
    record.bid_deadline = "詳見連結"
    record.bid_opening_time = "115/05/11 10:00"

    assert store.enqueue_missing([record]) == 1


def test_detail_cache_failure_counts_are_per_source(tmp_path) -> None:
    store = DetailCacheStore(
        cache_path=tmp_path / "detail_cache.json",
        queue_path=tmp_path / "detail_queue.json",
        logger=MagicMock(),
        max_attempts=2,
    )
    gov_record = _record("gov_pcc")
    g0v_record = _record("g0v")
    store.enqueue_missing([gov_record, g0v_record])

    store.mark_failure(gov_record, "captcha")
    store.mark_failure(gov_record, "captcha")

    pending_all = store.get_pending_records(limit=10)
    assert {record.source for record in pending_all} == {"g0v"}

    data = json.loads((tmp_path / "detail_queue.json").read_text(encoding="utf-8"))
    gov_entries = [entry for entry in data["entries"].values() if entry["source"] == "gov_pcc"]
    assert gov_entries[0]["attempt_counts"]["gov_pcc"] == 2


def test_detail_cache_prunes_expired_entries(tmp_path) -> None:
    cache_path = tmp_path / "detail_cache.json"
    old = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    "old": {
                        "primary_key": "old",
                        "alias_keys": ["old"],
                        "status": "success",
                        "budget_amount": "NT$ 1 元",
                        "expires_at": old,
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = DetailCacheStore(
        cache_path=cache_path,
        queue_path=tmp_path / "detail_queue.json",
        logger=MagicMock(),
    )

    summary = store.apply_to_records([_record()])
    data = json.loads(cache_path.read_text(encoding="utf-8"))

    assert summary == {"hit": 0, "miss": 1}
    assert data["entries"] == {}
