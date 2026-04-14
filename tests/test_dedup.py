from datetime import date

from core.dedup import deduplicate_bids
from core.models import BidRecord


def _bid(
    source: str,
    title: str = "資訊設備採購",
    amount: float = 1000000.0,
    metadata: dict[str, object] | None = None,
) -> BidRecord:
    return BidRecord(
        title=title,
        organization="某某大學",
        bid_date=date(2026, 3, 24),
        amount_raw="100萬",
        amount_value=amount,
        source=source,
        url=f"https://example.com/{source}",
        metadata=metadata or {},
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


def test_dedup_preserves_g0v_lookup_metadata() -> None:
    bids = [
        _bid(
            "g0v",
            metadata={
                "g0v_unit_id": "3.79.56.3",
                "g0v_job_number": "11514",
                "g0v_tender_api_url": "https://pcc-api.openfun.app/api/tender?unit_id=3.79.56.3&job_number=11514",
            },
        ),
        _bid("gov_pcc"),
    ]

    output = deduplicate_bids(bids)
    assert len(output) == 1
    record = output[0]

    assert record.source == "gov_pcc"
    assert record.metadata["g0v_unit_id"] == "3.79.56.3"
    assert record.metadata["g0v_job_number"] == "11514"
    assert "api/tender" in str(record.metadata["g0v_tender_api_url"])
