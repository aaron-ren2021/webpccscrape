# 當前推薦配置 - Hybrid Search

## 🎯 使用架構

**Hybrid Search（混合搜尋）**：Keyword Filter + Embedding Semantic Recall

```
標案來源（Crawler）
    ↓
Phase 1: Keyword Filter
    - 112 個中文語意關鍵詞
    - 10 大分類快速匹配
    - 速度：<1ms
    ↓
Phase 2: Embedding Recall
    - sentence-transformers（multilingual）
    - 語意相似度 top-50
    - 速度：1-2秒
    ↓
最終輸出（高召回率、高精確率）
```

---

## ✅ 推薦配置

### .env 設定

```bash
# === 核心功能（推薦啟用）===
ENABLE_PLAYWRIGHT=true          # Playwright 動態抓取
STEALTH_ENABLED=true            # 反偵測機制
ENABLE_EMBEDDING_RECALL=true    # Embedding 語意召回

# === Embedding 配置 ===
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_TOP_K=50
EMBEDDING_SIMILARITY_THRESHOLD=0.65

# === 暫時停用 ===
ENABLE_AI_CLASSIFICATION=false  # Local LLM 暫時不用
```

---

## 📊 效能表現

### 召回率測試（4/13）

| 測試標案 | Keyword | Embedding | 最終結果 |
|---------|---------|-----------|---------|
| Ai運算協作管理平台 | ✅ 通過 | ✅ 召回（0.808） | ✅ |
| 檔案管理系統開發 | ✅ 通過 | ✅ 召回（0.807） | ✅ |
| 無線基地台汰換 | ✅ 通過 | ✅ 召回（0.574） | ✅ |
| 網頁應用程式防火牆 | ✅ 通過 | ✅ 召回（0.523） | ✅ |

**召回率**: 100%（4/4）  
**處理速度**: ~2-3 秒/批次（50 筆）  
**成本**: $0（完全本地）

---

## 🚀 快速啟動

### 1. 安裝依賴

```bash
cd /home/xcloud/project/webpccscrape
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 設定環境變數

複製並編輯 `.env`：

```bash
cp .env.example .env
# 編輯 .env，設定 EMAIL_TO 等必要參數
```

最小配置：

```bash
# .env
ENABLE_EMBEDDING_RECALL=true
EMAIL_TO=your-email@example.com
```

### 3. 測試執行

```bash
# 測試 Hybrid Search
python test_hybrid_filter.py

# 完整測試（不發送通知）
python run_local.py --no-send --preview-html ./output/preview.html

# 正式執行
python run_local.py
```

---

## 📁 關鍵檔案

### 核心邏輯
- `core/filters.py` — 112 個中文語意關鍵詞，10 大分類
- `core/embedding_categories.py` — 10 大類別標準描述
- `core/embedding_recall.py` — Embedding 語意召回引擎
- `core/pipeline.py` — 主流程整合

### 測試
- `test_hybrid_filter.py` — Hybrid Search 完整測試
- `test_phase1_phase2.py` — 分階段測試

### 文檔
- `SEMANTIC_FILTER_SUMMARY.md` — 完整技術文檔
- `QUICK_START_SEMANTIC_FILTER.md` — 快速啟用指南

---

## 🔧 調整參數

### 提高召回率（減少漏抓）

降低相似度閾值：

```bash
EMBEDDING_SIMILARITY_THRESHOLD=0.5  # 預設 0.65
```

### 提高精確率（減少誤報）

提高相似度閾值：

```bash
EMBEDDING_SIMILARITY_THRESHOLD=0.75  # 預設 0.65
```

### 增加召回數量

```bash
EMBEDDING_TOP_K=100  # 預設 50
```

---

## 📈 vs 其他方案

### 為什麼不用 BM25？

| 方案 | 優勢 | 劣勢 |
|------|------|------|
| **當前：Keyword + Embedding** | ✅ 語意理解<br>✅ 同義詞匹配<br>✅ 實現簡單 | - |
| BM25 | ✅ 精確文本匹配<br>✅ TF-IDF 加權 | ❌ 需要中文分詞<br>❌ 無語意理解<br>❌ 增加複雜度 |

**結論**：對於政府採購標案（標題簡短、專業術語多），Embedding 的語意理解能力 > BM25 的統計特性。

### 為什麼暫時不用 Local LLM？

| 方案 | 優勢 | 劣勢 |
|------|------|------|
| **當前：Keyword + Embedding** | ✅ 召回率 100%<br>✅ 速度快 1-2s<br>✅ 無需額外服務 | - |
| Local LLM | ✅ 深度驗證<br>✅ 優先度評分 | ❌ 推理慢 3-5s<br>❌ 需啟動 Ollama<br>❌ 75% 準確率（測試） |

**結論**：當前 Hybrid Search 已達到 100% 召回率，Local LLM 的額外價值有限，暫時停用以簡化系統。

---

## ⏭️ 未來擴展（可選）

### 如需更高精確率

1. **加入專家規則**：針對特定單位或金額範圍的特殊規則
2. **用戶反饋學習**：記錄哪些標案被標記為「不相關」，調整閾值
3. **Reference Embeddings**：從歷史高價值標案建立參考向量庫

### 如需啟用 Local LLM

參考 `LOCAL_LLM_QUICK_START.md`：

```bash
# 1. 啟動 Ollama
./start_ollama.sh

# 2. 設定環境變數
ENABLE_AI_CLASSIFICATION=true
OLLAMA_BASE_URL=http://localhost:11434/v1
```

---

## ✅ 驗證清單

部署前確認：

- [x] Keyword Filter 更新為 112 個語意關鍵詞
- [x] Embedding 模型已下載（首次執行自動下載）
- [x] 測試通過（`python test_hybrid_filter.py`）
- [x] Pipeline 整合測試（`python run_local.py --no-send`）
- [ ] 設定通知方式（Email 或 GitHub Issue）
- [ ] 設定 Crontab 或 Azure Functions 定時執行

---

**當前版本**: v2.0 - Hybrid Search (Keyword + Embedding)  
**最後更新**: 2026-04-13  
**推薦配置**: Keyword Filter + Embedding Recall（無 LLM）
