---
name: pipeline-debug
description: "Debug the bid monitoring pipeline end-to-end. Use when: pipeline fails, no email sent, dedup issues, notification errors, state storage problems, troubleshooting run_local or function_app execution."
argument-hint: "Describe the pipeline issue you're seeing"
---

# Pipeline 除錯專家 (Pipeline Debug Skill)

## 目的
端到端除錯標案監控管線，從資料抓取到通知寄送的完整流程。

## 使用時機
- pipeline 執行失敗
- 沒有收到通知信
- 去重邏輯異常
- 狀態儲存問題

## 管線架構

```
抓取(crawler) → 過濾(filters) → 去重(dedup) → AI分類(ai_classifier)
    → 狀態比對(state_store) → 格式化(formatter) → 通知(dispatcher)
    → GitHub Issue(github_notify) → 狀態更新(state_store)
```

## 除錯檢查清單

### 1. 資料抓取階段
```bash
# 檢查爬蟲是否正常
grep "source_failed" logs/cron.log | tail -5
```
- 檔案：[crawler/gov.py](../../crawler/gov.py), [crawler/taiwanbuying.py](../../crawler/taiwanbuying.py)
- 常見問題：網路逾時、selector 失效、被擋 IP

### 2. 過濾階段
- 檔案：[core/filters.py](../../core/filters.py)
- 確認 `EDU_ORG_KEYWORDS` 和 `THEME_KEYWORDS` 是否涵蓋目標

### 3. AI 分類階段
- 檔案：[core/ai_classifier.py](../../core/ai_classifier.py)
- 確認 `ENABLE_AI_CLASSIFICATION=true` 和 API Key 設定
- 檢查 AI 回應格式是否正確

### 4. 去重階段
- 檔案：[core/dedup.py](../../core/dedup.py)
- 確認 UID 計算方式：[core/normalize.py](../../core/normalize.py)

### 5. 通知階段
```bash
grep "notification_failed\|acs_send_failed\|smtp" logs/cron.log | tail -5
```
- 檔案：[notify/dispatcher.py](../../notify/dispatcher.py)
- SMTP fallback：[notify/email_smtp.py](../../notify/email_smtp.py)

### 6. 狀態儲存
- Table Store：[storage/table_store.py](../../storage/table_store.py)
- Blob fallback：[storage/blob_store.py](../../storage/blob_store.py)
- 本地模式使用 `InMemoryStateStore`

## 快速測試指令
```bash
# 完整測試（不寄信、不存狀態）
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state

# 檢查產出
cat ./output/preview.html | head -50
```
