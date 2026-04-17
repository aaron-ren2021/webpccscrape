from datetime import date

from core.filters import filter_bids, infer_unit_type, is_educational_org
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
        _bid("資訊設備採購案", "某某大學"),
        _bid("桌椅採購", "某某大學"),
        _bid("資訊服務維護", "某某公司"),
    ]
    output = filter_bids(records)
    assert len(output) == 1
    assert output[0].title == "資訊設備採購案"


def test_infer_unit_type() -> None:
    # === 大學（含科技大學）===
    assert infer_unit_type("某某大學") == "大學"
    assert infer_unit_type("國立臺灣科技大學") == "大學"
    assert infer_unit_type("某某學院") == "大學"
    
    # === 國中小 ===
    assert infer_unit_type("某某國中") == "國中小"
    assert infer_unit_type("某某國小") == "國中小"
    
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
