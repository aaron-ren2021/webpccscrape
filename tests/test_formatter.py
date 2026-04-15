from __future__ import annotations

from datetime import date

from core.formatter import _render_card
from core.models import BidRecord


def _make_record(**kwargs: object) -> BidRecord:
    base = dict(
        title="測試標案",
        organization="測試機關",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="g0v",
        url="https://example.com",
        bid_deadline="",
        bid_opening_time="",
        budget_amount="",
        bid_bond="",
        tags=[],
    )
    base.update(kwargs)
    return BidRecord(**base)


def test_render_card_deadline_does_not_fallback_to_bid_date() -> None:
    record = _make_record(
        bid_date=date(2026, 4, 14),
        announcement_date=date(2026, 4, 14),
        bid_deadline="",
    )

    html = _render_card(1, record)

    assert "2026-04-14" not in html
    assert "無提供" in html

