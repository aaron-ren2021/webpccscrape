# 查詢系統規劃（Query System Planning）

本文件彙整未來將本專案升級為「標案查詢系統」的完整規劃，包含深度爬取、Hybrid Search、向量資料庫、台灣專有名詞處理、自然語言查詢等。

---

## 1. 目標
- 從「每日單日監控」升級為「可查詢歷史標案」的檢索系統
- 支援自然語言查詢、結構化過濾、全文檢索、台灣術語精準召回

## 2. 架構規劃摘要
- Playwright 深度爬取（模擬搜尋條件、逐筆詳細頁）
- CKIP 分詞 + Semantic Chunking
- BGE-M3（dense+sparse）向量化
- Qdrant 向量資料庫（Hybrid Search）
- BGE-reranker-large 二階段精排
- 查詢 API/CLI

## 3. 分階段實作
- Phase 1：搜尋模擬 + 詳細頁全文抓取
- Phase 2：Qdrant 部署 + Vector CRUD
- Phase 3：BGE-M3 Hybrid Search 整合
- Phase 4：CKIP 分詞 + Chunking
- Phase 5：Reranker + 查詢 API

## 4. 詳細規劃
請見 `/memories/session/vector_search_plan.md`，內含完整技術選型、資料流、驗證步驟、效能預估。

---

## 5. 目前狀態
- 現有系統為「單日自動監控」架構，僅支援當日新標案通知
- 本分支為查詢系統升級的前置規劃，尚未影響現有生產流程

---

> 詳細規劃與進度請見 `/memories/session/vector_search_plan.md`，如需推進請依 Phase 1 開始實作。
