"""標案主題類別的標準描述文本，用於 embedding 語意相似度比對。

每個類別包含：
- name: 類別名稱
- description: 詳細描述文本（用於 embedding 編碼）
- keywords: 代表性關鍵字（輔助說明）

設計理念：與 filters.py 的語意分類對齊，用於 Hybrid Filter 的 embedding 層。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CategoryDescription:
    name: str
    description: str
    keywords: list[str]


# 10 大主題類別的標準描述（對齊 filters.py 的 THEME_TAG_MAP）
CATEGORY_DESCRIPTIONS = [
    CategoryDescription(
        name="AI/資料分析",
        description=(
            "人工智慧、機器學習、深度學習相關的運算平台或資料分析系統。"
            "包含 AI 模型訓練、推理服務、大數據分析平台、智慧校園系統、"
            "BI 商業智慧工具、資料科學平台、預測分析、決策支援系統、演算法運算。"
            "常見案例：AI 運算協作管理平台、智慧教學系統、大數據分析工具、"
            "資料分析平台、商業智慧系統、機器學習平台、智慧教室、校務分析儀表板、"
            "AI 賦能計畫相關系統。"
        ),
        keywords=["AI", "人工智慧", "機器學習", "大數據", "資料分析", "智慧", "預測", "演算法"],
    ),
    CategoryDescription(
        name="系統開發/平台建置",
        description=(
            "資訊系統開發、管理平台建置、應用系統整合專案。"
            "包含客製化系統開發、協作平台建置、資訊系統整合、"
            "雲端平台導入、服務平台開發、系統升級專案。"
            "常見案例：管理系統開發建置、協作平台建置、資訊系統整合、"
            "應用系統開發、平台導入專案、系統客製化開發、校務系統、教學平台、文件流轉平台。"
        ),
        keywords=["系統", "平台", "建置", "開發", "整合", "協作", "管理系統"],
    ),
    CategoryDescription(
        name="資安/網路安全",
        description=(
            "資訊安全設備或服務，包含防火牆、網頁應用程式防火牆（WAF）、"
            "入侵偵測與防禦系統（IDS/IPS）、防毒軟體、弱點掃描、滲透測試、"
            "資安健診、零信任網路架構（Zero Trust）、資安監控中心（SOC）、"
            "資通安全設備、加密系統、身份認證系統。"
            "常見案例：網頁應用程式防火牆授權、防火牆設備採購、資安弱點掃描、"
            "防毒軟體訂閱、零信任架構建置、IDS/IPS 系統、資安監控平台。"
        ),
        keywords=["資安", "防火牆", "WAF", "弱點", "防毒", "零信任", "IDS", "IPS", "資通安全"],
    ),
    CategoryDescription(
        name="網路/通訊設備",
        description=(
            "網路設備採購或汰換，包含無線網路基地台、Access Point（AP）、"
            "交換器、路由器、無線控制器、網路卡、光纖設備、網通設備。"
            "包含校園無線網路建置、網路設備升級、WiFi 覆蓋擴充、"
            "有線/無線網路整合專案、區域網路建置。"
            "常見案例：無線基地台汰換、AP 設備採購、網路交換器更新、"
            "校園 WiFi 建置、路由器設備、光纖網路建置、無線網路擴充。"
        ),
        keywords=["網路", "基地台", "AP", "交換器", "路由器", "WiFi", "無線", "網通"],
    ),
    CategoryDescription(
        name="文件/檔案管理系統",
        description=(
            "檔案管理系統、文件管理系統、知識管理系統的開發建置或採購。"
            "包含電子公文系統、文件版本控制、檔案儲存管理、知識庫建置、"
            "內容管理系統（CMS）、文檔協作平台、公文流程系統。"
            "常見案例：檔案管理系統開發建置、電子公文系統、文件管理平台、"
            "知識管理系統、文檔加密系統、文書處理系統、公文系統、文件流轉、校務文件管理。"
        ),
        keywords=["檔案", "文件", "管理系統", "知識管理", "電子公文", "文管", "文書"],
    ),
    CategoryDescription(
        name="硬體設備",
        description=(
            "一般資訊硬體設備採購，包含個人電腦、筆記型電腦、伺服器、"
            "工作站、辦公資訊設備。"
            "不包含：醫療設備（節律器、呼吸器、超音波乳化儀等）、"
            "實驗室量測儀器（示波器、電錶、函數產生器、質譜儀、顯微鏡等）。"
            "常見案例：筆記型電腦採購、桌上型電腦、伺服器設備、"
            "工作站採購、資訊設備汰換。"
        ),
        keywords=["筆記型電腦", "電腦", "伺服器", "PC", "工作站", "資訊設備"],
    ),
    CategoryDescription(
        name="軟體/授權訂閱",
        description=(
            "軟體授權採購、訂閱服務、應用程式授權。"
            "包含作業系統授權、Office 軟體、Adobe 創意雲訂閱、防毒軟體、"
            "應用軟體訂閱、軟體維護更新、軟體升級授權。"
            "常見案例：軟體授權採購、Office 365 訂閱、Adobe Creative Cloud 授權、"
            "防毒軟體授權、作業系統升級、應用程式授權、軟體維護服務。"
        ),
        keywords=["軟體", "授權", "訂閱", "應用程式", "Office", "防毒軟體", "Adobe"],
    ),
    CategoryDescription(
        name="雲端/虛擬化",
        description=(
            "雲端服務、虛擬化平台、容器化技術。"
            "包含 SaaS/IaaS/PaaS 服務、私有雲建置、公有雲服務、混合雲、"
            "虛擬化平台、VM 管理、容器平台（Docker/Kubernetes）。"
            "常見案例：雲端平台服務、虛擬化環境建置、容器平台導入、"
            "雲端服務訂閱、私有雲建置、雲端儲存服務。"
        ),
        keywords=["雲端", "Cloud", "虛擬化", "VM", "容器", "SaaS", "IaaS", "PaaS"],
    ),
    CategoryDescription(
        name="儲存/備份/資料庫",
        description=(
            "儲存設備、備份系統、資料庫系統。"
            "包含 NAS/SAN 儲存、磁碟陣列、備份軟體、資料庫授權、"
            "SQL 服務器、資料備份方案、儲存擴充。"
            "常見案例：NAS 儲存設備、備份系統建置、磁碟陣列採購、"
            "資料庫授權、SQL Server、備份軟體、儲存設備汰換。"
        ),
        keywords=["儲存", "備份", "NAS", "SAN", "磁碟陣列", "資料庫", "Database"],
    ),
    CategoryDescription(
        name="機房/基礎設施",
        description=(
            "機房設備、基礎設施建置。"
            "包含機房空調、機櫃設備、不斷電系統（UPS）、電力系統、"
            "機房監控、環境控制、機房整建工程。"
            "常見案例：機房設備採purchase、UPS 不斷電系統、機櫃採購、"
            "機房空調系統、電力設備、機房監控系統、機房整建。"
        ),
        keywords=["機房", "機櫃", "UPS", "不斷電系統", "機房設備"],
    ),
]


def get_category_texts() -> list[str]:
    """回傳所有類別描述文本（用於 embedding 編碼）"""
    return [cat.description for cat in CATEGORY_DESCRIPTIONS]


def get_category_names() -> list[str]:
    """回傳所有類別名稱"""
    return [cat.name for cat in CATEGORY_DESCRIPTIONS]


def get_category_by_index(index: int) -> CategoryDescription | None:
    """根據索引回傳類別描述"""
    if 0 <= index < len(CATEGORY_DESCRIPTIONS):
        return CATEGORY_DESCRIPTIONS[index]
    return None
