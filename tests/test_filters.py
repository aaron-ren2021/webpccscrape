from datetime import date

from core.filters import (
    has_theme_match,
    has_education_project_context,
    filter_bids,
    infer_theme_tags,
    infer_unit_type,
    is_educational_org,
)
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
    # === 教育局 ===
    assert is_educational_org("臺北市教育局") is True
    
    # === 非教育機構 ===
    assert is_educational_org("交通部") is False
    
    # === 大專校院（含科技大學）===
    assert is_educational_org("國立臺灣大學") is True
    assert is_educational_org("國立臺灣科技大學") is True
    assert is_educational_org("國立臺北科技大學") is True
    
    # === 專科學校 ===
    assert is_educational_org("國立臺北護理健康大學專科部") is True
    assert is_educational_org("德霖技術學院") is True
    assert is_educational_org("某某專科學校") is True
    
    # === 軍校 ===
    assert is_educational_org("國防大學") is True
    assert is_educational_org("國防醫學院") is True
    assert is_educational_org("陸軍軍官學校") is True

    # === 國民中小學 ===
    assert is_educational_org("雲林縣立東明國民中學") is True
    assert is_educational_org("新竹市東區關埔國民小學") is True
    
    # === 醫療機構排除（關鍵測試）===
    assert is_educational_org("臺大醫院") is False
    assert is_educational_org("成大醫院") is False
    assert is_educational_org("中國醫藥大學附設醫院") is False
    assert is_educational_org("國立台灣大學醫學院附設醫院") is False
    assert is_educational_org("某某分院") is False
    assert is_educational_org("某某診所") is False
    
    # === 醫學院保留（白名單覆蓋）===
    assert is_educational_org("國立陽明交通大學醫學院") is True
    assert is_educational_org("台大醫學院") is True
    assert is_educational_org("中國醫藥大學醫學院") is True


def test_filter_bids_by_org_and_theme() -> None:
    records = [
        _bid("AI運算伺服器採購案", "某某大學"),
        _bid("桌椅採購", "某某大學"),
        _bid("資訊服務維護", "某某公司"),
    ]
    output = filter_bids(records)
    assert len(output) == 1
    assert output[0].title == "AI運算伺服器採購案"


def test_ai_priority_core_cases() -> None:
    core_cases = [
        ("國立臺北科技大學", "AI運算伺服器", True),
        ("中臺科技大學", "GPU算力管理平台", True),
        ("國立中正大學", "115年度次世代防火牆採購案", True),
        ("某某大學", "資訊管理系統建置", True),
    ]

    for _org, title, expected in core_cases:
        assert has_theme_match(title) is expected, title


def test_false_positive_regressions_are_excluded() -> None:
    regression_cases = [
        ("臺北市國語實驗國民小學", "114學年度參與深耕國際教育獎輔導與認證學校出國交流"),
        ("教育部", "教育部補助學校評鑑認證作業"),
        ("某某大學", "證照輔導課程委外服務案"),
        ("某某高中", "校務評鑑認可作業採購案"),
        ("新北市立金山高級中學", "114學年度第2期高中完免入學挹注計畫資本門財物(解剖顯微鏡、顯微鏡專用影像擷取裝置)採購案"),
        ("國立臺灣科技大學", "電力品質量測與分析系統1套"),
    ]

    for _org, title in regression_cases:
        assert has_theme_match(title) is False, title


def test_boundary_cases_stay_available_for_embedding() -> None:
    boundary_cases = [
        ("臺中市立文山國民中學", "MFA 多因子驗證設備採購"),
    ]

    for _org, title in boundary_cases:
        assert has_theme_match(title) is False, title


def test_support_terms_require_core_or_context() -> None:
    assert has_theme_match("建置") is False
    assert has_theme_match("建置校務系統") is True

    assert has_theme_match("智慧") is False
    assert has_theme_match("智慧校園管理平台") is True

    assert has_theme_match("文件") is False
    assert has_theme_match("電子公文管理系統") is True


def test_app_only_matches_full_phrase() -> None:
    assert has_theme_match("校務 app 建置") is False
    assert has_theme_match("校務行動應用建置") is False


def test_non_it_maintenance_is_excluded_but_it_maintenance_kept() -> None:
    assert has_theme_match("校園冷氣維修") is False
    assert has_theme_match("系統維護服務案") is False
    assert has_theme_match("網路維護採購案") is False
    assert has_theme_match("資安維護服務") is True


def test_engineering_activity_teaching_aids_are_excluded() -> None:
    excluded_cases = [
        ("某某大學", "校舍整修工程採購"),
        ("某某高中", "雙語教學教具採購"),
        ("某某國中", "科學營隊活動委外案"),
    ]
    for _org, title in excluded_cases:
        assert has_theme_match(title) is False, title


def test_auth_related_it_cases_remain_in_scope() -> None:
    positive_cases = [
        ("某某大學", "單一登入系統建置", False),
        ("某某大學", "MFA 多因子驗證系統", False),
        ("某某大學", "校園帳號整合與權限管理平台", True),
        ("某某大學", "身分識別與存取管理 IAM 平台", False),
    ]

    for _org, title, expected in positive_cases:
        assert has_theme_match(title) is expected, title


