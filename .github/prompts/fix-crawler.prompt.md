---
description: "Diagnose crawler failures and suggest CSS selector fixes."
agent: "Crawler Doctor"
tools: [execute, read, search, edit]
---

爬蟲故障診斷流程：

1. 檢查最近的錯誤 log
2. 分析目標網站 DOM 是否變動
3. 測試現有 CSS selector 是否仍有效
4. 建議修復方案（優先修改 .env 環境變數）
5. 驗證修復結果
