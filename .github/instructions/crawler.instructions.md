---
description: "Use when modifying crawler code, updating CSS selectors, fixing scraping issues, or adding new data sources."
applyTo: "crawler/**/*.py"
---

# 爬蟲程式碼規範

- 每個來源的 `fetch_bids()` 必須回傳 `list[BidRecord]`
- 使用 `crawler/common.py` 中的共用工具函式（`build_session`, `request_html`, `pick_first_text`）
- CSS selector 應設計為多候選，透過 `settings` 傳入
- 異常時不要中止整體流程，讓其他來源繼續執行
- 若啟用 `ENABLE_PLAYWRIGHT_FALLBACK`，需在 requests 失敗後嘗試 Playwright
- 新增來源時需在 `core/pipeline.py` 的 `run_monitor` 中註冊
