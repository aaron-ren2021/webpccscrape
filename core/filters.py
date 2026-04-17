from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from core.models import BidRecord

# 大專校院母集合 + 中小學 + 教育行政機構
EDU_ORG_INCLUDE_KEYWORDS = [
    "大學",
    "學院",
    "科技大學",
    "技術學院",
    "專科學校",
    "專科",
    "軍官學校",
    "國防大學",
    "國防醫學院",
    "學校",
    "國小",
    "國中",
    "高中",
    "高職",
    "教育局",
    "教育處",
]

# 醫療機構排除關鍵字（按優先級排序）
EDU_ORG_EXCLUDE_KEYWORDS_STRONG = [
    "附設醫院",
    "附屬醫院",
    "分院",
    "診所",
]

EDU_ORG_EXCLUDE_KEYWORDS_WEAK = [
    "醫院",
]

# 白名單（覆蓋排除規則）
EDU_ORG_WHITELIST_KEYWORDS = [
    "醫學院",
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
    "adobe",
    "creative cloud",
    "acrobat",
    "photoshop",
    "illustrator",
    "premiere",
    "lightroom",
    "indesign",
    "after effects",
    "ai設備",
    "ai 伺服器",
    "ai server",
    "gpu 伺服器",
    "gpu server",
    "ai運算伺服器",
    "ai運算設備",
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
    """
    多層邏輯篩選教育機構（按優先級）：
    1. IF 包含強排除關鍵字（附設/附屬醫院、分院、診所） → 強制排除
    2. ELSE IF 包含弱排除關鍵字（醫院） AND NOT 在白名單（醫學院） → 排除
    3. ELSE IF 包含教育機構關鍵字 → 保留
    4. ELSE → 排除
    
    範例：
    - 「台大醫院」→ 排除（醫院且非醫學院）
    - 「台大醫學院」→ 保留（白名單覆蓋醫院）
    - 「台大醫學院附設醫院」→ 排除（附設醫院強制排除）
    """
    if not org_name:
        return False
    
    # 第一層：強排除（附設/附屬醫院、分院、診所）→ 不管有沒有醫學院都排除
    if any(keyword in org_name for keyword in EDU_ORG_EXCLUDE_KEYWORDS_STRONG):
        return False
    
    # 第二層：弱排除（醫院）但白名單（醫學院）可覆蓋
    has_weak_exclude = any(keyword in org_name for keyword in EDU_ORG_EXCLUDE_KEYWORDS_WEAK)
    has_whitelist = any(keyword in org_name for keyword in EDU_ORG_WHITELIST_KEYWORDS)
    
    if has_weak_exclude and not has_whitelist:
        return False
    
    # 第三層：檢查是否為教育機構
    return any(keyword in org_name for keyword in EDU_ORG_INCLUDE_KEYWORDS)


def has_theme_match(title: str, summary: str = "", category: str = "") -> bool:
    text = f"{title} {summary} {category}".lower()
    return any(keyword.lower() in text for keyword in THEME_KEYWORDS)


def infer_unit_type(org_name: str) -> str:
    """識別教育機構類型（依優先順序）"""
    # 軍校識別（優先於大學/學院）
    if any(keyword in org_name for keyword in ["軍官學校", "國防大學", "國防醫學院"]):
        return "軍校"
    # 專科、技術學院（優先於大學/學院）
    if "專科" in org_name or "技術學院" in org_name:
        return "專科"
    # 科技大學、大學、學院（含醫學院）
    if "科技大學" in org_name or "大學" in org_name or "學院" in org_name:
        return "大學"
    # 國中小
    if "國小" in org_name or "國中" in org_name:
        return "國中小"
    # 高中職
    if "高中" in org_name or "高職" in org_name:
        return "高中職"
    # 教育局處
    if "教育局" in org_name or "教育處" in org_name:
        return "教育局處"
    # 泛稱學校
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
