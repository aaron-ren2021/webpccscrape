from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

from core.config import Settings
from core.models import BidRecord
from core.pipeline import run_monitor


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
    logger.info.assert_any_call(
        "include_old_unnotified_bid",
        extra={"title": "測試案-old", "bid_date": "2026-04-01"},
    )


def test_run_monitor_logs_g0v_link_resolution_summary(monkeypatch) -> None:
    logger = MagicMock()
    settings = Settings(
        recent_days=1,
        g0v_enabled=True,
        dry_run=True,
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
