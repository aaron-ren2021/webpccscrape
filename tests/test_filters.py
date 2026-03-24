from datetime import date

from core.filters import filter_bids, infer_unit_type, is_educational_org
from core.models import BidRecord


def _bid(title: str, org: str) -> BidRecord:
    return BidRecord(
        title=title,
        organization=org,
        bid_date=date(2026, 3, 24),
        amount_raw="100萬",
        amount_value=1_000_000,
        source="gov_pcc",
        url="https://example.com/bid",
    )


def test_is_educational_org() -> None:
    assert is_educational_org("臺北市教育局") is True
    assert is_educational_org("交通部") is False


def test_filter_bids_by_org_and_theme() -> None:
    records = [
        _bid("資訊設備採購案", "某某大學"),
        _bid("桌椅採購", "某某大學"),
        _bid("資訊服務維護", "某某公司"),
    ]
    output = filter_bids(records)
    assert len(output) == 1
    assert output[0].title == "資訊設備採購案"


def test_infer_unit_type() -> None:
    assert infer_unit_type("某某大學") == "大學"
    assert infer_unit_type("某某國中") == "國中小"
    assert infer_unit_type("某某高中") == "高中職"
