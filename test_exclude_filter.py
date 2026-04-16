"""測試排除關鍵字過濾器"""
from __future__ import annotations

from datetime import date

from core.models import BidRecord
from core.filters import filter_bids, has_theme_match

# 應該被排除的標案
exclude_test_cases = [
    BidRecord(
        uid="test-exclude-1",
        source="test",
        title="115年度隱形防墜網建置採購案",
        organization="某某市立高級中學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 500,000",
        amount_value=500000.0,
        summary="校園安全防護設施",
        category="工程",
        url="https://example.com/1",
    ),
    BidRecord(
        uid="test-exclude-2",
        source="test",
        title="人文大樓局部教室VRV空調汰換案",
        organization="某某大學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 2,000,000",
        amount_value=2000000.0,
        summary="更換VRV變頻空調系統",
        category="工程",
        url="https://example.com/2",
    ),
    BidRecord(
        uid="test-exclude-3",
        source="test",
        title="教學錄音服務系統 詳規範：202603182730001 共35ST",
        organization="某某學校",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 800,000",
        amount_value=800000.0,
        summary="廣播錄音設備",
        category="設備",
        url="https://example.com/3",
    ),
    BidRecord(
        uid="test-exclude-4",
        source="test",
        title="北門校區氣冷式冰水主機汰換案",
        organization="國立某某大學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 3,000,000",
        amount_value=3000000.0,
        summary="汰換老舊冰水主機",
        category="工程",
        url="https://example.com/4",
    ),
    BidRecord(
        uid="test-exclude-5",
        source="test",
        title="114年度活動中心冷氣空調更新工程",
        organization="某某縣立國民中學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 1,500,000",
        amount_value=1500000.0,
        summary="活動中心冷氣更新",
        category="工程",
        url="https://example.com/5",
    ),
    BidRecord(
        uid="test-exclude-6",
        source="test",
        title="強化校園監視系統設備採購案",
        organization="某某市立高級中學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 600,000",
        amount_value=600000.0,
        summary="監視器材設備",
        category="設備",
        url="https://example.com/6",
    ),
    BidRecord(
        uid="test-exclude-7",
        source="test",
        title="免疫分析通用稀釋液(或同等品)",
        organization="某某大學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 200,000",
        amount_value=200000.0,
        summary="實驗室試劑耗材",
        category="耗材",
        url="https://example.com/7",
    ),
    BidRecord(
        uid="test-exclude-8",
        source="test",
        title="刑事鑑識大樓空調系統冷卻水塔風扇馬達汰換",
        organization="某某警察大學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 400,000",
        amount_value=400000.0,
        summary="冷卻水塔維護",
        category="工程",
        url="https://example.com/8",
    ),
]

# 應該通過的標案（對照組）
valid_test_cases = [
    BidRecord(
        uid="test-valid-1",
        source="test",
        title="校園網路設備更新案",
        organization="某某大學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 1,000,000",
        amount_value=1000000.0,
        summary="更換老舊網路交換器和無線基地台",
        category="資訊",
        url="https://example.com/v1",
    ),
    BidRecord(
        uid="test-valid-2",
        source="test",
        title="資安防火牆系統建置",
        organization="某某學校",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 800,000",
        amount_value=800000.0,
        summary="建置次世代防火牆",
        category="資訊",
        url="https://example.com/v2",
    ),
]

print("=" * 80)
print("測試排除關鍵字過濾器")
print("=" * 80)

print("\n【應該被排除的標案】")
print("-" * 80)
for bid in exclude_test_cases:
    has_match = has_theme_match(bid.title, bid.summary, bid.category)
    status = "✗ 正確排除" if not has_match else "✓ 錯誤通過（應排除）"
    print(f"{status}: {bid.title}")
    if has_match:
        print(f"  → 警告：此標案不應該通過過濾器！")

print("\n【應該通過的標案】")
print("-" * 80)
for bid in valid_test_cases:
    has_match = has_theme_match(bid.title, bid.summary, bid.category)
    status = "✓ 正確通過" if has_match else "✗ 錯誤排除（應通過）"
    print(f"{status}: {bid.title}")
    if not has_match:
        print(f"  → 警告：此標案應該通過過濾器！")

print("\n" + "=" * 80)
print("使用 filter_bids() 完整測試")
print("=" * 80)

all_test_cases = exclude_test_cases + valid_test_cases
filtered = filter_bids(all_test_cases)

print(f"\n輸入: {len(all_test_cases)} 筆標案")
print(f"輸出: {len(filtered)} 筆標案")
print(f"排除: {len(all_test_cases) - len(filtered)} 筆標案")

print("\n通過過濾的標案:")
for bid in filtered:
    print(f"  ✓ {bid.title}")

expected_pass = len(valid_test_cases)
actual_pass = len(filtered)
if actual_pass == expected_pass:
    print(f"\n✓ 測試通過！預期通過 {expected_pass} 筆，實際通過 {actual_pass} 筆")
else:
    print(f"\n✗ 測試失敗！預期通過 {expected_pass} 筆，實際通過 {actual_pass} 筆")


def test_exclude_keywords_block_non_it_bids() -> None:
    for bid in exclude_test_cases:
        assert has_theme_match(bid.title, bid.summary, bid.category) is False, bid.title


def test_valid_it_cases_still_pass_filter() -> None:
    filtered = filter_bids(exclude_test_cases + valid_test_cases)
    filtered_titles = {bid.title for bid in filtered}

    for bid in valid_test_cases:
        assert bid.title in filtered_titles, bid.title
