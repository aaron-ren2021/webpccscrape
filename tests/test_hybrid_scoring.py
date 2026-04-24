from datetime import date

from core.filters import filter_bids, has_theme_match
from core.models import BidRecord


def _bid(title: str, org: str, summary: str = "", category: str = "") -> BidRecord:
    return BidRecord(
        title=title,
        organization=org,
        summary=summary,
        category=category,
        bid_date=date(2026, 4, 13),
        amount_raw="100萬",
        amount_value=1_000_000,
        source="gov_pcc",
        url="https://example.com/bid",
    )


def test_theme_match_separates_in_scope_and_excluded() -> None:
    records = [
        _bid("校務系統建置案", "某某大學", summary="校務系統升級與整合"),
        _bid("文件流轉", "某某大學", summary=""),
        _bid("桌椅採購", "某某大學", summary="教室桌椅汰換"),
    ]

    matched = [r.title for r in records if has_theme_match(r.title, r.summary, r.category)]
    excluded = [r.title for r in records if not has_theme_match(r.title, r.summary, r.category)]

    assert matched == ["校務系統建置案"]
    assert excluded == ["文件流轉", "桌椅採購"]


def test_filter_bids_keeps_boundary_cases_for_embedding() -> None:
    records = [
        _bid("校務系統建置案", "某某大學", summary="校務系統升級與整合"),
        _bid("文件流轉", "某某大學"),
        _bid("桌椅採購", "某某大學", summary="教室桌椅汰換"),
    ]

    output = filter_bids(records)

    assert [record.title for record in output] == ["校務系統建置案"]
