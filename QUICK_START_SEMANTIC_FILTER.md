# QUICK_START_SEMANTIC_FILTER

## 1) 啟用 BGE-M3 語意召回

在 `.env`（或對應部署環境變數）設定：

```bash
ENABLE_EMBEDDING_RECALL=true
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_TOP_K=30
EMBEDDING_SIMILARITY_THRESHOLD=0.68
```

可選參數（A/B 與監控）：

```bash
EMBEDDING_ENABLE_AB_TEST=false
EMBEDDING_AB_MODEL=
EMBEDDING_AB_SIMILARITY_THRESHOLD=0.65
EMBEDDING_AB_TOP_K=30
EMBEDDING_TIMEOUT_WARN_MS=3000
EMBEDDING_MEMORY_WARN_MB=2048
EMBEDDING_ZERO_RECALL_WARN_DAYS=3
```

## 2) 安裝依賴

```bash
cd /home/xcloud/project/webpccscrape
source venv/bin/activate
pip install -r requirements.txt
```

## 3) 先跑本地驗證（不發通知）

```bash
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state
```

建議檢查 `logs/cron.log` 事件：

- `keyword_screen_distribution`
- `embedding_recall_pipeline_step`
- `embedding_recall_done`
- `local_run_finished`

## 4) 測試與回歸

```bash
pytest -q test_hybrid_filter.py test_phase1_phase2.py
```

## 5) Threshold 調整流程

只在下列候選值比較：

- `0.65`
- `0.68`（基準）
- `0.70`

調整順序：

1. 先用 `0.68` 蒐集 3-7 天生產 log。
2. 比較命中率、誤判率、boundary -> recall 轉換率。
3. 測試集通過率不得下降。
4. 若誤判與漏判拉扯，維持 `0.68`。

## 6) A/B Sidecar（不影響正式通知）

開啟：

```bash
EMBEDDING_ENABLE_AB_TEST=true
EMBEDDING_AB_MODEL=BAAI/bge-m3
EMBEDDING_AB_SIMILARITY_THRESHOLD=0.65
```

觀測事件：

- `embedding_ab_dataset_row`
- `embedding_ab_row`
- `embedding_ab_summary`

固定比對欄位：

- `uid`
- `title`
- `keyword_confidence`
- `embedding_similarity`
- `embedding_best_category`
- `decision_source`
- `model_name`
- `threshold`

## 7) 每日摘要

```bash
python summarize_cron_log.py --log-file logs/cron.log --days 7
```

關鍵警示：

- `embedding_model_load_failed`
- `embedding_duration_warning`
- `embedding_memory_warning`
- `zero_recall_streak >= EMBEDDING_ZERO_RECALL_WARN_DAYS`
