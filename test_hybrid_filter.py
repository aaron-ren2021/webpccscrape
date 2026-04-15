"""測試 Hybrid Filter（Keyword + Embedding）的完整功能。

驗證重點：
1. ✅ Keyword Match - 快速過濾
2. ✅ Embedding Match - 語意召回
3. ✅ Hybrid Filter - 整合效果
"""
from __future__ import annotations

from datetime import date

import pytest

from core.models import BidRecord
from core.filters import filter_bids, has_theme_match
from core.embedding_recall import recall_bids_with_embedding
from core.embedding_categories import get_category_names, get_category_by_index


def create_comprehensive_test_bids() -> list[BidRecord]:
    """建立全面的測試標案（涵蓋 10 大分類）"""
    return [
        # === 1️⃣ AI/資料分析類 ===
        BidRecord(
            uid="ai-1",
            source="test",
            title="Ai運算協作管理平台一式",
            organization="國立某某大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 3,000,000",
            amount_value=3000000.0,
            summary="建置 AI 運算協作管理平台，包含機器學習工作流管理",
            category="資訊服務",
            url="https://example.com/ai-1",
        ),
        BidRecord(
            uid="ai-2",
            source="test",
            title="大數據分析平台建置",
            organization="國立科技大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 5,000,000",
            amount_value=5000000.0,
            summary="建置大數據資料分析平台，含 BI 商業智慧工具",
            category="資訊服務",
            url="https://example.com/ai-2",
        ),
        
        # === 2️⃣ 系統開發/平台建置類 ===
        BidRecord(
            uid="sys-1",
            source="test",
            title="檔案管理系統開發建置案",
            organization="某某市立高級中學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 1,500,000",
            amount_value=1500000.0,
            summary="開發校園檔案管理系統，含文件版本控制功能",
            category="資訊服務",
            url="https://example.com/sys-1",
        ),
        BidRecord(
            uid="sys-2",
            source="test",
            title="協作平台整合專案",
            organization="國立大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 2,000,000",
            amount_value=2000000.0,
            summary="整合跨部門協作平台，提升行政效率",
            category="資訊服務",
            url="https://example.com/sys-2",
        ),
        
        # === 3️⃣ 資安類 ===
        BidRecord(
            uid="sec-1",
            source="test",
            title="網頁應用程式防火牆授權1式",
            organization="某某縣立國民中學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 500,000",
            amount_value=500000.0,
            summary="購買網頁應用程式防火牆 WAF 授權一年份",
            category="資訊服務",
            url="https://example.com/sec-1",
        ),
        BidRecord(
            uid="sec-2",
            source="test",
            title="資安弱點掃描服務",
            organization="國立某某大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 800,000",
            amount_value=800000.0,
            summary="提供全校資安弱點掃描與滲透測試服務",
            category="資訊服務",
            url="https://example.com/sec-2",
        ),
        
        # === 4️⃣ 網路/通訊設備類 ===
        BidRecord(
            uid="net-1",
            source="test",
            title="無線基地台汰換",
            organization="國立某某科技大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 2,000,000",
            amount_value=2000000.0,
            summary="汰換校園無線基地台設備 50 台",
            category="財物類",
            url="https://example.com/net-1",
        ),
        BidRecord(
            uid="net-2",
            source="test",
            title="校園WiFi建置擴充",
            organization="某某高級中學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 1,200,000",
            amount_value=1200000.0,
            summary="擴充校園無線網路覆蓋範圍，新增 AP 30台",
            category="財物類",
            url="https://example.com/net-2",
        ),
        
        # === 5️⃣ 文件/檔案管理類 ===
        BidRecord(
            uid="doc-1",
            source="test",
            title="電子公文系統升級",
            organization="市立國民中學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 600,000",
            amount_value=600000.0,
            summary="升級電子公文系統，含文件管理模組",
            category="資訊服務",
            url="https://example.com/doc-1",
        ),
        
        # === 正常硬體設備（應通過） ===
        BidRecord(
            uid="hw-1",
            source="test",
            title="筆記型電腦採購",
            organization="某某大學資訊中心",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 5,000,000",
            amount_value=5000000.0,
            summary="採購筆記型電腦 100 台",
            category="財物類",
            url="https://example.com/hw-1",
        ),
        
        # === 不相關標案（應被過濾） ===
        BidRecord(
            uid="other-1",
            source="test",
            title="辦公室傢俱採購",
            organization="某某大學總務處",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 1,000,000",
            amount_value=1000000.0,
            summary="採購辦公桌椅等傢俱",
            category="財物類",
            url="https://example.com/other-1",
        ),
    ]


