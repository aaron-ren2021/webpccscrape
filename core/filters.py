from __future__ import annotations

from dataclasses import dataclass, field
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
    "中學",  # 涵蓋「高級中學」、「國民中學」等
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

# ============================================================================
# 語意分類關鍵字系統（Semantic Keyword Categories）
# ============================================================================
# 設計理念：Hybrid Filter = Keyword Match（快速過濾） + Embedding（語意召回）
# 每個分類包含：核心詞 + 同義詞 + 相關詞

# 1️⃣ AI / 資料分析類
AI_TERMS = [
    "ai", "人工智慧", "智慧", "分析", "資料", "數據",
    "決策", "預測", "模型", "大數據", "bi",  # BI = Business Intelligence
    "機器學習", "深度學習", "資料分析", "數據分析",
    "演算法", "運算", "資料科學",
]

# 2️⃣ 系統開發 / 平台類
SYSTEM_TERMS = [
    "系統", "平台", "建置", "開發", "整合",
    "管理系統", "資訊系統", "應用系統",
    "協作", "協作平台", "系統開發", "客製化",
    "專案", "導入", "雲端平台", "服務平台",
]

# 3️⃣ 資安類（優先擴充）
SECURITY_TERMS = [
    "資安", "防火牆", "waf", "入侵", "弱點",
    "資通安全", "防護", "資安設備",
    "防毒", "零信任", "ids", "ips",  # Intrusion Detection/Prevention System
    "滲透測試", "弱點掃描", "資安監控", "soc",  # Security Operations Center
    "加密", "認證", "網頁應用程式防火牆",
]

# 4️⃣ 網路設備類
NETWORK_TERMS = [
    "網路", "交換器", "基地台", "ap", "無線",
    "wifi", "網通", "通訊設備",
    "路由器", "無線網路", "網路設備",
    "光纖", "網卡", "乙太網路", "區域網路",
]

# 5️⃣ 文件 / 檔案管理類
DOCUMENT_TERMS = [
    "文件", "檔案", "文書", "電子公文",
    "文件管理", "檔案管理", "文管",
    "知識管理", "文檔", "公文系統",
]

# 6️⃣ 硬體設備類（補充）
HARDWARE_TERMS = [
    "資訊設備", "電腦設備", "筆記型電腦", "伺服器",
    "個人電腦", "pc", "主機", "工作站",
     "掃描器", "螢幕",
]

# 7️⃣ 軟體 / 授權類
SOFTWARE_TERMS = [
    "軟體", "授權", "訂閱", "軟體訂閱",
    "應用程式", "app", "應用軟體",
    "作業系統", "office", "防毒軟體",
]

# 8️⃣ 雲端 / 虛擬化類
CLOUD_TERMS = [
    "雲端", "cloud", "saas", "iaas", "paas",
    "虛擬化", "vm", "容器", "docker",
    "私有雲", "公有雲", "混合雲",
]

# 9️⃣ 儲存 / 備份類
STORAGE_TERMS = [
    "儲存", "備份", "nas", "san", "磁碟陣列",
    "資料庫", "database", "db", "sql",
    "儲存設備", "備份系統",
]

# 🔟 機房 / 基礎設施類
INFRA_TERMS = [
    "機房", "server room", "機櫃", "電力",
    "空調", "不斷電系統", "ups", "機房設備",
]

# ============================================================================
# 主題關鍵字（合併所有分類）
# ============================================================================
THEME_KEYWORDS = (
    AI_TERMS +
    SYSTEM_TERMS +
    SECURITY_TERMS +
    NETWORK_TERMS +
    DOCUMENT_TERMS +
    HARDWARE_TERMS +
    SOFTWARE_TERMS +
    CLOUD_TERMS +
    STORAGE_TERMS +
    INFRA_TERMS
)

