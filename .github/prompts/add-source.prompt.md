---
description: "Add a new procurement data source to the monitoring system."
agent: "agent"
tools: [read, search, edit, execute]
argument-hint: "Name and URL of the new data source"
---

新增一個標案資料來源到監控系統：

1. 在 `crawler/` 目錄下建立新的爬蟲模組，參考 `crawler/gov.py` 的結構
2. 實作 `fetch_bids(settings, logger) -> list[BidRecord]`
3. 在 `core/config.py` 的 `Settings` 中新增對應的 selector 設定
4. 在 `core/pipeline.py` 的 `run_monitor` 中註冊新來源
5. 在 `.env.example` 中加入新的環境變數說明
6. 執行測試驗證
