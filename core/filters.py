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

# 第一層：嚴格過濾詞（只要命中即視為教育資訊標案高相關）
STRICT_THEME_KEYWORDS = [
    "校務系統",
    "學務系統",
    "防火牆",
    "弱點掃描",
    "滲透測試",
    "fortigate",
    "tenable",
    "office 365",
    "power bi",
    "copilot 教育版",
    "備份系統",
    "虛擬化",
    "gpu 伺服器",
]

# 第二層：寬詞（不直接放行，提供 embedding/標籤等後續流程使用）
BROAD_THEME_KEYWORDS = [
    "軟體",
    "雲端",
    "網路設備",
    "資訊服務",
    "機房",
    "openai",
]

# 第三層：內部營運詞（僅供路由/商機分類，不作為是否放行依據）
INTERNAL_BIZ_KEYWORDS = [
    "標案投標",
    "履約",
    "驗收",
    "發票對帳",
    "標案監測",
]

# 排除關鍵字：非資訊設備案件（醫療、實驗室、量測儀器）
EXCLUDE_THEME_KEYWORDS = [
    # 醫療設備
    "節律系統",
    "心律調節器",
    "超音波乳化",
    "超音波掃描",
    "超音波探頭",
    "呼吸器",
    "呼吸照護",
    "麻醉機",
    "腦波系統",
    "心電圖",
    "血壓計",
    "血糖機",
    "醫療耗材",
    "手術器械",
    "導引鞘",
    "導管",
    # 實驗室儀器
    "質譜儀",
    "光譜儀",
    "色譜儀",
    "顯微鏡",
    "離心機",
    "培養箱",
    # 電子量測設備
    "示波器",
    "電錶",
    "三用電錶",
    "函數產生器",
    "信號產生器",
    "頻譜分析儀",
    # 其他非資訊服務
    "認證證書服務",
    "認證服務",
    "檢驗服務",
]

# 穩定版：保守放行詞（先維持上線穩定）
STABLE_THEME_KEYWORDS = [
    "資訊設備",
    "資訊服務",
    "電腦設備",
    "筆記型電腦",
    "伺服器",
    "網路設備",
    "無線網路",
    "基地台",
    "access point",
    "雲端",
    "資安",
    "軟體訂閱",
    "軟體",
    "機房",
    # 系統類
    "管理系統",
    "管理平台",
    "檔案管理",
    # AI/運算類
    "ai 運算",
    "gpu 運算",
    "運算平台",
    # 新增 Adobe 相關
    "adobe",
    "acrobat",
    "photoshop",
]

THEME_TAG_MAP = {
    "資安": ["資安", "防火牆", "弱點", "防毒", "零信任", "fortigate", "tenable", "rms", "ims", "ad 漏洞", "災難復原"],
    "雲端": ["雲端", "cloud", "saas", "iaas", "paas", "azure", "m365", "office 365", "onedrive", "teams", "outlook", "vm", "pve", "虛擬化"],
    "網路": ["網路", "無線", "交換器", "路由器", "wifi"],
    "軟體": [
        "軟體",
        "授權",
        "訂閱",
        "系統",
        "copilot",
        "copilot studio",
        "copilot 教育版",
        "openai",
        "a9 openai",
        "adobe cct",
        "adobe",      # 新增
        "acrobat",    # 新增
        "photoshop",  # 新增
        "github enterprise server",
        "power bi",
        "fabric",
        "m365 cowork",
        "segma",
        "向量資料庫",
        "圖片解析",
        "虛擬人像",
        "雲端帳單",
        "自動化申請表單",
    ],
    "機房": ["機房", "server room", "機櫃", "電力", "gpu 伺服器", "server", "jetson agx orin"],
    "內部營運": INTERNAL_BIZ_KEYWORDS,
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
    """
    主題匹配邏輯（兩階段）：
    1. 先檢查排除關鍵字（醫療、實驗室、量測設備） → 命中則排除
    2. 再檢查包含關鍵字（資訊設備相關） → 命中則保留
    """
    text = f"{title} {summary} {category}".lower()
    
    # 第一階段：排除非資訊設備
    if any(keyword.lower() in text for keyword in EXCLUDE_THEME_KEYWORDS):
        return False
    
    # 第二階段：包含資訊設備關鍵字
    return any(keyword.lower() in text for keyword in STABLE_THEME_KEYWORDS)


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
