"""測試 Vita 提供的誤判/漏抓樣本"""

from core.models import BidRecord
from core.filters import filter_bids

# 誤判樣本（應該被排除）
FALSE_POSITIVES = [
    {
        "title": "脈克拉第二代無導線節律系統-雙腔+脈克拉親水性塗層血管導引鞘(或同等品)等4項案",
        "org": "台大醫院",
        "expected": False,
        "reason": "醫療設備-節律系統、導引鞘"
    },
    {
        "title": "曙光進階超音波乳化系統-前房超音波乳化儀手柄(或同等品)案",
        "org": "某大學附設醫院",
        "expected": False,
        "reason": "醫療設備-超音波乳化"
    },
    {
        "title": "115-117年度 Vyaire 呼吸器零件供應契約案",
        "org": "某醫學中心",
        "expected": False,
        "reason": "醫療設備-呼吸器"
    },
    {
        "title": "中華工程教育學會認證證書服務",
        "org": "中華工程教育學會",
        "expected": False,
        "reason": "認證服務非資訊採購"
    },
    {
        "title": "115年度資本門設備-數位儲存示波器、桌上型數位電錶、函數產生器 財物採購案",
        "org": "某科技大學",
        "expected": False,
        "reason": "電子量測設備-示波器、電錶、函數產生器"
    },
    {
        "title": "ICP-MS 感應耦合電漿質譜儀系統 1 套（B115000050 工程學院 AI 賦能計畫 - 採購三維光學顯微鏡）",
        "org": "某大學",
        "expected": False,
        "reason": "實驗室儀器-質譜儀、顯微鏡"
    },
    {
        "title": "32 通道無線腦波系統",
        "org": "某醫學院",
        "expected": False,
        "reason": "醫療/研究設備-腦波系統"
    },
]

# 漏抓樣本（應該被保留）
FALSE_NEGATIVES = [
    {
        "title": "Ai 運算協作管理平台一式",
        "org": "某大學",
        "expected": True,
        "reason": "AI運算平台、協作平台、管理平台"
    },
    {
        "title": "檔案管理系統開發建置案",
        "org": "某大學",
        "expected": True,
        "reason": "檔案管理、管理系統"
    },
    {
        "title": "無線基地台汰換",
        "org": "某高中",
        "expected": True,
        "reason": "網路設備-基地台"
    },
    {
        "title": "網頁應用程式防火牆授權 1 式",
        "org": "某科技大學",
        "expected": True,
        "reason": "資安設備-防火牆"
    },
]


def test_samples():
    print("=" * 80)
    print("測試誤判樣本（應該被排除）")
    print("=" * 80)
    
    false_positive_pass = 0
    false_positive_total = len(FALSE_POSITIVES)
    
    for sample in FALSE_POSITIVES:
        record = BidRecord(
            title=sample["title"],
            organization=sample["org"],
            bid_date=None,
            amount_raw="未公告",
            amount_value=None,
            source="test",
            url="",
        )
        
        result = filter_bids([record])
        is_kept = len(result) == 1
        # 誤判樣本的 expected=False 表示應該被排除（不保留）
        passed = is_kept == sample["expected"]
        
        status = "✓ PASS" if passed else "✗ FAIL"
        if passed:
            false_positive_pass += 1
        
        print(f"\n{status}")
        print(f"標題: {sample['title'][:60]}...")
        print(f"原因: {sample['reason']}")
        print(f"預期: {'保留' if sample['expected'] else '排除'}")
        print(f"實際: {'保留' if is_kept else '排除'}")
    
    print("\n" + "=" * 80)
    print("測試漏抓樣本（應該被保留）")
    print("=" * 80)
    
    false_negative_pass = 0
    false_negative_total = len(FALSE_NEGATIVES)
    
    for sample in FALSE_NEGATIVES:
        record = BidRecord(
            title=sample["title"],
            organization=sample["org"],
            bid_date=None,
            amount_raw="未公告",
            amount_value=None,
            source="test",
            url="",
        )
        
        result = filter_bids([record])
        is_kept = len(result) == 1
        passed = is_kept == sample["expected"]
        
        status = "✓ PASS" if passed else "✗ FAIL"
        if passed:
            false_negative_pass += 1
        
        print(f"\n{status}")
        print(f"標題: {sample['title'][:60]}...")
        print(f"原因: {sample['reason']}")
        print(f"預期: {'保留' if sample['expected'] else '排除'}")
        print(f"實際: {'保留' if is_kept else '排除'}")
    
    print("\n" + "=" * 80)
    print("測試總結")
    print("=" * 80)
    print(f"誤判樣本: {false_positive_pass}/{false_positive_total} 通過")
    print(f"漏抓樣本: {false_negative_pass}/{false_negative_total} 通過")
    print(f"總計: {false_positive_pass + false_negative_pass}/{false_positive_total + false_negative_total} 通過")
    
    success_rate = (false_positive_pass + false_negative_pass) / (false_positive_total + false_negative_total) * 100
    print(f"成功率: {success_rate:.1f}%")
    
    if success_rate == 100:
        print("\n🎉 所有測試通過！")
    else:
        print(f"\n⚠️  還有 {false_positive_total + false_negative_total - false_positive_pass - false_negative_pass} 個測試未通過")


if __name__ == "__main__":
    test_samples()
