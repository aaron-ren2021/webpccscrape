from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from core.models import BidRecord

EDU_ORG_KEYWORDS = [
    "大學",
    "學院",
    "學校",
    "國小",
    "國中",
    "高中",
    "高職",
    "教育局",
    "教育處",
]

THEME_KEYWORDS = [
    "資訊設備",
    "資訊服務",
    "電腦設備",
    "筆記型電腦",
    "伺服器",
    "網路設備",
    "無線網路",
    "雲端",
    "資安",
    "軟體訂閱",
    "軟體",
    "機房",
]

THEME_TAG_MAP = {
    "資安": ["資安", "防火牆", "弱點", "防毒", "零信任"],
    "雲端": ["雲端", "cloud", "saas", "iaas", "paas"],
    "網路": ["網路", "無線", "交換器", "路由器", "wifi"],
    "軟體": ["軟體", "授權", "訂閱", "系統"],
    "機房": ["機房", "server room", "機櫃", "電力"],
}


def is_educational_org(org_name: str) -> bool:
    if not org_name:
        return False
    return any(keyword in org_name for keyword in EDU_ORG_KEYWORDS)


def has_theme_match(title: str, summary: str = "", category: str = "") -> bool:
    text = f"{title} {summary} {category}".lower()
    return any(keyword.lower() in text for keyword in THEME_KEYWORDS)


def infer_unit_type(org_name: str) -> str:
    if "大學" in org_name or "學院" in org_name:
        return "大學"
    if "國小" in org_name or "國中" in org_name:
        return "國中小"
    if "高中" in org_name or "高職" in org_name:
        return "高中職"
    if "教育局" in org_name or "教育處" in org_name:
        return "教育局處"
    if "學校" in org_name:
        return "學校"
    return "其他"


def infer_theme_tags(title: str, summary: str = "", category: str = "") -> list[str]:
    text = f"{title} {summary} {category}".lower()
    tags: list[str] = []
    for tag, keywords in THEME_TAG_MAP.items():
        if any(keyword.lower() in text for keyword in keywords):
            tags.append(tag)
    return tags


def filter_bids(records: Iterable[BidRecord]) -> list[BidRecord]:
    output: list[BidRecord] = []
    for record in records:
        if not is_educational_org(record.organization):
            continue
        if not has_theme_match(record.title, record.summary, record.category):
            continue
        record.unit_type = infer_unit_type(record.organization)
        record.tags = infer_theme_tags(record.title, record.summary, record.category)
        output.append(record)
    return output


def count_by_unit_type(records: Iterable[BidRecord]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record.unit_type] += 1
    return dict(counts)
