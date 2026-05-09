from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

from core.config import Settings
from core.models import BidRecord
from core.pipeline import merge_taiwanbuying_hints_into_gov_records, _resolve_state_store, run_monitor
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

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [old_record, today_record])
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


def test_run_monitor_uses_complete_detail_cache_without_inline_gov_enrich(monkeypatch) -> None:
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
            records[0].bid_bond = "免繳"
            records[0].bid_deadline = "115/05/10 17:00"
            records[0].bid_opening_time = "115/05/11 10:00"
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


def test_run_monitor_enriches_cache_miss_before_render(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=False,
        dry_run=True,
        detail_cache_enabled=True,
    )
    amount_record = _record(uid="missing-amount", bid_date=date(2026, 4, 29))
    amount_record.amount_raw = ""
    amount_record.amount_value = None
    amount_record.budget_amount = "已公開（金額見詳細頁）"
    amount_record.bid_bond = "免繳"
    amount_record.bid_deadline = "115/05/10 17:00"
    amount_record.bid_opening_time = "115/05/11 10:00"
    deadline_record = _record(uid="missing-deadline", bid_date=date(2026, 4, 29))
    deadline_record.bid_bond = "免繳"
    deadline_record.bid_deadline = "詳見連結"
    deadline_record.bid_opening_time = "115/05/11 10:00"
    rendered_records = []
    enriched_titles = []

    class DetailStore:
        def apply_to_records(self, records):
            for record in records:
                record.metadata["detail_cache_status"] = "miss"
            return {"hit": 0, "miss": len(records)}

        def enqueue_missing(self, records):
            raise AssertionError("persist_state=False must not enqueue")

    def _fake_enrich(records, _settings, _logger):
        enriched_titles.extend(record.title for record in records)
        for record in records:
            record.budget_amount = "NT$ 9,500,000 元"
            record.amount_raw = "NT$ 9,500,000 元"
            record.amount_value = 9_500_000.0
            record.bid_bond = "免繳"
            record.bid_deadline = "115/05/10 17:00"
            record.bid_opening_time = "115/05/11 10:00"

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [amount_record, deadline_record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.enrich_gov_detail", _fake_enrich)
    monkeypatch.setattr("core.pipeline._resolve_detail_cache_store", lambda _settings, _logger: DetailStore())
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **kwargs: rendered_records.extend(kwargs["records"]) or "<html></html>")
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.notification_sent is True
    assert enriched_titles == ["測試案-missing-amount", "測試案-missing-deadline"]
    assert {record.budget_amount for record in rendered_records} == {"NT$ 9,500,000 元"}
    assert {record.amount_value for record in rendered_records} == {9_500_000.0}


def test_run_monitor_failed_inline_fallback_preserves_existing_values(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=False,
        dry_run=True,
        detail_cache_enabled=True,
    )
    record = _record(uid="fallback-fails", bid_date=date(2026, 4, 29))
    record.amount_raw = "100萬"
    record.amount_value = 1_000_000
    record.budget_amount = "NT$ 1,000,000 元"
    record.bid_bond = "免繳"
    record.bid_deadline = "詳見連結"
    record.bid_opening_time = "115/05/11 10:00"
    rendered_records = []

    class DetailStore:
        def apply_to_records(self, records):
            records[0].metadata["detail_cache_status"] = "miss"
            return {"hit": 0, "miss": 1}

        def enqueue_missing(self, records):
            raise AssertionError("persist_state=False must not enqueue")

    def _failing_enrich(_records, _settings, _logger):
        raise RuntimeError("captcha")

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.enrich_gov_detail", _failing_enrich)
    monkeypatch.setattr("core.pipeline._resolve_detail_cache_store", lambda _settings, _logger: DetailStore())
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **kwargs: rendered_records.extend(kwargs["records"]) or "<html></html>")
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.notification_sent is True
    assert rendered_records[0].amount_raw == "100萬"
    assert rendered_records[0].amount_value == 1_000_000
    assert rendered_records[0].budget_amount == "NT$ 1,000,000 元"
    assert rendered_records[0].bid_bond == "免繳"
    assert rendered_records[0].bid_deadline == "詳見連結"
    assert rendered_records[0].bid_opening_time == "115/05/11 10:00"
    logger.warning.assert_any_call("gov_detail_enrich_failed", extra={"error": "captcha"})


