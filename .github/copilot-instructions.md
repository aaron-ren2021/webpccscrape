# 教育資訊標案自動監控系統 - 專案指南

## 專案概述
台灣政府採購標案自動監控系統，每日抓取標案資料、篩選教育單位資訊設備案件，透過 AI 分析優先度，以 Email 通知並自動建立 GitHub Issue 追蹤。

## 架構
```
crawler/  → 資料抓取層（requests + BeautifulSoup，可選 Playwright fallback）
core/     → 邏輯核心（過濾、去重、AI分類、格式化）
notify/   → 通知層（ACS Email → SMTP fallback → GitHub Issue）
storage/  → 狀態儲存（Azure Table → Blob → Memory fallback）
```

## 程式碼風格
- Python 3.11+，使用 `from __future__ import annotations`
- 使用 `dataclass(slots=True)` 定義資料結構
- 所有模組使用 `logging` 模組記錄 log，格式為結構化 extra dict
- 型別標註使用 `Optional` 和 `list[str]` 語法
- 環境變數透過 `core/config.py` 的 `Settings.from_env()` 管理

## 關鍵設計原則
1. **多層 fallback**：每個功能都有降級方案（ACS→SMTP、Table→Blob→Memory）
2. **多組 selector 候選**：CSS selector 透過環境變數可熱調整，不需改程式碼
3. **AI 可選**：AI 分類為可選增強，關閉時回退到關鍵字匹配
4. **安全第一**：API Key 和密碼永遠不要硬編碼或寫入 log

## 測試
```bash
pytest                    # 單元測試
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state  # 整合測試
```

## 部署
- **Azure Functions**：`function_app.py`，Timer Trigger UTC 00:30
- **本地 crontab**：`run_local.py`，每日 8:35 執行
- 見 `LOCAL_DEPLOY.md` 取得完整本地部署步驟