# ============================================================================
# 排除關鍵字（非資訊設備，優先於主題匹配）
# ============================================================================
EXCLUDE_KEYWORDS = [
    # 建築/安全設施
    "防墜網", "圍籬", "欄杆", "鷹架", "帷幕", "隔間",
    "防水", "漏水", "補漏", "油漆", "粉刷", "地板", "天花板",
    
    # 空調/冷氣系統（包含各種變體）
    "空調", "冷氣", "冰水主機", "冷卻水塔", "冷氣空調",
    "vrv", "變頻空調", "分離式冷氣", "箱型冷氣",
    "冷媒", "風扇馬達", "送風機", "排風", "通風",
    
    # 監視系統（CCTV，非資訊系統監控）
    "監視系統", "監視器材", "監視設備", "cctv", "閉路電視",
    "監視鏡頭", "攝影監視",
    
    # 錄音/錄影設備（非數位教學系統）
    "錄音系統", "錄音設備", "錄音服務", "廣播系統",
    
    # 實驗室耗材/消耗品
    "稀釋液", "試劑", "實驗耗材", "化學品", "生物材料",
    "耗材", "消耗品", "碳粉", "墨水匣",

    # 醫療設備/耗材
    "節律", "節律器", "脈克拉", "導引鞘", "超音波乳化", "乳化儀",
    "呼吸器", "呼吸器零件",

    # 量測/實驗儀器
    "示波器", "函數產生器", "訊號產生器", "電源供應器", "電錶",
    "質譜儀", "感應耦合電漿", "icp-ms", "腦波",

    # 認證/證書服務
    "認證證書", "證書服務",
    
    # 電梯/升降設備
    "電梯", "升降設備", "升降機", "昇降機",
    
    # 消防設備
    "消防", "滅火器", "火警", "警報器", "偵煙",
    
    # 照明設備（排除智慧照明）
    "照明設備", "燈具", "路燈", "投射燈",
    
    # 水電/管線
    "給排水", "水電", "管線", "配管", "配線工程",
    "電力工程", "高壓", "變壓器",
    
    # 體育/遊樂設施
    "運動設施", "遊樂設施", "遊具", "球場", "跑道",
    
    # 其他非資訊設備
    "飲水機", "飲水設備", "淨水", "開飲機",
    "家具", "桌椅", "課桌椅", "辦公桌",
    "窗簾", "百葉窗", "捲簾", "布幕",
]

# ============================================================================
# 標籤映射（用於自動標記標案類別）
# ============================================================================
THEME_TAG_MAP = {
    "AI": AI_TERMS,
    "系統開發": SYSTEM_TERMS,
    "資安": SECURITY_TERMS,
    "網路": NETWORK_TERMS,
    "文件管理": DOCUMENT_TERMS,
    "硬體": HARDWARE_TERMS,
    "軟體": SOFTWARE_TERMS,
    "雲端": CLOUD_TERMS,
    "儲存": STORAGE_TERMS,
    "機房": INFRA_TERMS,
}

HIGH_CONFIDENCE_THRESHOLD = 2
LOW_CONFIDENCE_THRESHOLD = 0

CORE_THEME_GROUPS = [
    ("ai", ["ai", "人工智慧", "機器學習", "深度學習", "大數據", "資料分析", "數據分析", "資料科學"], 2),
    ("system", ["系統", "平台", "資訊系統", "應用系統", "管理系統", "校務系統", "教務系統", "學務系統", "公文系統"], 2),
    ("security", ["資安", "防火牆", "waf", "入侵", "弱點", "資通安全", "防護", "防毒", "零信任", "ids", "ips", "滲透測試", "弱點掃描", "資安監控", "soc", "加密", "認證", "網頁應用程式防火牆"], 2),
    ("network", ["網路", "交換器", "基地台", "ap", "無線", "wifi", "網通", "通訊設備", "路由器", "無線網路", "網路設備", "光纖", "網卡", "乙太網路", "區域網路"], 2),
    ("document", ["文件管理", "檔案管理", "電子公文", "知識管理", "文管", "文書", "公文系統"], 2),
    ("hardware", ["資訊設備", "電腦設備", "筆記型電腦", "伺服器", "個人電腦", "pc", "主機", "工作站", "掃描器", "螢幕"], 2),
    ("software", ["軟體", "授權", "訂閱", "軟體訂閱", "應用程式", "app", "應用軟體", "作業系統", "office", "防毒軟體"], 2),
    ("cloud", ["雲端", "cloud", "saas", "iaas", "paas", "虛擬化", "vm", "容器", "docker", "私有雲", "公有雲", "混合雲"], 2),
    ("storage", ["儲存", "備份", "nas", "san", "磁碟陣列", "資料庫", "database", "db", "sql", "儲存設備", "備份系統"], 2),
]

