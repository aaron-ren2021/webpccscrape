# CURRENT_CONFIG

## 生產真值（Local Cron）

- 執行入口：`run_local.py`
- 排程：`30 8 * * 1-5`（Asia/Taipei，每週一到五 08:30）
- Log：`logs/cron.log`
- Pipeline：Core Keywords + Support Context + Boundary Embedding Recall（BGE-M3）

## 目前規則重點

- Keyword filter 已改成 `核心詞 / 輔助詞` 雙層
- 只有核心詞可直接構成 IT 主題命中
- 輔助詞如 `建置`、`整合`、`開發`、`管理`、`平台`、`系統` 不再單獨算分
- 輔助詞必須搭配核心詞或明確 IT 場景才會形成 boundary / high confidence
- 英文縮寫改為詞邊界比對，避免 `iPad Air` 這類字串誤中 `AI`

## 目前建議設定

```bash
ENABLE_EMBEDDING_RECALL=true
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_TOP_K=30
EMBEDDING_SIMILARITY_THRESHOLD=0.68

# 可選：旁路 A/B（不影響正式通知）
EMBEDDING_ENABLE_AB_TEST=false
EMBEDDING_AB_MODEL=
EMBEDDING_AB_SIMILARITY_THRESHOLD=0.65
EMBEDDING_AB_TOP_K=30

# 可選：效能告警門檻
EMBEDDING_TIMEOUT_WARN_MS=3000
EMBEDDING_MEMORY_WARN_MB=2048
EMBEDDING_ZERO_RECALL_WARN_DAYS=3
```

## 每日檢查項

- 來源抓取：`local_run_finished` 的 `source_status`、`source_success_count`、`source_failed_count`
- Keyword 篩選：`keyword_screen_distribution` 的 `high_confidence`、`boundary`
- Embedding 召回：`embedding_recall_pipeline_step`、`embedding_recall_done` 的 `candidate_count/recalled`
- 最終通知：`local_run_finished` 的 `new_count`、`notification_sent`、`notification_backend`
- 失敗原因：`source_failed`、`embedding_model_load_failed`、`embedding_recall_failed`、`notification_failed`

## 效能與異常觀測

- 載入模型失敗：`embedding_model_load_failed`
- 單次推理超時：`embedding_duration_warning`
- 記憶體飆高：`embedding_memory_warning`
- 連續多日 recall 異常為 0：用 `summarize_cron_log.py` 檢查 `zero_recall_streak`

## A/B 比較規格（Sidecar）

啟用 `EMBEDDING_ENABLE_AB_TEST=true` 後，會額外寫入：

- `embedding_ab_dataset_row`
- `embedding_ab_row`
- `embedding_ab_summary`

可比對欄位固定為：

- `uid`
- `title`
- `keyword_confidence`
- `embedding_similarity`
- `embedding_best_category`
- `decision_source`
- `model_name`
- `threshold`

## Threshold 微調準則

- 基準值維持 `0.68`
- 候選值只比較 `0.65 / 0.68 / 0.70`
- 測試集通過率不得下降
- 生產誤判率下降優先，尤其是非 IT 的教學器材、交流行政、消費型硬體
- 誤判/漏判拉扯時，維持現值 `0.68`

## 快速驗證命令

```bash
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state
python summarize_cron_log.py --log-file logs/cron.log --days 7
pytest -q tests/test_filters.py test_exclude_filter.py
```

## 已知風險

- 首次載入 BGE-M3 可能因網路/快取造成額外延遲
- 依賴缺失（如 `numpy`、`sentence-transformers`）會導致 embedding 測試或召回失敗
- `logs/cron.log` 若被外部 rotation/清理，長期趨勢需先做歸檔
