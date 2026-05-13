# 教育資訊標案監控系統

每天定時彙整教育單位相關的資訊/軟體/網路/AI 標案，經過規則篩選、去重、詳細資料補強後，以 HTML Email 通知，並可選擇建立 GitHub Issue 追蹤高優先案件。

## 1. 專案目的

這個專案的核心目標是：

- 從多個來源抓取標案資料
- 聚焦教育單位與教育場域相關案件
- 篩出資訊設備、資訊服務、校園授權、網路、AI 運算等高相關標案
- 避免重複通知
- 補齊預算金額、押標金、截止投標、開標時間等詳細欄位
- 以 Email 發送每日新案摘要

當日沒有新案件時，不寄送通知，只在 log 留下 `no new bids`。

## 2. 目前實際架構盤點

### 2.1 入口

- `run_local.py`
  - 本機執行入口
  - 支援 `--no-send`、`--preview-html`、`--no-persist-state`
  - 會把執行紀錄寫入 `logs/cron.log`
- `function_app.py`
  - Azure Functions Timer Trigger 入口
  - 排程為每天 UTC `00:30`，對應台灣時間 `08:30`

兩個入口最後都會進到 `core.pipeline.run_monitor()`，因此真正的系統 orchestration 集中在 pipeline。

### 2.2 執行資料流

```text
run_local.py / function_app.py
            ↓
     core.config.Settings
            ↓
   core.pipeline.run_monitor()
            ↓
  crawler.taiwanbuying / crawler.gov / crawler.g0v
            ↓
  台灣採購公報候選提示合併到 gov 正式案件
            ↓
      core.filters.filter_bids()
            ↓
   core.dedup.deduplicate_bids()
            ↓
 storage.detail_cache_store 套用快取
            ↓
 gov/g0v inline detail enrichment
            ↓
 排除過期案件 / 排除 candidate-only 案件
            ↓
 可選 AI 分類與優先度標記
            ↓
 狀態比對（local JSON / Azure Table / Blob）
            ↓
 core.formatter 產生 HTML 與主旨
            ↓
 notify.dispatcher -> ACS 或 SMTP
            ↓
 可選 GitHub issue 建立
            ↓
 標記已通知 / detail backfill queue
```

### 2.3 來源角色分工

- `crawler/taiwanbuying.py`
  - 主要用來抓候選案件與類別提示
  - 在 pipeline 中會作為 `candidate_only` 線索，協助補強 `gov_pcc` 正式案件判斷
- `crawler/gov.py`
  - 正式通知主來源之一
  - 先抓列表頁，再視需要補抓詳細頁資訊
- `crawler/g0v.py`
  - `https://pcc-api.openfun.app` 開放資料來源
  - 作為結構化補充來源，並可進一步補強連結與詳細欄位

目前 pipeline 不是把三個來源完全平行視為相同資料，而是：

- `taiwanbuying` 偏向候選提示來源
- `gov_pcc` 與 `g0v` 是進入正式篩選與通知的主要資料來源

### 2.4 核心模組職責

- `core/config.py`
  - 集中解析 `.env` / App Settings
  - 目前已涵蓋 crawler、stealth、proxy、state、detail cache、AI、embedding、GitHub 等設定
- `core/models.py`
  - 定義 `BidRecord`、`RunResult`、`SourceRunStatus`
  - `BidRecord` 已含列表欄位、detail 欄位、AI 欄位與 metadata
- `core/filters.py`
  - 教育單位判斷
  - 嚴格主題詞、寬鬆主題詞、排除詞、上下文條件
  - 是第一層商業規則篩選
- `core/dedup.py`
  - 標題/機關/日期等層面的去重
- `core/normalize.py`
  - 日期、金額、文字正規化與截止日判斷
- `core/stable_keys.py`
  - 產生通知穩定鍵，降低跨來源重複通知
- `core/formatter.py`
  - 產生 Email HTML 與主旨
