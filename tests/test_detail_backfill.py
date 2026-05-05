from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

from core.config import Settings
from core.detail_backfill import run_detail_backfill
from core.models import BidRecord
from storage.detail_cache_store import DetailCacheStore


def _settings(tmp_path) -> Settings:
    return Settings(
        detail_cache_path=str(tmp_path / "detail_cache.json"),
        detail_backfill_queue_path=str(tmp_path / "detail_queue.json"),
        detail_backfill_limit=10,
        detail_backfill_max_attempts=3,
        g0v_enabled=True,
    )


def _record(source: str) -> BidRecord:
    return BidRecord(
        title=f"{source}案",
        organization="測試機關",
        bid_date=date(2026, 5, 10),
        amount_raw="",
        amount_value=None,
        source=source,
        url=(
            "https://pcc-api.openfun.app/api/tender?unit_id=UNIT001&job_number=JOB001"
            if source == "g0v"
            else "https://web.pcc.gov.tw/tps/QueryTender/query/searchTenderDetail?pkPmsMain=AAA"
        ),
        metadata={"g0v_unit_id": "UNIT001", "g0v_job_number": "JOB001"} if source == "g0v" else {},
    )


def test_detail_backfill_g0v_success_updates_cache_and_removes_queue(monkeypatch, tmp_path) -> None:
    settings = _settings(tmp_path)
    store = DetailCacheStore(settings.detail_cache_path, settings.detail_backfill_queue_path, MagicMock())
    store.enqueue_missing([_record("g0v")])

    def _fake_enrich(record, _settings, _logger, session=None):
        record.budget_amount = "9,500,000元"
        record.amount_value = 9_500_000
        record.bid_deadline = "115/05/11 17:00"
        return True

    monkeypatch.setattr("core.detail_backfill.enrich_g0v_record", _fake_enrich)

    result = run_detail_backfill(settings, MagicMock())

    cache = json.loads((tmp_path / "detail_cache.json").read_text(encoding="utf-8"))
    queue = json.loads((tmp_path / "detail_queue.json").read_text(encoding="utf-8"))
    assert result.success_count == 1
    assert result.failed_count == 0
    assert next(iter(cache["entries"].values()))["budget_amount"] == "9,500,000元"
    assert queue["entries"] == {}


def test_detail_backfill_gov_failure_preserves_queue_and_increments_attempt(monkeypatch, tmp_path) -> None:
    settings = _settings(tmp_path)
    store = DetailCacheStore(settings.detail_cache_path, settings.detail_backfill_queue_path, MagicMock())
    store.enqueue_missing([_record("gov_pcc")])

    def _fake_enrich(records, _settings, _logger):
        records[0].metadata["detail_fetch_mode"] = "captcha"

    monkeypatch.setattr("core.detail_backfill.enrich_gov_detail", _fake_enrich)

    result = run_detail_backfill(settings, MagicMock())

    queue = json.loads((tmp_path / "detail_queue.json").read_text(encoding="utf-8"))
    entry = next(iter(queue["entries"].values()))
    assert result.success_count == 0
    assert result.failed_count == 1
    assert entry["failure_reason"] == "captcha"
    assert entry["attempt_counts"]["gov_pcc"] == 1


def test_detail_backfill_dry_run_does_not_mutate_queue(monkeypatch, tmp_path) -> None:
    settings = _settings(tmp_path)
    store = DetailCacheStore(settings.detail_cache_path, settings.detail_backfill_queue_path, MagicMock())
    store.enqueue_missing([_record("g0v")])
    before = (tmp_path / "detail_queue.json").read_text(encoding="utf-8")
    monkeypatch.setattr(
        "core.detail_backfill.enrich_g0v_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dry run must not fetch")),
    )

    result = run_detail_backfill(settings, MagicMock(), dry_run=True)

    assert result.selected_count == 1
    assert (tmp_path / "detail_queue.json").read_text(encoding="utf-8") == before
