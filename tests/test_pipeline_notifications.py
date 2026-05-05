from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

from core.config import Settings
from core.models import BidRecord
from core.pipeline import _resolve_state_store, run_monitor
from storage.local_state_store import LocalJsonStateStore


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 4, 29, 12, 0, tzinfo=tz)


def _record(uid: str, bid_date: date | None, source: str = "gov_pcc") -> BidRecord:
    return BidRecord(
        title=f"測試案-{uid}",
        organization="某某大學",
        bid_date=bid_date,
        amount_raw="100萬",
        amount_value=1_000_000,
        source=source,
        url=f"https://example.com/{uid}",
        uid=uid,
    )


def test_run_monitor_includes_old_unnotified_records(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=False,
        dry_run=True,
    )

    old_record = _record(uid="old", bid_date=date(2026, 4, 1))
    today_record = _record(uid="today", bid_date=date(2026, 4, 24))

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [old_record, today_record])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **_kwargs: "<html></html>")
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)
    monkeypatch.setattr("core.pipeline.enrich_gov_detail", lambda _records, _settings, _logger: None)

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.new_count == 2
    assert result.notification_sent is True
    assert old_record.metadata["notification_candidate_reason"] == "catch_up_unnotified"
    logger.info.assert_any_call(
        "include_old_unnotified_bid",
        extra={
            "title": "測試案-old",
            "bid_date": "2026-04-01",
            "announcement_date": "",
            "reason": "catch_up_unnotified",
        },
    )


def test_run_monitor_logs_g0v_link_resolution_summary(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=True,
        dry_run=True,
        detail_cache_enabled=False,
    )

    g0v_record = _record(uid="g0v", bid_date=None, source="g0v")
    g0v_record.metadata = {
        "g0v_tender_api_url": "https://pcc-api.openfun.app/api/tender?unit_id=U&job_number=J",
    }

    def _fake_g0v_enrich(record, _settings, _logger, session=None):
        record.url = "https://web.pcc.gov.tw/tps/QueryTender/query/searchTenderDetail?pkPmsMain=AAA"
        record.metadata["g0v_link_resolution_state"] = "resolved_official"
        return False

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_g0v_bids", lambda _s, _l: [g0v_record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.enrich_gov_detail", lambda _records, _settings, _logger: None)
    monkeypatch.setattr("core.pipeline.enrich_g0v_record", _fake_g0v_enrich)
    monkeypatch.setattr("core.pipeline.build_session", lambda _settings: object())
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **_kwargs: "<html></html>")
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)

    run_monitor(settings=settings, logger=logger, persist_state=False)

    logger.info.assert_any_call(
        "g0v_link_resolution_summary",
        extra={
            "count": 1,
            "g0v_link_resolved_count": 1,
            "g0v_link_fallback_api_count": 0,
            "g0v_link_unresolved_count": 0,
        },
    )


def test_run_monitor_excludes_expired_deadlines_before_notifications(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=False,
        dry_run=True,
        github_token="token",
        github_repo="owner/repo",
        detail_cache_enabled=False,
    )
    expired_record = _record(uid="expired", bid_date=date(2026, 4, 29))

    def _fake_enrich(records, _settings, _logger):
        records[0].bid_deadline = "115/04/29 11:00"
        records[0].ai_priority = "high"

    class Store:
        def get_notified_keys(self):
            return set()

        def mark_notified(self, records):
            raise AssertionError("expired records must not be marked notified")

    monkeypatch.setattr("core.pipeline.datetime", FixedDateTime)
    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [expired_record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.enrich_gov_detail", _fake_enrich)
    monkeypatch.setattr("core.pipeline._resolve_state_store", lambda _settings, _logger: Store())
    monkeypatch.setattr(
        "core.pipeline.render_email_html",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("expired records must not render")),
    )
    monkeypatch.setattr(
        "core.pipeline.send_email",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("expired records must not send")),
    )
    monkeypatch.setattr(
        "core.pipeline.create_bid_issues",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("expired records must not create issues")),
    )

    result = run_monitor(settings=settings, logger=logger, persist_state=True)

    assert result.new_count == 0
    assert result.notification_sent is False
    logger.info.assert_any_call(
        "expired_bid_deadline_skipped",
        extra={
            "title": "測試案-expired",
            "deadline": "115/04/29 11:00",
            "source": "gov_pcc",
        },
    )
    logger.info.assert_any_call("no new bids")


