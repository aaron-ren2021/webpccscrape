---
description: "Run a complete bid monitoring test cycle: crawl, filter, classify, and generate preview HTML without sending emails."
agent: "agent"
tools: [execute, read, search]
---

執行完整標案監控測試流程：

1. 啟動虛擬環境
2. 執行 `python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state`
3. 檢查 `./output/preview.html` 的輸出內容
4. 回報抓取結果摘要：
   - 總共抓取幾筆
   - 過濾後幾筆
   - 去重後幾筆
   - 新增幾筆
   - 各來源狀態
   - AI 分類結果（如有啟用）
