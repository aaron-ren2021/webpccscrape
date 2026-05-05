from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from core.models import BidRecord


SERVICE_HIGH_AMOUNT = 10_000_000.0
SERVICE_GIGANTIC_AMOUNT = 20_000_000.0
GOODS_HIGH_AMOUNT = 10_000_000.0
GOODS_GIGANTIC_AMOUNT = 100_000_000.0

SERVICE_CATEGORY = "勞務"
GOODS_CATEGORY = "財物"
UNKNOWN_CATEGORY = "其他"

_SERVICE_TERMS = ("勞務", "顧問", "委託", "維運", "服務", "系統整合", "資訊服務", "技術服務")
_GOODS_TERMS = ("財物", "軟體", "硬體", "設備", "儀器", "採購", "授權", "工作站", "伺服器", "電腦")
_STRATEGIC_TIERS = {"a", "a級", "a 級", "strategy", "strategic", "策略", "策略客戶"}


@dataclass(frozen=True, slots=True)
class HighAmountDecision:
    is_high_amount: bool
    is_gigantic_amount: bool
    amount: Optional[float]
    procurement_category: str
    high_threshold: float
    gigantic_threshold: float
    reasons: tuple[str, ...] = ()


def evaluate_high_amount(record: BidRecord, fallback_high_threshold: Optional[float] = None) -> HighAmountDecision:
    amount = record.amount_value
    procurement_category = infer_procurement_category(record)
    high_threshold, gigantic_threshold = _thresholds_for_category(procurement_category, fallback_high_threshold)

    reasons: list[str] = []
    if amount is not None and amount >= high_threshold:
        reasons.append(f"{procurement_category}金額達高金額門檻")

    if _matches_won_p80(record, amount):
        reasons.append("金額達近12個月得標案件P80")

    if _matches_strategic_customer(record, amount, high_threshold):
        reasons.append("A級/策略客戶且達標準門檻50%")

    if _matches_long_contract(record):
        reasons.append("3年以上長約")

    is_gigantic = amount is not None and amount >= gigantic_threshold
    if is_gigantic:
        reasons.append(f"{procurement_category}金額達巨額門檻")

    return HighAmountDecision(
        is_high_amount=bool(reasons) or is_gigantic,
        is_gigantic_amount=is_gigantic,
        amount=amount,
        procurement_category=procurement_category,
        high_threshold=high_threshold,
        gigantic_threshold=gigantic_threshold,
        reasons=tuple(reasons),
    )


def infer_procurement_category(record: BidRecord) -> str:
    text = " ".join(
        str(part)
        for part in (
            record.category,
            record.title,
            record.summary,
            record.metadata.get("procurement_category", "") if record.metadata else "",
        )
        if part
    )
    if any(term in text for term in _SERVICE_TERMS):
        return SERVICE_CATEGORY
    if any(term in text for term in _GOODS_TERMS):
        return GOODS_CATEGORY
    return UNKNOWN_CATEGORY


def _thresholds_for_category(category: str, fallback_high_threshold: Optional[float]) -> tuple[float, float]:
    if category == SERVICE_CATEGORY:
        return SERVICE_HIGH_AMOUNT, SERVICE_GIGANTIC_AMOUNT
    if category == GOODS_CATEGORY:
        return GOODS_HIGH_AMOUNT, GOODS_GIGANTIC_AMOUNT
    return (fallback_high_threshold or GOODS_HIGH_AMOUNT), GOODS_GIGANTIC_AMOUNT


def _matches_won_p80(record: BidRecord, amount: Optional[float]) -> bool:
    threshold = _metadata_float(record.metadata, "won_p80_amount", "p80_amount", "past_12m_won_p80")
    return amount is not None and threshold is not None and amount >= threshold


def _matches_strategic_customer(record: BidRecord, amount: Optional[float], high_threshold: float) -> bool:
    if amount is None or amount < high_threshold * 0.5:
        return False
    tier = _metadata_text(record.metadata, "customer_tier", "client_tier", "account_tier", "customer_grade")
    return tier.lower() in _STRATEGIC_TIERS


def _matches_long_contract(record: BidRecord) -> bool:
    years = _metadata_float(record.metadata, "contract_years", "term_years", "contract_duration_years")
    if years is not None and years >= 3:
        return True
    months = _metadata_float(record.metadata, "contract_months", "term_months", "contract_duration_months")
    if months is not None and months >= 36:
        return True
    text = f"{record.title} {record.summary}"
    return bool(re.search(r"(?:3|三)\s*年(?:期|以上)?|36\s*個?月", text))


def _metadata_text(metadata: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _metadata_float(metadata: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = metadata.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[^\d.]", "", str(value))
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None
