from __future__ import annotations

from core.high_amount import GOODS_CATEGORY, SERVICE_CATEGORY, evaluate_high_amount, infer_procurement_category
from core.models import BidRecord


def _record(**kwargs: object) -> BidRecord:
    base = dict(
        title="測試標案",
        organization="測試機關",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="g0v",
        url="https://example.com",
        category="",
        summary="",
        metadata={},
    )
    base.update(kwargs)
    return BidRecord(**base)


def test_service_high_and_gigantic_thresholds() -> None:
    high = evaluate_high_amount(_record(title="系統整合顧問服務案", amount_value=10_000_000))
    gigantic = evaluate_high_amount(_record(title="資訊服務長期維運案", amount_value=20_000_000))

    assert high.is_high_amount is True
    assert high.is_gigantic_amount is False
    assert high.procurement_category == SERVICE_CATEGORY
    assert gigantic.is_gigantic_amount is True


def test_goods_gigantic_threshold_is_one_hundred_million() -> None:
    high = evaluate_high_amount(_record(category="財物類", title="伺服器設備採購案", amount_value=10_000_000))
    not_gigantic = evaluate_high_amount(_record(category="財物類", title="設備採購案", amount_value=99_999_999))
    gigantic = evaluate_high_amount(_record(category="財物類", title="設備採購案", amount_value=100_000_000))

    assert high.is_high_amount is True
    assert not_gigantic.is_gigantic_amount is False
    assert gigantic.is_gigantic_amount is True
    assert gigantic.procurement_category == GOODS_CATEGORY


def test_p80_rule_upgrades_to_high_amount() -> None:
    decision = evaluate_high_amount(
        _record(amount_value=8_000_000, metadata={"won_p80_amount": 7_500_000})
    )

    assert decision.is_high_amount is True
    assert "P80" in "、".join(decision.reasons)


def test_strategic_customer_rule_uses_half_threshold() -> None:
    decision = evaluate_high_amount(
        _record(title="資訊設備採購案", amount_value=5_000_000, metadata={"customer_tier": "A級"})
    )

    assert decision.is_high_amount is True
    assert "策略客戶" in "、".join(decision.reasons)


def test_long_contract_rule_upgrades_even_without_annual_threshold() -> None:
    decision = evaluate_high_amount(_record(title="校務系統三年期維運服務案", amount_value=3_000_000))

    assert decision.is_high_amount is True
    assert "長約" in "、".join(decision.reasons)


def test_infer_procurement_category_prefers_service_terms() -> None:
    category = infer_procurement_category(_record(category="資訊服務", title="軟體授權及系統整合案"))

    assert category == SERVICE_CATEGORY