def test_run_monitor_g0v_api_fills_amount_when_detail_cache_misses(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=True,
        dry_run=True,
        detail_cache_enabled=True,
    )
    record = _record(uid="g0v-miss", bid_date=date(2026, 4, 29), source="g0v")
    record.amount_raw = ""
    record.amount_value = None
    record.metadata = {
        "g0v_tender_api_url": "https://pcc-api.openfun.app/api/tender?unit_id=U&job_number=J",
    }
    rendered_records = []

    class DetailStore:
        def apply_to_records(self, records):
            records[0].metadata["detail_cache_status"] = "miss"
            return {"hit": 0, "miss": 1}

        def enqueue_missing(self, records):
            raise AssertionError("persist_state=False must not enqueue")

    def _fake_g0v_enrich(record, _settings, _logger, session=None):
        record.budget_amount = "9,500,000元"
        record.amount_raw = "9,500,000元"
        record.amount_value = 9_500_000.0
        record.bid_bond = "免繳"
        record.bid_deadline = "115/05/10 17:00"
        record.bid_opening_time = "115/05/11 10:00"
        record.metadata["g0v_link_resolution_state"] = "fallback_api"
        return True

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_g0v_bids", lambda _s, _l: [record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.enrich_g0v_record", _fake_g0v_enrich)
    monkeypatch.setattr("core.pipeline.build_session", lambda _settings: object())
    monkeypatch.setattr("core.pipeline._resolve_detail_cache_store", lambda _settings, _logger: DetailStore())
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **kwargs: rendered_records.extend(kwargs["records"]) or "<html></html>")
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.notification_sent is True
    assert rendered_records[0].budget_amount == "9,500,000元"
    assert rendered_records[0].amount_value == 9_500_000.0


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


def test_taiwanbuying_candidate_unmatched_does_not_notify(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(g0v_enabled=False, dry_run=True, detail_cache_enabled=False)
    candidate = _record(uid="tw", bid_date=date(2026, 4, 29), source="taiwanbuying")
    candidate.metadata = {
        "candidate_only": True,
        "category_hint": "computer_edu",
        "category_hint_source": "taiwanbuying",
    }

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [candidate])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("candidate must not render")))
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("candidate must not send")))

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.filtered_count == 0
    assert result.new_count == 0
    assert result.notification_sent is False


def test_taiwanbuying_hint_merge_preserves_gov_official_fields(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(g0v_enabled=False, dry_run=True, detail_cache_enabled=False)
    gov_record = _record(uid="gov", bid_date=date(2026, 4, 29), source="gov_pcc")
    gov_record.title = "資訊設備採購案"
    gov_record.organization = "某某大學"
    gov_record.amount_raw = "100萬"
    gov_record.amount_value = 1_000_000
    gov_record.url = "https://gov.example/bid"
    gov_record.metadata = {"tender_id": "A-001"}
    candidate = _record(uid="tw", bid_date=date(2026, 4, 29), source="taiwanbuying")
    candidate.title = "不同的台採標題"
    candidate.organization = "某某大學"
    candidate.amount_raw = "999萬"
    candidate.amount_value = 9_990_000
    candidate.url = "https://tw.example/bid"
    candidate.category = "電腦類"
    candidate.metadata = {
        "candidate_only": True,
        "category_hint": "computer_edu",
        "category_hint_source": "taiwanbuying",
        "tender_id": "A-001",
    }
    rendered_records = []

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [candidate])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [gov_record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **kwargs: rendered_records.extend(kwargs["records"]) or "<html></html>")
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: "dry_run")
    monkeypatch.setattr("core.pipeline.find_earliest_deadline", lambda _records: None)

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.notification_sent is True
    output = rendered_records[0]
    assert output.source == "gov_pcc"
    assert output.title == "資訊設備採購案"
    assert output.organization == "某某大學"
    assert output.amount_value == 1_000_000
    assert output.url == "https://gov.example/bid"
    assert output.metadata["taiwanbuying_hint_matched"] is True
    assert output.metadata["taiwanbuying_match_method"] == "tender_id_exact"
    assert output.metadata["taiwanbuying_candidate_url"] == "https://tw.example/bid"


def test_taiwanbuying_hint_does_not_merge_into_g0v() -> None:
    logger = MagicMock()
    candidate = _record(uid="tw", bid_date=date(2026, 4, 29), source="taiwanbuying")
    candidate.title = "資訊設備採購案"
    candidate.organization = "某某大學"
    candidate.category = "電腦類"
    candidate.metadata = {
        "candidate_only": True,
        "category_hint": "computer_edu",
        "tender_id": "A-001",
    }
    assert merge_taiwanbuying_hints_into_gov_records([], [candidate], logger) == []