BOUNDARY_SINGLE_TERMS = [
    "智慧",
    "協作",
    "整合",
    "導入",
    "建置",
    "開發",
    "文件",
    "檔案",
]

CONTEXTUAL_TERMS = [
    ("管理", ["系統", "平台", "資訊系統", "應用系統", "管理系統", "文件管理", "檔案管理", "公文系統"]),
    ("文件", ["管理", "系統", "電子公文", "文書", "檔案", "公文"]),
    ("檔案", ["管理", "系統", "電子公文", "文書", "文件"]),
    ("教學", ["平台", "系統", "智慧", "校園", "教室", "學習"]),
    ("校園", ["平台", "系統", "智慧", "教學", "教室", "學習"]),
    ("學習", ["平台", "系統", "智慧", "教學", "校園", "教室"]),
    ("教室", ["平台", "系統", "智慧", "教學", "校園", "學習"]),
    ("協作", ["平台", "系統", "管理"]),
    ("整合", ["平台", "系統", "資訊系統", "應用系統", "雲端"]),
    ("導入", ["平台", "系統", "雲端"]),
    ("建置", ["平台", "系統", "雲端", "資訊系統"]),
    ("開發", ["平台", "系統", "文件", "檔案", "公文"]),
]

NEGATIVE_HINT_TERMS = ["維修", "耗材", "消耗品"]


@dataclass(slots=True)
class ThemeScreenResult:
    score: int
    decision: str
    matched_terms: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    org_signal: str = ""


def classify_theme_screen(org_name: str, title: str, summary: str = "", category: str = "") -> ThemeScreenResult:
    text = f"{title} {summary} {category}".lower()

    if not is_educational_org(org_name):
        return ThemeScreenResult(
            score=0,
            decision="excluded_strong",
            reasons=["org_not_educational"],
            org_signal="non_educational_org",
        )

    for keyword in EDU_ORG_EXCLUDE_KEYWORDS_STRONG:
        if keyword.lower() in text:
            return ThemeScreenResult(
                score=0,
                decision="excluded_strong",
                reasons=[f"strong_exclude:{keyword}"],
                org_signal="educational_org",
            )

    if any(keyword.lower() in text for keyword in EXCLUDE_KEYWORDS):
        return ThemeScreenResult(
            score=0,
            decision="excluded_strong",
            reasons=["strong_theme_exclude"],
            org_signal="educational_org",
        )

    score = 0
    matched_terms: list[str] = []
    reasons: list[str] = []

    for group_name, keywords, weight in CORE_THEME_GROUPS:
        matched = _first_matching_terms(text, keywords)
        if matched:
            score += weight
            matched_terms.extend(matched)
            reasons.append(f"core:{group_name}")

    for term in BOUNDARY_SINGLE_TERMS:
        if term.lower() in text:
            score += 1
            matched_terms.append(term)
            reasons.append(f"support:{term}")

    for term, context_terms in CONTEXTUAL_TERMS:
        if term.lower() not in text:
            continue
        if any(ctx.lower() in text for ctx in context_terms):
            score += 1
            matched_terms.append(term)
            reasons.append(f"context:{term}")

    if any(term in text for term in NEGATIVE_HINT_TERMS):
        score -= 1
        reasons.append("penalty:maintenance_or_consumables")

    decision = "high_confidence" if score >= HIGH_CONFIDENCE_THRESHOLD else "boundary" if score > LOW_CONFIDENCE_THRESHOLD else "excluded_low_score"
    return ThemeScreenResult(
        score=score,
        decision=decision,
        matched_terms=_unique_terms(matched_terms),
        reasons=reasons,
        org_signal="educational_org",
    )