- `core/pipeline.py`
  - 整個系統的執行骨幹
  - 整合抓取、過濾、去重、detail enrichment、AI 分類、通知與狀態寫回

### 2.5 詳細資料補強機制

目前 detail enrichment 已經不是單一步驟，而是兩層設計：

- Inline enrichment
  - 在 `core.pipeline.run_monitor()` 內，對仍缺少 detail 欄位的案件立即補抓
  - 優先提升當次通知內容完整度
- Background backfill
  - 由 `storage/detail_cache_store.py` 管理缺漏佇列與快取
  - `core/detail_backfill.py` 可針對待補案件批次回填

`DetailCacheStore` 目前負責：

- 套用既有 detail cache
- 維護待補隊列
- 記錄成功/失敗與嘗試次數
- 以 TTL 清理過期 detail 資料

### 2.6 狀態儲存策略

通知去重狀態目前有三種路徑：

- `storage/local_state_store.py`
  - 本機 JSON 狀態檔
  - 支援舊格式遷移與 retention 清理
- `storage/table_store.py`
  - Azure Table Storage
- `storage/blob_store.py`
  - Azure Blob JSON fallback

如果不持久化，pipeline 也會退回 in-memory store，但那只適合單次測試。

### 2.7 通知與追蹤

- `notify/dispatcher.py`
  - 統一通知入口
  - `dry_run` 直接跳過寄送
  - 有 ACS 就先走 ACS，失敗再 fallback SMTP
- `notify/email_acs.py`
  - Azure Communication Services Email
- `notify/email_smtp.py`
  - SMTP 備援
- `notify/github_notify.py`
  - 若設定 GitHub token/repo，會為 AI 判定 `high` 的案件建立 Issue

### 2.8 反偵測與抓取支援層

`crawler/` 目前除了來源抓取檔，也包含一整層共用支援：

- `crawler/stealth/`
  - 瀏覽器指紋與 stealth 初始化
- `crawler/behavior/`
  - 人類行為模擬與節流
- `crawler/session/`
  - session 持久化
- `crawler/network/`
  - proxy 管理
- `crawler/detection/`
  - 封鎖、captcha、挑戰頁等事件記錄
- `crawler/stealth_runner.py`
  - 反偵測統一入口
- `crawler/common.py`
  - 共用 session / HTTP helper

這代表目前系統不是單純 requests crawler，而是同時支援：

- `requests + BeautifulSoup`
- `Playwright + Stealth`

並且可透過設定切換或降級。

## 3. 專案結構

```text
.
├─ function_app.py                 # Azure Timer Trigger 入口
├─ run_local.py                    # 本機執行入口
├─ run_detail_backfill.py          # detail backfill 執行入口
├─ check_sources.py                # 多來源健康檢查
├─ verify_stealth.py               # stealth 驗證工具
├─ summarize_cron_log.py           # cron log 摘要工具
├─ requirements.txt
├─ host.json
├─ local.settings.json.example
├─ AGENTS.md
├─ crawler/
│  ├─ common.py
│  ├─ gov.py
│  ├─ taiwanbuying.py
│  ├─ g0v.py
│  ├─ batch_crawler.py
│  ├─ identity_manager.py
│  ├─ stealth_runner.py
│  ├─ analytics/
│  ├─ behavior/
│  ├─ detection/
│  ├─ network/
│  ├─ session/
│  └─ stealth/
├─ core/
│  ├─ ai_classifier.py
│  ├─ config.py
│  ├─ dedup.py
│  ├─ detail_backfill.py
│  ├─ embedding_categories.py
│  ├─ embedding_recall.py
│  ├─ filters.py
│  ├─ formatter.py
│  ├─ high_amount.py
│  ├─ models.py
│  ├─ normalize.py
│  ├─ pipeline.py
│  └─ stable_keys.py
├─ storage/
│  ├─ blob_store.py
│  ├─ detail_cache_store.py
│  ├─ local_state_store.py
│  └─ table_store.py
├─ notify/
│  ├─ dispatcher.py
│  ├─ email_acs.py
│  ├─ email_smtp.py
│  └─ github_notify.py
├─ tests/
│  ├─ test_dedup.py
│  ├─ test_detail_backfill.py
│  ├─ test_detail_cache_store.py
│  ├─ test_filters.py
│  ├─ test_formatter.py
│  ├─ test_g0v.py
│  ├─ test_gov.py
│  ├─ test_hybrid_scoring.py
│  ├─ test_local_state_store.py
│  ├─ test_normalize.py
│  ├─ test_pipeline_notifications.py
│  └─ ...
└─ docs/
   ├─ ADVANCED_ANTI_DETECTION.md
   ├─ IDENTITY_ROTATION_GUIDE.md
   └─ ...
```

