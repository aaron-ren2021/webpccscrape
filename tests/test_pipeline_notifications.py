from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from core.config import Settings
from core.models import BidRecord
from core.pipeline import _collect_notification_candidates


def _record(**kwargs: object) -> BidRecord:
    data = dict(
        title="測試案",
        organization="測試單位",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="g0v",
        url="https://example.com",
        uid="uid",
    )
    data.update(kwargs)
    return BidRecord(**data)


def test_collect_notification_candidates_skip_non_today_g0v() -> None:
    today = date(2026, 4, 15)
    settings = Settings(g0v_notify_today_only=True, recent_days=1)
    logger = MagicMock()

    g0v_yesterday = _record(uid="g0v-y", announcement_date=date(2026, 4, 14), source="g0v")
    g0v_today = _record(uid="g0v-t", announcement_date=today, source="g0v")
    gov_old = _record(uid="gov-old", source="gov_pcc", bid_date=date(2026, 4, 1))

    output = _collect_notification_candidates(
        [g0v_yesterday, g0v_today, gov_old],
        notified_keys=set(),
        today=today,
        settings=settings,
        logger=logger,
    )

    assert [item.uid for item in output] == ["g0v-t", "gov-old"]

