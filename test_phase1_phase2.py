"""測試 Phase 1 (Keyword Expansion) 和 Phase 2 (Embedding Recall) 的效果。

使用 4 個已知遺漏的標案作為測試案例：
1. "Ai運算協作管理平台一式"
2. "檔案管理系統開發建置案"
3. "無線基地台汰換"
4. "網頁應用程式防火牆授權1式"
"""
from __future__ import annotations

from datetime import date

from core.models import BidRecord
from core.filters import filter_bids, has_theme_match
from core.embedding_recall import recall_bids_with_embedding


def create_test_bids() -> list[BidRecord]:
    """建立 4 個已知遺漏的測試標案 + 一些正常標案"""
    test_bids = [
        BidRecord(
            uid="test-1",
            source="test",
            title="Ai運算協作管理平台一式",
            organization="國立某某大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 3,000,000",
            amount_value=3000000.0,
            summary="建置 AI 運算協作管理平台，包含機器學習工作流管理",
            category="資訊服務",
            url="https://example.com/1",
        ),
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
            uid="test-3",
            source="test",
            title="無線基地台汰換",
            organization="國立某某科技大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 2,000,000",
            amount_value=2000000.0,
            summary="汰換校園無線基地台設備 50 台",
            category="財物類",
            url="https://example.com/3",
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
        # 加入一些正常標案（應該通過）
        BidRecord(
            uid="test-5",
            source="test",
            title="筆記型電腦採購",
            organization="某某大學資訊中心",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 5,000,000",
            amount_value=5000000.0,
            summary="採購筆記型電腦 100 台",
            category="財物類",
            url="https://example.com/5",
        ),
        BidRecord(
            uid="test-6",
            source="test",
            title="伺服器設備採購",
            organization="國立某某大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 10,000,000",
            amount_value=10000000.0,
            summary="採購高效能伺服器設備",
            category="財物類",
            url="https://example.com/6",
        ),
        # 加入一些不相關標案（應該被過濾）
        BidRecord(
            uid="test-7",
            source="test",
            title="辦公室傢俱採購",
            organization="某某大學總務處",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 1,000,000",
            amount_value=1000000.0,
            summary="採購辦公桌椅等傢俱",
            category="財物類",
            url="https://example.com/7",
        ),
    ]
    return test_bids


def test_phase1_keyword_expansion():
    """測試 Phase 1: Keyword Expansion"""
    print("=" * 80)
    print("Phase 1: Keyword Expansion 測試")
    print("=" * 80)
    
    test_bids = create_test_bids()
    print(f"\n總測試標案數: {len(test_bids)}")
    
    # 測試每個標案的關鍵字匹配
    print("\n個別標案關鍵字匹配測試:")
    print("-" * 80)
    for bid in test_bids:
        match = has_theme_match(bid.title, bid.summary, bid.category)
        status = "✓ 通過" if match else "✗ 未通過"
        print(f"{status} | {bid.title}")
    
    # 完整過濾流程
    filtered = filter_bids(test_bids)
    print(f"\n經過 filter_bids() 後: {len(filtered)} 筆")
    print("\n通過的標案:")
    print("-" * 80)
    for bid in filtered:
        print(f"  - {bid.title}")
        print(f"    單位: {bid.organization}")
        print(f"    標籤: {', '.join(bid.tags) if bid.tags else '無'}")
        print()
    
    # 檢查 4 個已知遺漏標案是否通過
    target_titles = [
        "Ai運算協作管理平台一式",
        "檔案管理系統開發建置案",
        "無線基地台汰換",
        "網頁應用程式防火牆授權1式",
    ]
    
    passed_count = sum(1 for bid in filtered if bid.title in target_titles)
    
    print("=" * 80)
    print(f"Phase 1 結果: 4 個已知遺漏標案中，{passed_count} 個通過篩選")
    print("=" * 80)
    
    return filtered


def test_phase2_embedding_recall():
    """測試 Phase 2: Embedding Recall"""
    print("\n\n")
    print("=" * 80)
    print("Phase 2: Embedding Recall 測試")
    print("=" * 80)
    
    # 先通過 Phase 1
    test_bids = create_test_bids()
    filtered = filter_bids(test_bids)
    
    print(f"\nPhase 1 後的候選數: {len(filtered)}")
    
    # 測試 embedding recall
    try:
        recalled = recall_bids_with_embedding(
            filtered,
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
            top_k=10,
            similarity_threshold=0.6,
        )
        
        print(f"Embedding recall 後: {len(recalled)} 筆")
        print("\n召回的標案（按相似度排序）:")
        print("-" * 80)
        for bid in recalled:
            similarity = bid.metadata.get("embedding_similarity", 0.0) if hasattr(bid, 'metadata') and bid.metadata else 0.0
            category_idx = bid.metadata.get("embedding_best_category_idx", -1) if hasattr(bid, 'metadata') and bid.metadata else -1
            print(f"  - {bid.title}")
            print(f"    相似度: {similarity:.3f} | 最佳匹配類別: {category_idx}")
            print()
        
        # 檢查 4 個已知遺漏標案
        target_titles = [
            "Ai運算協作管理平台一式",
            "檔案管理系統開發建置案",
            "無線基地台汰換",
            "網頁應用程式防火牆授權1式",
        ]
        
        recalled_count = sum(1 for bid in recalled if bid.title in target_titles)
        
        print("=" * 80)
        print(f"Phase 2 結果: 4 個已知遺漏標案中，{recalled_count} 個被召回")
        print("=" * 80)
        
    except ImportError as exc:
        print(f"⚠ Embedding 功能未啟用（缺少依賴）: {exc}")
    except Exception as exc:
        print(f"✗ Embedding recall 失敗: {exc}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 測試 Phase 1
    filtered = test_phase1_keyword_expansion()
    
    # 測試 Phase 2
    test_phase2_embedding_recall()