## 4. 執行模式

### 4.1 本機模式

適合開發、手動巡檢、cron 執行。

```bash
python run_local.py
```

常用變體：

```bash
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state
```

### 4.2 Azure Functions 模式

適合雲端定時執行。

- 入口：`function_app.py`
- Timer Cron：`0 30 0 * * *`
- Azure 使用 UTC，因此 `00:30 UTC = 08:30 Asia/Taipei`

### 4.3 Detail Backfill 模式

用於補齊先前通知後仍缺少 detail 欄位的案件。

```bash
python run_detail_backfill.py
```

## 5. 安裝方式

1. 建立 Python 3.12 環境
2. 安裝依賴

```bash
pip install -r requirements.txt
```

3. 準備設定檔

```bash
cp local.settings.json.example local.settings.json
```

如果專案另外有 `.env.example`，也可複製後再調整本機設定。

4. 安裝 Playwright 與 Chromium

```bash
pip install playwright
playwright install chromium
```

5. 驗證 stealth 環境

```bash
python verify_stealth.py
```

## 6. 本機常用指令

### 6.1 本機預覽但不寄信

```bash
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state
```

### 6.2 本機完整流程

```bash
python run_local.py
```

### 6.3 執行測試

```bash
pytest
```

### 6.4 檢查資料來源健康

```bash
python check_sources.py
```

### 6.5 產生 log 摘要

```bash
python summarize_cron_log.py --log-file logs/cron.log --days 7
```

## 7. 本地部署與排程

### 7.1 crontab 範例

```bash
crontab -e
```

加入：

```cron
35 8 * * 1-5 cd /home/xcloud/project/webpccscrape && /home/xcloud/project/webpccscrape/venv/bin/python run_local.py >> /home/xcloud/project/webpccscrape/logs/cron.log 2>&1
```

### 7.2 每日摘要排程範例

```cron
0 9 * * 1-5 cd /home/xcloud/project/webpccscrape && /home/xcloud/project/webpccscrape/venv/bin/python summarize_cron_log.py --log-file logs/cron.log --days 1 >> /home/xcloud/project/webpccscrape/logs/cron_summary.log 2>&1
```

## 8. 重要設定分類

請以 `core/config.py` 為準；目前 README 只整理主要類別：

- 抓取與來源
  - `TAIWANBUYING_*`
  - `GOV_*`
  - `G0V_*`
  - `API_ONLY_MODE`
- 通用 HTTP / timeout / retry
  - `REQUEST_*`
  - `REQUEST_DELAY_*`
- Stealth / session / proxy
  - `ENABLE_PLAYWRIGHT`
  - `STEALTH_*`
  - `PROXY_*`
- 通知去重與保存
  - `STATE_RETENTION_DAYS`
  - `AZURE_STORAGE_CONNECTION_STRING`
  - `AZURE_TABLE_NAME`
  - `AZURE_BLOB_*`
- Detail cache / backfill
  - `DETAIL_CACHE_*`
  - `DETAIL_BACKFILL_*`
