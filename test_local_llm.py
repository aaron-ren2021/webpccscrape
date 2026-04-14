"""測試 Local LLM（Ollama + Qwen2.5:3b）的第三輪驗證功能。

驗證重點：
1. ✅ 深度驗證 - 確認標案是否真的相關
2. ✅ 優先度評分 - high/medium/low
3. ✅ Confidence 評分 - 0.0-1.0
4. ⏸️ 摘要生成 - 暫時關閉（validation_mode）
"""
from __future__ import annotations

import os
from datetime import date

from core.models import BidRecord
from core.ai_classifier import classify_bid, build_ai_clients
from core.config import Settings


def create_test_bids() -> list[BidRecord]:
    """建立測試標案（含真實案例和邊界案例）"""
    return [
        # ===  1️⃣ 明顯相關（應該 high priority）===
        BidRecord(
            uid="test-1",
            source="test",
            title="Ai運算協作管理平台一式",
            organization="國立臺灣大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 8,000,000",
            amount_value=8000000.0,
            summary="建置 AI 運算協作管理平台，包含機器學習工作流管理，支援大數據分析",
            category="資訊服務",
            url="https://example.com/1",
        ),
        
        # === 2️⃣ 明顯相關（high priority - 資安）===
        BidRecord(
            uid="test-2",
            source="test",
            title="網頁應用程式防火牆授權1式",
            organization="國立某某科技大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 1,200,000",
            amount_value=1200000.0,
            summary="購買網頁應用程式防火牆 WAF 授權三年份，含弱點掃描服務",
            category="資訊服務",
            url="https://example.com/2",
        ),
        
        # === 3️⃣ 中度相關（medium priority）===
        BidRecord(
            uid="test-3",
            source="test",
            title="無線基地台汰換",
            organization="某某市立高級中學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 500,000",
            amount_value=500000.0,
            summary="汰換校園無線基地台設備 30 台",
            category="財物類",
            url="https://example.com/3",
        ),
        
        # === 4️⃣ 邊界案例（可能相關，需要 LLM 判斷）===
        BidRecord(
            uid="test-4",
            source="test",
            title="智慧教室設備採購",
            organization="國立某某大學",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 3,000,000",
            amount_value=3000000.0,
            summary="採購智慧教室設備，包含觸控螢幕、投影設備、音響系統",
            category="財物類",
            url="https://example.com/4",
        ),
        
        # === 5️⃣ 不相關（應該被過濾）===
        BidRecord(
            uid="test-5",
            source="test",
            title="辦公室傢俱採購",
            organization="某某大學總務處",
            bid_date=date(2026, 4, 13),
            amount_raw="NT$ 800,000",
            amount_value=800000.0,
            summary="採購辦公桌椅、檔案櫃等傢俱",
            category="財物類",
            url="https://example.com/5",
        ),
    ]


def test_local_llm_validation():
    """測試 Local LLM 的深度驗證功能"""
    print("=" * 80)
    print("  測試 Local LLM（Ollama + Qwen2.5:3b）第三輪驗證")
    print("=" * 80)
    
    # 設定環境變數模擬配置
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434/v1"
    os.environ["OLLAMA_MODEL"] = "qwen2.5:3b"
    os.environ["USE_VALIDATION_MODE"] = "true"
    
    # 載入配置
    settings = Settings.from_env()
    
    # 建立 AI clients
    print("\n初始化 AI Clients...")
    openai_client, anthropic_client = build_ai_clients(settings)
    
    if not openai_client:
        print("❌ 無法連接 Ollama。請確認：")
        print("   1. Ollama 服務已啟動: ollama serve")
        print("   2. 模型已下載: ollama pull qwen2.5:3b")
        print("   3. Ollama 正在監聽 http://localhost:11434")
        return
    
    print("✅ Ollama 連接成功")
    print(f"   Base URL: {settings.ollama_base_url}")
    print(f"   Model: {settings.ollama_model}")
    print(f"   Validation Mode: {settings.use_validation_mode}")
    
    # 測試標案
    test_bids = create_test_bids()
    
    print(f"\n開始驗證 {len(test_bids)} 筆測試標案...")
    print("-" * 80)
    
    results = []
    
    for i, bid in enumerate(test_bids, 1):
        print(f"\n[{i}/{len(test_bids)}] {bid.title}")
        print(f"   單位: {bid.organization}")
        print(f"   金額: {bid.amount_raw}")
        
        try:
            classification = classify_bid(
                bid,
                openai_client=openai_client,
                anthropic_client=anthropic_client,
                model=settings.ollama_model,
                validation_mode=True,  # 使用驗證模式
            )
            
            # 顯示結果
            confidence_pct = classification.edu_score * 10  # 0-10 轉為 0-100%
            relevance = "✅ 相關" if classification.is_educational else "✗ 不相關"
            
            print(f"   結果: {relevance}")
            print(f"   信心度: {confidence_pct}%")
            print(f"   優先度: {classification.priority}")
            print(f"   理由: {classification.edu_reason[:60]}...")
            
            results.append({
                "bid": bid,
                "classification": classification,
            })
            
        except Exception as exc:
            print(f"   ❌ 驗證失敗: {exc}")
            import traceback
            traceback.print_exc()
    
    # 統計結果
    print("\n" + "=" * 80)
    print("  驗證結果統計")
    print("=" * 80)
    
    relevant_count = sum(1 for r in results if r["classification"].is_educational)
    high_priority = sum(1 for r in results if r["classification"].priority == "high")
    medium_priority = sum(1 for r in results if r["classification"].priority == "medium")
    low_priority = sum(1 for r in results if r["classification"].priority == "low")
    
    print(f"\n總測試數: {len(test_bids)}")
    print(f"判定相關: {relevant_count}/{len(test_bids)}")
    print(f"高優先度: {high_priority}")
    print(f"中優先度: {medium_priority}")
    print(f"低優先度: {low_priority}")
    
    print("\n詳細結果:")
    print("-" * 80)
    for r in results:
        bid = r["bid"]
        cls = r["classification"]
        status = "✅" if cls.is_educational else "✗"
        print(f"{status} {bid.title[:40]:<42} | {cls.priority:<6} | 信心: {cls.edu_score*10}%")
    
    # 驗證關鍵案例
    print("\n" + "=" * 80)
    print("  關鍵案例驗證")
    print("=" * 80)
    
    expected = {
        "test-1": ("相關", "high"),  # AI 平台
        "test-2": ("相關", "high"),  # WAF 資安
        "test-3": ("相關", "medium"),  # 無線基地台
        "test-5": ("不相關", "low"),  # 傢俱
    }
    
    for result in results:
        bid_id = result["bid"].uid
        if bid_id in expected:
            cls = result["classification"]
            exp_relevance, exp_priority = expected[bid_id]
            
            is_relevant = cls.is_educational
            actual_relevance = "相關" if is_relevant else "不相關"
            
            relevance_match = "✅" if actual_relevance == exp_relevance else "❌"
            priority_match = "✅" if cls.priority == exp_priority else "⚠️"
            
            print(f"\n{result['bid'].title[:50]}")
            print(f"   期望: {exp_relevance} | {exp_priority}")
            print(f"   實際: {actual_relevance} {relevance_match} | {cls.priority} {priority_match}")
            print(f"   信心度: {cls.edu_score*10}%")


if __name__ == "__main__":
    # 等待 Ollama 服務啟動
    import time
    print("等待 Ollama 服務啟動...")
    time.sleep(3)
    
    # 測試
    test_local_llm_validation()