def test_run_monitor_keeps_active_and_missing_deadline_records(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=False,
        dry_run=True,
        detail_cache_enabled=False,
    )
    expired_record = _record(uid="expired", bid_date=date(2026, 4, 29))
    active_record = _record(uid="active", bid_date=date(2026, 4, 29))
    missing_deadline_record = _record(uid="missing", bid_date=date(2026, 4, 29))
    rendered_records = []

    def _fake_enrich(records, _settings, _logger):
        records[0].bid_deadline = "115/04/29 11:00"
        records[1].bid_deadline = "115/04/29 13:00"
        records[2].bid_deadline = "無提供"

    def _fake_render_email_html(**kwargs):
        rendered_records.extend(kwargs["records"])
        return "<html></html>"

    monkeypatch.setattr("core.pipeline.datetime", FixedDateTime)
    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr(
        "core.pipeline.fetch_gov_bids",
        lambda _s, _l: [expired_record, active_record, missing_deadline_record],
    )
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.enrich_gov_detail", _fake_enrich)
    monkeypatch.setattr("core.pipeline.render_email_html", _fake_render_email_html)
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.new_count == 2
    assert result.notification_sent is True
    assert {record.title for record in rendered_records} == {"測試案-active", "測試案-missing"}


def test_run_monitor_skips_g0v_alias_already_notified_from_previous_day(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=True,
        dry_run=True,
    )
    already_sent = _record(uid="sent", bid_date=None, source="g0v")
    already_sent.announcement_date = date(2026, 4, 28)
    already_sent.metadata = {
        "g0v_unit_id": "UNIT001",
        "g0v_job_number": "JOB001",
    }

    class Store:
        def get_notified_keys(self):
            return {"source:g0v:unit001:job001"}

        def mark_notified(self, records):
            raise AssertionError("already-notified records must not be saved again")

    monkeypatch.setattr("core.pipeline.datetime", FixedDateTime)
    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_g0v_bids", lambda _s, _l: [already_sent])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.enrich_g0v_record", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("core.pipeline.build_session", lambda _settings: object())
    monkeypatch.setattr("core.pipeline._resolve_state_store", lambda _settings, _logger: Store())
    monkeypatch.setattr(
        "core.pipeline.render_email_html",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("already-notified records must not render")),
    )
    monkeypatch.setattr(
        "core.pipeline.send_email",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("already-notified records must not send")),
    )

    result = run_monitor(settings=settings, logger=logger, persist_state=True)

    assert result.new_count == 0
    assert result.notification_sent is False


def test_run_monitor_marks_unknown_date_as_catch_up(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=False,
        dry_run=True,
    )
    unknown_date_record = _record(uid="unknown", bid_date=None)
    unknown_date_record.bid_deadline = "115/05/10 17:00"
    rendered_records = []

    monkeypatch.setattr("core.pipeline.datetime", FixedDateTime)
    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [unknown_date_record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.enrich_gov_detail", lambda _records, _settings, _logger: None)
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **kwargs: rendered_records.extend(kwargs["records"]) or "<html></html>")
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.new_count == 1
    assert rendered_records[0].metadata["notification_candidate_reason"] == "catch_up_unknown_date"


def test_run_monitor_uses_detail_cache_without_inline_gov_enrich(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=False,
        dry_run=True,
        detail_cache_enabled=True,
    )
    record = _record(uid="cached", bid_date=date(2026, 4, 29))
    rendered_records = []

    class DetailStore:
        def apply_to_records(self, records):
            records[0].budget_amount = "NT$ 1,000,000 元"
            records[0].bid_deadline = "115/05/10 17:00"
            records[0].metadata["detail_cache_status"] = "hit"

        def enqueue_missing(self, records):
            raise AssertionError("persist_state=False must not enqueue")

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr(
        "core.pipeline.enrich_gov_detail",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("inline enrich disabled")),
    )
    monkeypatch.setattr("core.pipeline._resolve_detail_cache_store", lambda _settings, _logger: DetailStore())
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **kwargs: rendered_records.extend(kwargs["records"]) or "<html></html>")
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.notification_sent is True
    assert rendered_records[0].budget_amount == "NT$ 1,000,000 元"
    assert rendered_records[0].metadata["detail_cache_status"] == "hit"


def test_run_monitor_logs_queue_failure_without_failing_notification(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=False,
        dry_run=True,
        detail_cache_enabled=True,
    )
    record = _record(uid="queue", bid_date=date(2026, 4, 29))

    class NotifyStore:
        def get_notified_keys(self):
            return set()

        def mark_notified(self, records):
            return None

    class DetailStore:
        def apply_to_records(self, records):
            return {"hit": 0, "miss": len(records)}

        def enqueue_missing(self, records):
            raise OSError("disk full")

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline._resolve_state_store", lambda _settings, _logger: NotifyStore())
    monkeypatch.setattr("core.pipeline._resolve_detail_cache_store", lambda _settings, _logger: DetailStore())
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **_kwargs: "<html></html>")
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)

    result = run_monitor(settings=settings, logger=logger, persist_state=True)

    assert result.notification_sent is True
    assert result.errors == []
    logger.warning.assert_any_call("detail_backfill_queue_failed", extra={"error": "disk full"})


def test_resolve_state_store_uses_local_json_without_azure(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    store = _resolve_state_store(Settings(azure_storage_connection_string=""), MagicMock())

    assert isinstance(store, LocalJsonStateStore)
    assert store.path == tmp_path / "state/notified_state.json"