def classify_theme_only(title: str, summary: str = "", category: str = "") -> ThemeScreenResult:
    text = f"{title} {summary} {category}".lower()

    for keyword in EDU_ORG_EXCLUDE_KEYWORDS_STRONG:
        if keyword.lower() in text:
            return ThemeScreenResult(score=0, decision="excluded_strong", reasons=[f"strong_exclude:{keyword}"])

    if any(keyword.lower() in text for keyword in EXCLUDE_KEYWORDS):
        return ThemeScreenResult(score=0, decision="excluded_strong", reasons=["strong_theme_exclude"])

    score = 0
    matched_terms: list[str] = []
    reasons: list[str] = []

    for group_name, keywords, weight in CORE_THEME_GROUPS:
        matched = _first_matching_terms(text, keywords)
        if matched:
            score += weight
            matched_terms.extend(matched)
            reasons.append(f"core:{group_name}")

    for term in BOUNDARY_SINGLE_TERMS:
        if term.lower() in text:
            score += 1
            matched_terms.append(term)
            reasons.append(f"support:{term}")

    for term, context_terms in CONTEXTUAL_TERMS:
        if term.lower() not in text:
            continue
        if any(ctx.lower() in text for ctx in context_terms):
            score += 1
            matched_terms.append(term)
            reasons.append(f"context:{term}")

    if any(term in text for term in NEGATIVE_HINT_TERMS):
        score -= 1
        reasons.append("penalty:maintenance_or_consumables")

    decision = "high_confidence" if score >= HIGH_CONFIDENCE_THRESHOLD else "boundary" if score > LOW_CONFIDENCE_THRESHOLD else "excluded_low_score"
    return ThemeScreenResult(score=score, decision=decision, matched_terms=_unique_terms(matched_terms), reasons=reasons)


def screen_bids(records: Iterable[BidRecord]) -> tuple[list[BidRecord], list[BidRecord], dict[str, int]]:
    high_confidence: list[BidRecord] = []
    boundary: list[BidRecord] = []
    stats: dict[str, int] = defaultdict(int)

    for record in records:
        result = classify_theme_screen(record.organization, record.title, record.summary, record.category)
        stats[result.decision] += 1

        _annotate_screen_result(record, result)

        if result.decision == "high_confidence":
            record.unit_type = infer_unit_type(record.organization)
            record.tags = infer_theme_tags(record.title, record.summary, record.category)
            high_confidence.append(record)
        elif result.decision == "boundary":
            record.unit_type = infer_unit_type(record.organization)
            record.tags = infer_theme_tags(record.title, record.summary, record.category)
            boundary.append(record)

    return high_confidence, boundary, dict(stats)


def _annotate_screen_result(record: BidRecord, result: ThemeScreenResult) -> None:
    record.metadata["keyword_score"] = result.score
    record.metadata["keyword_confidence"] = result.decision
    record.metadata["keyword_matched_terms"] = result.matched_terms
    record.metadata["keyword_reasons"] = result.reasons
    record.metadata["keyword_org_signal"] = result.org_signal
    if result.decision == "high_confidence":
        record.metadata["filter_source"] = "keyword_high_confidence"
    elif result.decision == "boundary":
        record.metadata["filter_source"] = "keyword_boundary"
    else:
        record.metadata["filter_source"] = "keyword_excluded"


def _first_matching_terms(text: str, keywords: list[str]) -> list[str]:
    matched: list[str] = []
    for keyword in keywords:
        if keyword.lower() in text and keyword not in matched:
            matched.append(keyword)
    return matched


def _unique_terms(terms: list[str]) -> list[str]:
    unique: list[str] = []
    for term in terms:
        if term not in unique:
            unique.append(term)
    return unique



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
    """檢查標案是否符合資訊設備主題。"""
    result = classify_theme_only(title, summary, category)
    return result.decision != "excluded_strong" and result.decision != "excluded_low_score"


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
    high_confidence, boundary, _ = screen_bids(records)
    return high_confidence + boundary


def count_by_unit_type(records: Iterable[BidRecord]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record.unit_type] += 1
    return dict(counts)
