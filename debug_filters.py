"""Debug script to understand why some bids are filtered out"""
from __future__ import annotations

from datetime import date

from core.models import BidRecord
from core.filters import is_educational_org, has_theme_match, filter_bids


# Test the 2 problematic bids
test_bids = [
    BidRecord(
        uid="test-2",
        source="test",
        title="檔案管理系統開發建置案",
        organization="某某市立高級中學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 1,500,000",
        amount_value=1500000.0,
        summary="開發校園檔案管理系統，含文件版本控制功能",
        category="資訊服務",
        url="https://example.com/2",
    ),
    BidRecord(
        uid="test-4",
        source="test",
        title="網頁應用程式防火牆授權1式",
        organization="某某縣立國民中學",
        bid_date=date(2026, 4, 13),
        amount_raw="NT$ 500,000",
        amount_value=500000.0,
        summary="購買網頁應用程式防火牆 WAF 授權一年份",
        category="資訊服務",
        url="https://example.com/4",
    ),
]

print("Debug: 檢查為什麼這 2 個標案未通過 filter_bids()")
print("=" * 80)

for bid in test_bids:
    print(f"\n標案: {bid.title}")
    print(f"  組織: {bid.organization}")
    
    # Check educational org
    is_edu = is_educational_org(bid.organization)
    print(f"  是否教育單位: {is_edu}")
    
    # Check theme match
    has_match = has_theme_match(bid.title, bid.summary, bid.category)
    print(f"  是否主題匹配: {has_match}")
    
    # Combined
    if is_edu and has_match:
        print(f"  ✓ 應該通過")
    else:
        print(f"  ✗ 不通過 (edu={is_edu}, theme={has_match})")

print("\n" + "=" * 80)
print("執行 filter_bids():")
filtered = filter_bids(test_bids)
print(f"結果: {len(filtered)} 筆通過")
for bid in filtered:
    print(f"  - {bid.title}")
