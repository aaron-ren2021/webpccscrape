from __future__ import annotations

from datetime import date

from core.formatter import _render_card, find_earliest_deadline, render_email_subject
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


def test_render_card_g0v_unsafe_link_shows_backup_api_links() -> None:
    record = _make_record(
        source="g0v",
        url="",
        metadata={
            "g0v_link_resolution_state": "unresolved",
            "g0v_tender_api_url": "https://pcc-api.openfun.app/api/tender?unit_id=U&job_number=J",
            "g0v_unit_api_url": "https://pcc-api.openfun.app/api/listbyunit?unit_id=U",
        },
    )

    html = _render_card(1, record)

    assert "查看詳情" not in html
    assert "來源 API" in html
    assert "機關 API" in html
    assert "資料連結暫不可用" in html


def test_render_card_g0v_official_link_uses_official_label() -> None:
    record = _make_record(
        source="g0v",
        url="https://web.pcc.gov.tw/tps/QueryTender/query/searchTenderDetail?pkPmsMain=AAA",
        metadata={
            "g0v_link_resolution_state": "resolved_official",
        },
    )

    html = _render_card(1, record)

    assert "查看詳情（官方頁）" in html


def test_render_card_g0v_fallback_api_link_uses_fallback_label() -> None:
    record = _make_record(
        source="g0v",
        url="https://pcc-api.openfun.app/api/tender?unit_id=U&job_number=J",
        metadata={
            "g0v_link_resolution_state": "fallback_api",
        },
    )

    html = _render_card(1, record)

    assert "來源 API（備援）" in html


def test_render_card_shows_bid_bond_amount_when_available() -> None:
    record = _make_record(bid_bond="450,000")

    html = _render_card(1, record)

    assert "450,000" in html
    assert "需繳納</div>" not in html


def test_find_earliest_deadline_sorts_roc_and_returns_ce() -> None:
    records = [
        _make_record(bid_deadline="115/04/27 17:00"),
        _make_record(bid_deadline="115/04/24"),
        _make_record(bid_deadline="無提供"),
    ]

    earliest = find_earliest_deadline(records)

    assert earliest == "2026-04-24"


def test_render_email_subject_uses_deadline_text() -> None:
    subject = render_email_subject(
        prefix="[教育資訊標案監控]",
        run_date=date(2026, 4, 24),
        count=3,
        earliest_deadline="2026-04-24",
    )

    assert subject == "[教育資訊標案監控] 2026-04-24 新增 3 筆｜最緊急截止 2026-04-24"