- 通知
  - ACS：`ACS_CONNECTION_STRING`、`ACS_EMAIL_SENDER`
  - SMTP：`SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`SMTP_FROM`
  - 收件者：`EMAIL_TO`
- AI 分類
  - `ENABLE_AI_CLASSIFICATION`
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `AI_MODEL`
  - `OLLAMA_*`
- Embedding recall
  - `ENABLE_EMBEDDING_RECALL`
  - `EMBEDDING_*`
- GitHub issue tracking
  - `GITHUB_TOKEN`
  - `GITHUB_REPO`
  - `GITHUB_LABELS`

## 9. 儲存與通知行為

### 9.1 新案判斷

pipeline 會先讀取已通知 key，再用 `core/stable_keys.py` 產生穩定識別鍵，避免：

- 同一來源重複通知
- 不同來源指向同一標案時重複通知

### 9.2 detail 欄位缺漏時的行為

若列表頁或 API 當下取不到完整 detail，系統會：

- 先嘗試 inline enrichment
- 若仍缺漏，Email 內容允許優雅降級
- 把案件加入 detail backfill queue，供後續補抓

### 9.3 通知後寫回

當通知成功後，系統會：

- 寫入已通知狀態
- 將仍缺少 detail 的案件加入待補隊列

## 10. Azure 部署

### 10.1 需要工具

- Azure CLI
- Azure Functions Core Tools v4

### 10.2 建立資源範例

```bash
az group create -n rg-bid-monitor -l eastasia
az storage account create -n <storageAccount> -g rg-bid-monitor -l eastasia --sku Standard_LRS
az functionapp create \
  -g rg-bid-monitor \
  -n <functionAppName> \
  --storage-account <storageAccount> \
  --consumption-plan-location eastasia \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4
```

### 10.3 設定 App Settings

把本機使用的環境變數同步到 Function App Configuration。

### 10.4 部署

```bash
func azure functionapp publish <functionAppName>
```

## 11. 常見故障排除

### 11.1 抓不到資料

- 檢查 `*_ROW_SELECTORS`、`*_TITLE_SELECTORS` 等 selector
- 優先調整環境變數，不要先改程式
- 若動態頁面變多，確認 Playwright / Chromium 是否安裝完整

### 11.2 只有單一來源成功

- 另一來源失敗不會中止整體流程
- 先看 log 中的 `source_failed`

### 11.3 沒寄信

- 無新案時本來就不寄信
- 若應寄未寄，檢查 `notification_failed`
- 檢查 ACS 失敗後是否已 fallback SMTP

### 11.4 重複通知

- 檢查 state store 是否啟用持久化
- 本機若加上 `--no-persist-state`，每次執行都會視為新一輪
- 檢查 local JSON / Azure Table / Blob 設定是否正確

### 11.5 detail 欄位長期缺漏

- 檢查 `detail_cache_*` 與 queue 檔案
- 執行 `python run_detail_backfill.py`
- 觀察 `detail_backfill_*`、`detail_cache_*` 相關 log

## 12. 反偵測與 Stealth 機制

目前已具備完整的 Playwright + Stealth 支援層，主要能力包含：

- 瀏覽器指紋隱匿
- 人類行為模擬
- identity / proxy 輪轉
- session 持久化
- 自適應節流與 cooldown
- 偵測 blocked / captcha / challenge 事件並記錄

相關模組位於：

- `crawler/stealth/`
- `crawler/behavior/`
- `crawler/session/`
- `crawler/network/`
- `crawler/detection/`

可用以下指令驗證環境：

```bash
python verify_stealth.py
```

## 13. 測試現況

`tests/` 目前已涵蓋多個核心區塊，包括：

- `filters`
- `dedup`
- `normalize`
- `formatter`
- `gov`
- `g0v`
- `detail_cache_store`
- `detail_backfill`
- `local_state_store`
- `pipeline notifications`

建議每次調整核心規則、通知格式或 crawler 行為後都跑一次：

```bash
pytest
```