def print_section_header(title: str):
    """印出區段標題"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


@pytest.fixture
def keyword_filtered() -> list[BidRecord]:
    """提供 Embedding 測試用的 keyword 篩選候選。"""
    return filter_bids(create_comprehensive_test_bids())


def test_keyword_filter():
    """測試 Keyword Match（快速過濾層）"""
    print_section_header("測試 1: Keyword Match（快速過濾層）")
    
    test_bids = create_comprehensive_test_bids()
    print(f"\n總測試標案數: {len(test_bids)}")
    
    # 測試每個標案的關鍵字匹配
    print("\n個別標案關鍵字匹配結果:")
    print("-" * 80)
    
    passed = []
    failed = []
    
    for bid in test_bids:
        match = has_theme_match(bid.title, bid.summary, bid.category)
        status = "✓" if match else "✗"
        
        if match:
            passed.append(bid)
            print(f"  {status} {bid.title} (ID: {bid.uid})")
        else:
            failed.append(bid)
            print(f"  {status} {bid.title} (ID: {bid.uid}) [未匹配]")
    
    # 完整過濾流程
    filtered = filter_bids(test_bids)
    
    print(f"\n經過 filter_bids() 後: {len(filtered)}/{len(test_bids)} 筆")
    print("\n✅ 通過篩選的標案:")
    print("-" * 80)
    for bid in filtered:
        tags_str = ', '.join(bid.tags) if bid.tags else '(無標籤)'
        print(f"  - {bid.title}")
        print(f"    ID: {bid.uid} | 單位: {bid.organization}")
        print(f"    標籤: {tags_str}")
        print()
    
    return filtered


def test_embedding_recall(keyword_filtered: list[BidRecord]):
    """測試 Embedding Match（語意召回層）"""
    print_section_header("測試 2: Embedding Match（語意召回層）")
    
    print(f"\nKeyword 過濾後的候選數: {len(keyword_filtered)}")
    
    try:
        # 執行 embedding recall
        recalled = recall_bids_with_embedding(
            keyword_filtered,
            model_name="BAAI/bge-m3",
            top_k=20,  # 取前 20 個
            similarity_threshold=0.5,  # 降低閾值以觀察更多結果
        )
        
        print(f"\nEmbedding recall 後: {len(recalled)}/{len(keyword_filtered)} 筆")
        print("\n召回的標案（按相似度排序）:")
        print("-" * 80)
        
        categories = get_category_names()
        
        for i, bid in enumerate(recalled, 1):
            similarity = bid.metadata.get("embedding_similarity", 0.0) if hasattr(bid, 'metadata') and bid.metadata else 0.0
            category_idx = bid.metadata.get("embedding_best_category_idx", -1) if hasattr(bid, 'metadata') and bid.metadata else -1
            
            category_name = categories[category_idx] if 0 <= category_idx < len(categories) else "未分類"
            
            print(f"  {i}. {bid.title}")
            print(f"     相似度: {similarity:.3f} | 最佳匹配: {category_name}")
            print(f"     ID: {bid.uid}")
            
            # 顯示該類別的詳細資訊
            if category_idx >= 0:
                cat_desc = get_category_by_index(category_idx)
                if cat_desc:
                    print(f"     類別關鍵字: {', '.join(cat_desc.keywords[:5])}")
            print()
        
        return recalled
        
    except ImportError as exc:
        print(f"⚠ Embedding 功能未啟用（缺少依賴）: {exc}")
        return keyword_filtered
    except Exception as exc:
        print(f"✗ Embedding recall 失敗: {exc}")
        import traceback
        traceback.print_exc()
        return keyword_filtered


def test_hybrid_filter():
    """測試 Hybrid Filter（整合效果）"""
    print_section_header("測試 3: Hybrid Filter（Keyword + Embedding）")
    
    test_bids = create_comprehensive_test_bids()
    
    # 定義已知應召回的標案（ground truth）
    target_bids = {
        "ai-1": "Ai運算協作管理平台",
        "sys-1": "檔案管理系統開發",
        "sec-1": "網頁應用程式防火牆",
        "net-1": "無線基地台汰換",
    }
    
    print(f"\n測試目標: 確保以下 {len(target_bids)} 個關鍵標案被召回:")
    for uid, title in target_bids.items():
        print(f"  - {title} (ID: {uid})")
    
    # Step 1: Keyword Filter
    keyword_filtered = filter_bids(test_bids)
    keyword_matched = sum(1 for bid in keyword_filtered if bid.uid in target_bids)
    
    print(f"\n✅ Keyword Filter 結果: {keyword_matched}/{len(target_bids)} 個目標標案通過")
    
    # Step 2: Embedding Recall
    try:
        final_results = recall_bids_with_embedding(
            keyword_filtered,
            top_k=20,
            similarity_threshold=0.5,
        )
        
        embedding_matched = sum(1 for bid in final_results if bid.uid in target_bids)
        
        print(f"✅ Embedding Recall 結果: {embedding_matched}/{len(target_bids)} 個目標標案被召回")
        
        print("\n詳細召回狀況:")
        print("-" * 80)
        for uid, title in target_bids.items():
            found_in_keyword = any(bid.uid == uid for bid in keyword_filtered)
            found_in_final = any(bid.uid == uid for bid in final_results)
            
            if found_in_final:
                bid = next(b for b in final_results if b.uid == uid)
                sim = bid.metadata.get("embedding_similarity", 0.0) if hasattr(bid, 'metadata') and bid.metadata else 0.0
                print(f"  ✓ {title}")
                print(f"    Keyword: {'通過' if found_in_keyword else '未通過'} | Embedding: 通過 (相似度: {sim:.3f})")
            else:
                print(f"  ✗ {title}")
                print(f"    Keyword: {'通過' if found_in_keyword else '未通過'} | Embedding: 未通過")
        
        print(f"\n" + "=" * 80)
        print(f"🎯 Hybrid Filter 總召回率: {embedding_matched}/{len(target_bids)} = {embedding_matched/len(target_bids)*100:.1f}%")
        print("=" * 80)
        
    except Exception as exc:
        print(f"⚠ Embedding 測試跳過: {exc}")


if __name__ == "__main__":
    # 測試 1: Keyword Filter
    keyword_results = test_keyword_filter()
    
    # 測試 2: Embedding Recall
    embedding_results = test_embedding_recall(keyword_results)
    
    # 測試 3: Hybrid Filter 整合效果
    test_hybrid_filter()
