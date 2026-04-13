# Azure 教育資訊標案自動監控系統

## 1. 專案目的
本專案會每天定時抓取兩個來源的標案資料（台灣採購公報、政府電子採購相關公開查詢頁），篩選「教育單位」且「資訊設備/資訊服務」相關案件，去重後以 HTML Email 通知。

**郵件內容包含**：
- 標案標題、機關名稱、公告日期、截止日期
- **預算金額**：從政府電子採購網詳細頁面抓取（如未公開則顯示「未公開」）
- **押標金**：押標金百分比或金額（如未提供則顯示「無提供」）
- 聯絡資訊、決標方式等

若當日無新案件則不寄信，僅在 log 記錄 `no new bids`。

## 2. 架構說明
- 執行環境：Azure Functions (Python Timer Trigger)
- 觸發時間：每天台灣時間 08:30（UTC `00:30`）
- 抓取層：
  - 預設 `Playwright + Stealth`（真人行為模擬/指紋隱匿/identity 輪轉）
  - 無法啟動瀏覽器時自動 fallback `requests + BeautifulSoup`
- 邏輯層：
  - 關鍵字篩選（教育單位 + 主題）
  - 精準去重 + 近似去重
  - **詳細資料補充**：針對政府電子採購網標案，額外抓取詳細頁面以取得預算金額與押標金資訊
  - 新案判斷（未通知過）
- 儲存層：
  - 優先 Azure Table Storage
  - 失敗 fallback Azure Blob Storage JSON
- 通知層：
  - 優先 ACS Email
  - 未配置/失敗 fallback SMTP

```text
.
├─ function_app.py
├─ run_local.py
├─ host.json
├─ requirements.txt
├─ local.settings.json.example
├─ .env.example
├─ STEALTH_MIGRATION_COMPLETE.md   # Stealth/Playwright 重大改版紀錄
├─ verify_stealth.py               # Stealth/真人行為模擬驗證腳本
├─ crawler/
│  ├─ common.py
│  ├─ gov.py
│  ├─ taiwanbuying.py
│  ├─ stealth/         # 指紋隱匿/瀏覽器初始化
│  ├─ behavior/        # 人類行為模擬/節流
│  ├─ session/         # Session 持久化
│  ├─ network/         # Proxy 輪轉
│  ├─ detection/       # 偵測事件記錄
│  └─ stealth_runner.py# 反偵測統一入口
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
4. Playwright 及瀏覽器安裝（**必須**）：
```bash
pip install playwright
playwright install chromium
```
5. （可選）驗證 Stealth/真人行為模擬：
```bash
python verify_stealth.py
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

### 5.3 驗證 Stealth/真人行為模擬
```bash
python verify_stealth.py
```

### 5.4 單元測試
```bash
pytest


## 6. 本地部署腳本（Linux）

### 6.1 crontab 定時排程

若需在本地每天工作日 8:30 自動寄信，可用 crontab 設定：

```bash
crontab -e
```

新增以下內容（假設 Python 路徑與專案路徑已正確）：

```
30 8 * * 1-5 /home/xcloud/project/webpccscrape/venv/bin/python /home/xcloud/project/webpccscrape/run_local.py >> /home/xcloud/project/webpccscrape/logs/cron.log 2>&1
```

說明：
- `30 8 * * 1-5` 代表每週一至五早上 8:30 執行
- `/home/xcloud/project/webpccscrape/venv/bin/python` 為虛擬環境內的 Python 路徑
- `>> logs/cron.log 2>&1` 將輸出記錄到 logs/cron.log 檔案

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
- Playwright：`ENABLE_PLAYWRIGHT`

## 9. 常見故障排除
1. 抓不到資料
- 檢查 `*_ROW_SELECTORS` / `*_TITLE_SELECTORS` 等 selector。
- 優先改環境變數，不要先改程式。
- 動態頁面時啟用 `ENABLE_PLAYWRIGHT=true`（預設已啟用）。

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

## 12. 反偵測/Stealth 機制說明

本專案已預設全面啟用 Playwright + Stealth 反偵測強化層，顯著提升動態網頁抓取成功率，降低被封鎖/驗證碼機率。

### 12.1 功能亮點
- **瀏覽器指紋隱匿**：自動遮蔽 `navigator.webdriver`、plugins、languages、WebGL 等自動化特徵，並隨機選用真實桌面 Chrome 指紋組合。
- **人類行為模擬**：自動隨機捲動、滑鼠移動、hover/click、停留時間，避免機械式操作，並可於 `verify_stealth.py` 驗證。
- **Identity/Proxy 輪轉**：自動切換多組身份與 Proxy，降低單一來源被封鎖風險。
- **Session 持久化**：自動儲存/載入 cookies 與 localStorage，讓每次執行都像「回訪用戶」而非新機器人。
- **自適應請求節奏**：完全取代固定 sleep，改用 jitter、cooldown window、指數退避，降低異常流量偵測。
- **偵測事件記錄**：自動分類成功/封鎖/驗證碼/挑戰頁，失敗時自動截圖與 HTML 快照，便於除錯。

### 12.2 啟用方式
- **已預設啟用**（`STEALTH_ENABLED=true`），如需關閉可設 `STEALTH_ENABLED=false`。
- Proxy/identity 輪轉功能可於 `.env` 設定 `PROXY_ENABLED=true` 並填入 `PROXY_LIST`。
- 所有參數皆可於 `.env` 或 Azure App Settings 熱調整。

### 12.3 主要檔案結構
（見上方「專案結構」）

### 12.4 相關環境變數
- `STEALTH_ENABLED`：是否啟用反偵測（預設 true）
- `STEALTH_HUMAN_BEHAVIOR`：啟用人類行為模擬（預設 true）
- `STEALTH_SESSION_PERSISTENCE`：啟用 session 持久化
- `STEALTH_MAX_RETRIES`：失敗重試次數
- `STEALTH_THROTTLE_DELAY_MIN/MAX`：每次請求最小/最大間隔
- `STEALTH_THROTTLE_COOLDOWN_AFTER`：每 N 次請求後 cooldown
- `PROXY_ENABLED`、`PROXY_LIST`、`PROXY_STRATEGY`：Proxy 輪轉設定
## 13. 常見 Stealth 問題排解
- 若遇驗證碼/封鎖，建議：
  - 增加 Proxy/identity 組數，調整 `STEALTH_THROTTLE_DELAY_MAX` 增加間隔
  - 檢查 log 內 `batch_fetch_error`、`blocked`、`captcha` 訊息
  - 執行 `python verify_stealth.py` 驗證環境與參數
  - 如仍失敗，請參考 `STEALTH_MIGRATION_COMPLETE.md` 或聯絡維護者

詳細請見 `local.settings.json.example`。
