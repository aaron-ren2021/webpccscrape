# 快速啟用 Semantic Filter

## 🚀 一鍵啟用

### 1. 安裝依賴

```bash
cd /home/xcloud/project/webpccscrape
source venv/bin/activate
pip install sentence-transformers scikit-learn
```

### 2. 啟用 Embedding Recall

編輯 `.env` 或 `local.settings.json`，新增：

```bash
# 啟用 embedding 語意召回
ENABLE_EMBEDDING_RECALL=true

# 可選配置（使用預設值即可）
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_TOP_K=50
EMBEDDING_SIMILARITY_THRESHOLD=0.65
```

### 3. 測試執行

```bash
# 完整測試（推薦）
python test_hybrid_filter.py

# 本地執行pipeline（不發送通知）
python run_local.py --no-send --preview-html ./output/preview.html

# 正常執行（會發送通知）
python run_local.py
```

---

## 📊 驗證結果

執行 `test_hybrid_filter.py` 應該看到：

```
================================================================================
🎯 Hybrid Filter 總召回率: 4/4 = 100.0%
================================================================================
```

---

## ⚙️ 配置說明

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `ENABLE_EMBEDDING_RECALL` | `false` | 是否啟用 embedding 語意召回 |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-transformers 模型名稱 |
| `EMBEDDING_TOP_K` | `50` | 召回前 K 個候選 |
| `EMBEDDING_SIMILARITY_THRESHOLD` | `0.65` | 最低相似度閾值（0-1） |

---

## 🔧 調整召回率/精確率

### 提高召回率（減少漏抓）

降低相似度閾值：

```bash
EMBEDDING_SIMILARITY_THRESHOLD=0.5  # 降低到 0.5
```

### 提高精確率（減少誤報）

提高相似度閾值：

```bash
EMBEDDING_SIMILARITY_THRESHOLD=0.7  # 提高到 0.7
```

---

## 🐛 問題排查

### Q1: ImportError: No module named 'sentence_transformers'

```bash
pip install sentence-transformers scikit-learn
```

### Q2: Embedding 模型下載很慢

首次執行會自動下載 50MB 模型，之後會快取。可預先下載：

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

### Q3: 想要關閉 Embedding 功能

```bash
ENABLE_EMBEDDING_RECALL=false
```

系統會自動回退到純 Keyword Filter。

---

## 📈 效能影響

| 階段 | 時間 | 說明 |
|------|------|------|
| Keyword Filter | <1ms | 幾乎無影響 |
| Embedding Encode | 1-2s | 首次載入模型（之後快取） |
| Similarity Calc | 20-50ms/筆 | CPU 環境，批次處理更快 |

**總體影響**: 每日執行時間增加約 2-3 秒（可接受）

---

## ✅ 驗證清單

- [ ] 安裝依賴 `sentence-transformers` 和 `scikit-learn`
- [ ] 設定 `ENABLE_EMBEDDING_RECALL=true`
- [ ] 執行 `python test_hybrid_filter.py` 驗證
- [ ] 檢查召回率是否達到 100%
- [ ] 執行 `python run_local.py --no-send --preview-html ./output/preview.html`
- [ ] 檢查 preview.html 中的標案是否符合預期
- [ ] 正式啟用前，先觀察 1-2 天的結果

---

**需要協助？** 查看 `SEMANTIC_FILTER_SUMMARY.md` 取得完整文件。