def test_tag_inference_avoids_ascii_substring_false_positives() -> None:
    assert "AI" not in infer_theme_tags("Apple平板電腦 iPad Air 13吋")
    assert "機房" in infer_theme_tags("GPU 伺服器採購案")


def test_infer_unit_type() -> None:
    # === 大學（含科技大學）===
    assert infer_unit_type("某某大學") == "大學"
    assert infer_unit_type("國立臺灣科技大學") == "大學"
    assert infer_unit_type("某某學院") == "大學"
    
    # === 國中小 ===
    assert infer_unit_type("某某國中") == "國中小"
    assert infer_unit_type("某某國小") == "國中小"
    assert infer_unit_type("雲林縣立東明國民中學") == "國中小"
    assert infer_unit_type("新竹市東區關埔國民小學") == "國中小"
    
    # === 高中職 ===
    assert infer_unit_type("某某高中") == "高中職"
    assert infer_unit_type("某某高職") == "高中職"
    
    # === 專科（優先於大學/學院）===
    assert infer_unit_type("國立臺北護理健康大學專科部") == "專科"
    assert infer_unit_type("德霖技術學院") == "專科"
    assert infer_unit_type("某某專科學校") == "專科"
    
    # === 軍校（優先順序最高，在大學/學院之前）===
    assert infer_unit_type("國防大學") == "軍校"
    assert infer_unit_type("國防醫學院") == "軍校"
    assert infer_unit_type("陸軍軍官學校") == "軍校"
    
    # === 教育局處 ===
    assert infer_unit_type("臺北市教育局") == "教育局處"


def test_edge_cases_for_medical_institutions() -> None:
    """測試醫療機構的邊緣案例"""
    # === 只有「醫院」沒有「大學」關鍵字 → 排除 ===
    assert is_educational_org("榮民總醫院") is False
    assert is_educational_org("長庚醫院") is False
    
    # === 大學醫院（醫院為主體）→ 排除 ===
    assert is_educational_org("台大醫院") is False
    assert is_educational_org("成大醫院") is False
    
    # === 大學醫學院（教學單位）→ 保留 ===
    assert is_educational_org("台大醫學院") is True
    assert is_educational_org("成大醫學院") is True
    
    # === 附設/附屬醫院（強制排除，即使有醫學院）===
    assert is_educational_org("國立台灣大學醫學院附設醫院") is False
    assert is_educational_org("中國醫藥大學附屬醫院") is False
    
    # === 分院、診所（強制排除）===
    assert is_educational_org("台大醫院新竹分院") is False
    assert is_educational_org("某某牙醫診所") is False
    
    # === 國防醫學院（軍校醫學院，教學單位）→ 保留 ===
    assert is_educational_org("國防醫學院") is True
    
    # === 只有「醫學院」在名稱中 → 保留 ===
    assert is_educational_org("陽明醫學院") is True


def test_direct_and_conditional_pass_rules_for_workstation_and_hci() -> None:
    records = [
        _bid("OVS-ES 教育版授權採購案", "某某大學"),
        _bid("超融合設備採購案", "某某大學"),
        _bid("工作站採購案", "某某大學"),
        _bid("GPU 工作站採購案", "某某大學"),
        _bid("人工智慧工作站採購案", "某某大學"),
        _bid("高效能工作站採購案", "某某大學"),
        _bid("虛擬化工作站採購案", "某某大學"),
    ]

    output_titles = {record.title for record in filter_bids(records)}
    assert "OVS-ES 教育版授權採購案" in output_titles
    assert "超融合設備採購案" in output_titles
    assert "工作站採購案" not in output_titles
    assert "GPU 工作站採購案" in output_titles
    assert "人工智慧工作站採購案" in output_titles
    assert "高效能工作站採購案" in output_titles
    assert "虛擬化工作站採購案" in output_titles


def test_user_reported_missed_bids_are_now_included() -> None:
    records = [
        _bid("115年全校電腦採購", "臺中市立臺中工業高級中等學校"),
        _bid("114學年度東明國中AI科技教育：未來領航者社群計畫資本門設備採購", "雲林縣立東明國民中學"),
        _bid("新竹市115-118年度中小學微軟教育整合應用工具三年授權及防毒軟體採購", "新竹市東區關埔國民小學"),
        _bid("大王國中--115年臺東縣國民中小學網路優化-匯聚交換器設備及無線網路基地臺(AP)採購案", "臺東縣政府"),
        _bid("SAS統計軟體全校授權租賃3年", "國立屏東科技大學"),
        _bid("VR虛擬實境設備等設備", "建國科技大學"),
    ]

    output_titles = {record.title for record in filter_bids(records)}
    assert len(output_titles) == len(records)
    for record in records:
        assert record.title in output_titles


def test_education_project_context_for_non_edu_org() -> None:
    assert (
        has_education_project_context(
            "大王國中--115年臺東縣國民中小學網路優化-匯聚交換器設備及無線網路基地臺(AP)採購案"
        )
        is True
    )
    assert has_education_project_context("某縣政府道路鋪面改善工程") is False
