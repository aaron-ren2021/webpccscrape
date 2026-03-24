from datetime import date

from core.dedup import deduplicate_bids
from core.models import BidRecord


def _bid(source: str, title: str = "資訊設備採購", amount: float = 1000000.0) -> BidRecord:
    return BidRecord(
        title=title,
        organization="某某大學",
        bid_date=date(2026, 3, 24),
        amount_raw="100萬",
        amount_value=amount,
        source=source,
        url=f"https://example.com/{source}",
    )


def test_dedup_exact_prefers_gov() -> None:
    bids = [_bid("taiwanbuying"), _bid("gov_pcc")]
    output = deduplicate_bids(bids)
    assert len(output) == 1
    assert output[0].source == "gov_pcc"
    assert output[0].backup_source == "taiwanbuying"


def test_dedup_approx_for_near_amount_and_title() -> None:
    bids = [
        _bid("gov_pcc", title="資訊設備採購案", amount=1_000_000),
        _bid("taiwanbuying", title="資訊設備 採購案", amount=1_002_000),
    ]
    output = deduplicate_bids(bids)
    assert len(output) == 1
