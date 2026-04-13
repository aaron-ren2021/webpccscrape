---
name: selector-maintenance
description: "Diagnose and fix web scraper CSS selector failures. Use when: crawler fails, scraper returns no data, website DOM structure changed, selector needs updating, debugging crawl errors, taiwanbuying or gov.pcc scraping issues."
argument-hint: "Describe the scraping error or source that broke"
---

# 爬蟲 Selector 維護專家 (Selector Maintenance Skill)

## 目的
當目標網站 DOM 結構改變導致爬蟲失敗時，自動診斷並建議修復方案。

## 使用時機
- 爬蟲抓不到資料（source_failed 錯誤）
- 抓取結果為空
- 解析 HTML 出現格式異常
- 需要新增/調整 CSS selector

## 診斷流程

### Step 1: 確認故障來源
檢查 logs 中的錯誤訊息：
```bash
grep -E "source_failed|parse_error|no records" logs/cron.log | tail -20
```

### Step 2: 檢查目標網站結構
使用 `#tool:execute` 取得目標頁面 HTML：
```bash
curl -s -A "Mozilla/5.0" "TARGET_URL" | head -200
```

### Step 3: 分析 DOM 變動
比對現有 selector 與實際 HTML 結構：

**台灣採購公報 (taiwanbuying)**：
- 設定檔：環境變數 `TAIWANBUYING_*_SELECTORS`
- 爬蟲程式：[crawler/taiwanbuying.py](../../crawler/taiwanbuying.py)
- 目前 selector：
  - 行：`table tbody tr`, `.result-item`, `.list-group-item`
  - 標題：`a`, `.title`, `.subject`, `td:nth-child(2)`
  - 機關：`.org`, `.unit`, `td:nth-child(3)`

**政府採購網 (gov.pcc)**：
- 設定檔：環境變數 `GOV_*_SELECTORS`
- 爬蟲程式：[crawler/gov.py](../../crawler/gov.py)
- 目前 selector：
  - 行：`table tbody tr`, `.result-item`, `.list-group-item`
  - 標題：`a`, `.title`, `.subject`, `td:nth-child(2)`
  - 機關：`.org`, `.unit`, `td:nth-child(3)`

### Step 4: 建議修復方案

1. **優先方案**：更新 `.env` 中的 selector 環境變數
   ```bash
   # 範例：更新台灣採購公報的行 selector
   TAIWANBUYING_ROW_SELECTORS=新selector1,新selector2
   ```

2. **備選方案**：啟用 Playwright（預設已啟用）
   ```bash
   ENABLE_PLAYWRIGHT=true
   ```

3. **最後方案**：修改爬蟲程式碼

### Step 5: 驗證修復
```bash
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state
```

## 共用爬蟲工具
參考 [crawler/common.py](../../crawler/common.py) 中的工具函式：
- `pick_first_text()` - 多候選 selector 取文字
- `pick_first_attr()` - 多候選 selector 取屬性
- `parse_html()` - HTML 解析

## 多組 Selector 候選策略
系統採用「多組 selector 候選」策略，每個欄位支援多個 CSS selector，依序嘗試直到匹配成功。修改時優先調整環境變數，不需改程式碼。

## 注意事項
- 優先透過環境變數調整，不要先改程式碼
- 每次只改一個 selector 並驗證
- 保留舊的 selector 作為候補