def test_taiwanbuying_fuzzy_ambiguous_same_school_same_day_does_not_merge() -> None:
    logger = MagicMock()
    candidate = _record(uid="tw", bid_date=date(2026, 4, 29), source="taiwanbuying")
    candidate.title = "資訊設備採購案"
    candidate.organization = "某某大學"
    candidate.category = "電腦類"
    candidate.metadata = {"candidate_only": True, "category_hint": "computer_edu"}
    gov_a = _record(uid="a", bid_date=date(2026, 4, 29), source="gov_pcc")
    gov_a.title = "資訊設備採購案A"
    gov_b = _record(uid="b", bid_date=date(2026, 4, 29), source="gov_pcc")
    gov_b.title = "資訊設備採購案B"

    merged = merge_taiwanbuying_hints_into_gov_records([gov_a, gov_b], [candidate], logger)

    assert all("taiwanbuying_hint_matched" not in record.metadata for record in merged)
    logger.warning.assert_any_call(
        "taiwanbuying_hint_ambiguous",
        extra={
            "reason": "fuzzy_score_gap_too_small",
            "title": "資訊設備採購案",
            "organization": "某某大學",
            "url": "https://example.com/tw",
        },
    )


def test_taiwanbuying_hint_merge_logs_summary() -> None:
    logger = MagicMock()
    candidate = _record(uid="tw", bid_date=date(2026, 4, 29), source="taiwanbuying")
    candidate.title = "資訊設備採購案"
    candidate.organization = "某某大學"
    candidate.metadata = {"candidate_only": True, "category_hint": "computer_edu"}
    gov_record = _record(uid="gov", bid_date=date(2026, 4, 29), source="gov_pcc")
    gov_record.title = "資訊設備採購案"
    gov_record.organization = "某某大學"

    merge_taiwanbuying_hints_into_gov_records([gov_record], [candidate], logger)

    logger.info.assert_any_call(
        "taiwanbuying_hint_merge_summary",
        extra={
            "candidate_count": 1,
            "eligible_hint_count": 1,
            "matched_count": 1,
            "unmatched_count": 0,
            "fuzzy_min_score": 0.92,
            "fuzzy_min_gap": 0.03,
            "date_tolerance_days": 1,
        },
    )


def test_taiwanbuying_hint_fuzzy_threshold_can_be_tuned() -> None:
    logger = MagicMock()
    candidate = _record(uid="tw", bid_date=date(2026, 4, 29), source="taiwanbuying")
    candidate.title = "資訊設備採購案"
    candidate.organization = "某某大學"
    candidate.metadata = {"candidate_only": True, "category_hint": "computer_edu"}
    gov_record = _record(uid="gov", bid_date=date(2026, 4, 29), source="gov_pcc")
    gov_record.title = "資訊設備採購案-第一期"
    gov_record.organization = "某某大學"

    merge_taiwanbuying_hints_into_gov_records(
        [gov_record],
        [candidate],
        logger,
        fuzzy_min_score=0.99,
    )
    assert "taiwanbuying_hint_matched" not in gov_record.metadata

    merge_taiwanbuying_hints_into_gov_records(
        [gov_record],
        [candidate],
        logger,
        fuzzy_min_score=0.80,
    )
    assert gov_record.metadata["taiwanbuying_hint_matched"] is True
    assert gov_record.metadata["taiwanbuying_match_method"] == "org_title_fuzzy_date"


def test_candidate_only_record_blocked_before_formatter_and_send(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(g0v_enabled=False, dry_run=True, detail_cache_enabled=False)
    record = _record(uid="bad", bid_date=date(2026, 4, 29), source="gov_pcc")
    record.metadata = {"candidate_only": True}

    monkeypatch.setattr("core.pipeline.fetch_taiwanbuying_bids", lambda _s, _l: [])
    monkeypatch.setattr("core.pipeline.fetch_gov_bids", lambda _s, _l: [record])
    monkeypatch.setattr("core.pipeline.filter_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.deduplicate_bids", lambda records: list(records))
    monkeypatch.setattr("core.pipeline.render_email_html", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("candidate_only must not render")))
    monkeypatch.setattr("core.pipeline.send_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("candidate_only must not send")))

    result = run_monitor(settings=settings, logger=logger, persist_state=False)

    assert result.new_count == 0
    assert result.notification_sent is False
    logger.warning.assert_any_call(
        "candidate_only_record_blocked_before_notification",
        extra={
            "title": "測試案-bad",
            "organization": "某某大學",
            "source": "gov_pcc",
            "url": "https://example.com/bad",
        },
    )


def test_resolve_state_store_uses_local_json_without_azure(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    store = _resolve_state_store(Settings(azure_storage_connection_string=""), MagicMock())

    assert isinstance(store, LocalJsonStateStore)
    assert store.path == tmp_path / "state/notified_state.json"
