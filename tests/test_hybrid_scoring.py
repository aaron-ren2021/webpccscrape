from datetime import date

from core.filters import filter_bids, screen_bids
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


def test_hybrid_screening_separates_high_boundary_and_excluded() -> None:
    records = [
        _bid("校務系統建置案", "某某大學", summary="校務系統升級與整合"),
        _bid("文件流轉", "某某大學", summary=""),
        _bid("桌椅採購", "某某大學", summary="教室桌椅汰換"),
    ]

    high_confidence, boundary, stats = screen_bids(records)

    assert [record.title for record in high_confidence] == ["校務系統建置案"]
    assert [record.title for record in boundary] == ["文件流轉"]
    assert stats["high_confidence"] == 1
    assert stats["boundary"] == 1
    assert stats["excluded_strong"] == 1

    assert high_confidence[0].metadata["filter_source"] == "keyword_high_confidence"
    assert boundary[0].metadata["filter_source"] == "keyword_boundary"
    assert high_confidence[0].metadata["keyword_confidence"] == "high_confidence"
    assert boundary[0].metadata["keyword_confidence"] == "boundary"


def test_filter_bids_keeps_boundary_cases_for_embedding() -> None:
    records = [
        _bid("校務系統建置案", "某某大學", summary="校務系統升級與整合"),
        _bid("文件流轉", "某某大學"),
        _bid("桌椅採購", "某某大學", summary="教室桌椅汰換"),
    ]

    output = filter_bids(records)

    assert [record.title for record in output] == ["校務系統建置案", "文件流轉"]
