from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from core.config import Settings
from core.models import BidRecord
from core.pipeline import run_monitor


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
