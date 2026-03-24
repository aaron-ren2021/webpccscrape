# Azure 教育資訊標案自動監控系統

## 1. 專案目的
本專案會每天定時抓取兩個來源的標案資料（台灣採購公報、政府電子採購相關公開查詢頁），篩選「教育單位」且「資訊設備/資訊服務」相關案件，去重後以 HTML Email 通知。若當日無新案件則不寄信，僅在 log 記錄 `no new bids`。

## 2. 架構說明
- 執行環境：Azure Functions (Python Timer Trigger)
- 觸發時間：每天台灣時間 08:30（UTC `00:30`）
- 抓取層：
  - 優先 `requests + BeautifulSoup`
  - 無法解析時可啟用 `Playwright` fallback
- 邏輯層：
  - 關鍵字篩選（教育單位 + 主題）
  - 精準去重 + 近似去重
  - 新案判斷（未通知過）
- 儲存層：
  - 優先 Azure Table Storage
  - 失敗 fallback Azure Blob Storage JSON
- 通知層：
  - 優先 ACS Email
  - 未配置/失敗 fallback SMTP

## 3. 專案結構
```text
.
├─ function_app.py
├─ run_local.py
├─ host.json
├─ requirements.txt
├─ local.settings.json.example
├─ .env.example
├─ crawler/
│  ├─ common.py
│  ├─ gov.py
│  └─ taiwanbuying.py
├─ core/
│  ├─ config.py
│  ├─ dedup.py
│  ├─ filters.py
│  ├─ formatter.py
│  ├─ models.py
│  ├─ normalize.py
│  └─ pipeline.py
├─ storage/
│  ├─ blob_store.py
│  └─ table_store.py
├─ notify/
│  ├─ dispatcher.py
│  ├─ email_acs.py
│  └─ email_smtp.py
└─ tests/
   ├─ test_dedup.py
   ├─ test_filters.py
   └─ test_normalize.py
```

## 4. 安裝方式
1. 建立 Python 3.11+ 環境
2. 安裝依賴：
```bash
pip install -r requirements.txt
```
3. 複製設定檔：
```bash
cp .env.example .env
cp local.settings.json.example local.settings.json
```
4. 如需 Playwright fallback：
```bash
playwright install chromium
```

## 5. 本機執行方式
### 5.1 本機測試模式（不寄信、輸出 HTML）
```bash
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state
```

### 5.2 本機完整流程（含寄信）
```bash
python run_local.py
```

### 5.3 單元測試
```bash
pytest


## 6. 本地部署腳本（Linux）

### 6.1 crontab 定時排程

若僅需在本地每天工作日 8:30 自動寄信，可用 crontab 設定：

```bash
crontab -e
```

新增以下內容（假設 Python 路徑與專案路徑已正確）：

```
30 8 * * 1-5 /usr/bin/python3 /你的路徑/webpccscrape/run_local.py
```

說明：
- `30 8 * * 1-5` 代表每週一至五早上 8:30 執行
- `/usr/bin/python3` 請依實際 Python 路徑調整
- `/你的路徑/webpccscrape/run_local.py` 請改為實際專案路徑

### 6.2 SMTP 設定

請於 `.env` 設定 SMTP 相關參數，範例如下：

```
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_account
SMTP_PASSWORD=your_password
SMTP_FROM=your@email.com
EMAIL_TO=收件人1,收件人2
```

---
```

## 6. Azure 部署方式
### 6.1 需要工具
- Azure CLI
- Azure Functions Core Tools v4

### 6.2 建立資源（範例）
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

### 6.3 設定 App Settings
將 `.env.example` 內參數（不含註解）設定到 Function App Configuration。

### 6.4 部署
```bash
func azure functionapp publish <functionAppName>
```

## 7. 定時排程說明
- Timer Cron：`0 30 0 * * *`
- Azure Timer 使用 UTC，`00:30 UTC = 08:30 Asia/Taipei`

## 8. 環境變數說明
請參考 `.env.example`，重點如下：
- 抓取：`TAIWANBUYING_*`、`GOV_*`
- 儲存：`AZURE_STORAGE_CONNECTION_STRING`、`AZURE_TABLE_NAME`、`AZURE_BLOB_*`
- 信件：
  - ACS：`ACS_CONNECTION_STRING`、`ACS_EMAIL_SENDER`
  - SMTP：`SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`SMTP_FROM`
  - 收件人：`EMAIL_TO`
- fallback：`ENABLE_PLAYWRIGHT_FALLBACK`

## 9. 常見故障排除
1. 抓不到資料
- 檢查 `*_ROW_SELECTORS` / `*_TITLE_SELECTORS` 等 selector。
- 優先改環境變數，不要先改程式。
- 動態頁面時啟用 `ENABLE_PLAYWRIGHT_FALLBACK=true`。

2. 只抓到單一來源
- 另一來源失敗不會中止整體流程，請看 log 的 `source_failed`。

3. 沒寄信
- 無新案時正常不寄信，log 會有 `no new bids`。
- 有新案未寄出時檢查 `notification_failed`。

4. 重複通知
- 檢查 Storage 連線設定。
- Table 失敗會自動 fallback 到 Blob。

## 10. 後續可擴充方向
- 增加更多公開來源與來源健康檢查。
- 將 selector 設定改為 Azure App Configuration 或 Key Vault 管理。
- 增加人工審核 UI / Teams 通知。
- 加入快照測試（HTML regression）與整合測試。

## 11. HTML 結構變動容錯設計
- 每個來源採「多組 selector 候選」策略。
- selector 透過環境變數可熱調整。
- 程式內含 TODO 註解提醒：若來源 DOM 大改，優先調整 selector 與查詢參數。

## 12. 部署前資源清單與設定值清單
### 12.1 Azure 資源
- Azure Function App (Python 3.11, Functions v4)
- Azure Storage Account
- （選用）Azure Communication Services Email + 已驗證寄件網域
- （可選）Application Insights

### 12.2 必填設定值
- `AZURE_STORAGE_CONNECTION_STRING`
- `EMAIL_TO`
- `TAIWANBUYING_URL`
- `GOV_URL`
- `USER_AGENT`

### 12.3 擇一寄信通道
- ACS（建議）
  - `ACS_CONNECTION_STRING`
  - `ACS_EMAIL_SENDER`
- SMTP（備援）
  - `SMTP_HOST` `SMTP_PORT` `SMTP_FROM`
  - 視需求加 `SMTP_USERNAME` `SMTP_PASSWORD`
