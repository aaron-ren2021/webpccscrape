# Azure 教育資訊標案自動監控系統

## 1. 專案目的
本專案每天定時抓取多個來源的標案資料，篩選「教育單位」且「資訊設備/資訊服務」相關案件，去重後以 HTML Email 通知。

**資料來源（多層容錯）**：
1. **台灣採購公報**（taiwanbuying）— Playwright + Stealth 抓取
2. **政府電子採購網**（gov.pcc）— Playwright + Stealth 抓取列表頁
3. **開放資料 API**（https://pcc-api.openfun.app）— 結構化補充來源

**郵件內容包含**：
- 標案標題、機關名稱、截止投標日期
- **預算金額**：列表頁無此欄位時顯示「詳見連結」，引導使用者點擊連結查看
- **押標金/開標時間**：詳細頁資訊，無法取得時顯示「詳見連結」
- 直接連結至標案詳細頁面

**容錯策略**：
- 列表頁資料優先（標題、機關、截止日期）
- 詳細頁無法取得時優雅降級，不影響通知
- 多來源自動 fallback，確保每日穩定通知

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

### 6.3 BGE-M3 生產設定與每日巡檢

`.env` 建議至少設定：

```bash
ENABLE_EMBEDDING_RECALL=true
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_TOP_K=30
EMBEDDING_SIMILARITY_THRESHOLD=0.68

# 可選：旁路 A/B（只寫 log，不影響正式通知）
EMBEDDING_ENABLE_AB_TEST=false
EMBEDDING_AB_MODEL=
EMBEDDING_AB_SIMILARITY_THRESHOLD=0.65
EMBEDDING_AB_TOP_K=30

# 可選：效能告警門檻
EMBEDDING_TIMEOUT_WARN_MS=3000
EMBEDDING_MEMORY_WARN_MB=2048
EMBEDDING_ZERO_RECALL_WARN_DAYS=3
```

每日巡檢（`logs/cron.log`）重點事件：
- `local_run_finished`：`crawled_count/filtered_count/deduped_count/new_count/source_success_count/source_failed_count`
- `keyword_screen_distribution`：`high_confidence/boundary/included_total`
- `bid_bond_unparsed_summary`：`unparsed_count/top_patterns/sample_count`
- `embedding_recall_pipeline_step`：`duration_ms/memory_mb/model_name/threshold/top_k`
- `embedding_recall_done`：`candidate_count/recalled/result_count`
- `embedding_duration_warning`、`embedding_memory_warning`、`embedding_model_load_failed`

每日摘要工具：

```bash
python summarize_cron_log.py --log-file logs/cron.log --days 7
```

若需要每日彙總輸出（可選）：

```bash
python summarize_cron_log.py --log-file logs/cron.log --days 1 >> logs/cron_summary.log 2>&1
```

若需要旁路 A/B 比較，查看：
- `embedding_ab_dataset_row`（統一欄位：`uid/title/keyword_confidence/embedding_similarity/embedding_best_category/decision_source/model_name/threshold`）
- `embedding_ab_row`
- `embedding_ab_summary`

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
- Embedding：`ENABLE_EMBEDDING_RECALL`、`EMBEDDING_MODEL`、`EMBEDDING_TOP_K`、`EMBEDDING_SIMILARITY_THRESHOLD`
- Embedding A/B：`EMBEDDING_ENABLE_AB_TEST`、`EMBEDDING_AB_MODEL`、`EMBEDDING_AB_SIMILARITY_THRESHOLD`、`EMBEDDING_AB_TOP_K`
- 押標金未解析監控：`BID_BOND_UNPARSED_SAMPLE_SIZE`、`BID_BOND_UNPARSED_RAW_TRUNCATE`、`BID_BOND_UNPARSED_TOP_N`

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

## 10. 多來源容錯策略

### 10.1 資料來源優先順序
1. **taiwanbuying**（台灣採購公報）
   - 方式：Playwright + Stealth
   - 狀態：✅ 穩定（約 15-20 筆/天）

2. **gov.pcc**（政府電子採購網）
   - 列表頁：Playwright + Stealth ✅ 正常（約 900-1000 筆/天）
   - 詳細頁：❌ CAPTCHA 必擋（`/tps/` 子系統撲克牌驗證）
   - 策略：**列表頁資料 + 快速探測**（2 筆 URL 測試，全失敗則跳過）

3. **pcc-api.openfun.app**（開放資料 API）
   - 方式：REST API，無需爬蟲
   - 資料來源：行政院公共工程委員會「政府電子採購網」
   - 授權：開放 CORS，允許自由取用（需遵守原始資料著作權）
   - API 端點：
     - 列表：`GET https://pcc-api.openfun.app/api/listbydate?date=YYYYMMDD`
     - 資訊：`GET https://pcc-api.openfun.app/api/getinfo`
   - 狀態：⚠️ 作為補充來源（可能有 1-2 天延遲）

### 10.2 Detail 頁面策略

**列表頁可取得欄位**（gov.pcc）：
| 欄位 | 來源 | 狀態 |
|------|------|------|
| 🏫 機關 | 列表頁 td:nth-child(2) | ✅ |
| 📋 標案名稱 | 列表頁 td:nth-child(3) | ✅ |
| ⏰ 截止投標 | 列表頁 td:nth-child(5) | ✅ ROC 格式 115/04/24 |
| 🔗 詳細連結 | 列表頁 td:nth-child(4) a | ✅ |

**詳細頁獨有欄位**（無法穩定取得）：
- 💰 預算金額、💳 押標金、📌 開標時間

**Formatter Fallback 邏輯**：
```
預算金額: detail.budget_amount → "詳見連結"
截止投標: detail.bid_deadline（含時間） → list.bid_date（日期） ✅
押標金: detail.bid_bond → "詳見連結"
開標時間: detail.bid_opening_time → "詳見連結"
```

### 10.3 CAPTCHA 應對

gov.pcc 架構：
- `/prkms/` 子系統（列表頁）— stealth 可正常抓取
- `/tps/` 子系統（詳細頁）— **必定觸發撲克牌 CAPTCHA**，無法繞過

應對策略：
1. ✅ 列表頁 stealth 正常運作（主要資料來源）
2. ⚡ Detail 頁快速探測（2 筆測試 → CAPTCHA → 放棄）
3. ✅ Formatter 使用列表頁資料 fallback
4. ⏱️ 執行時間優化：從 7 分鐘降到 **60 秒**

### 10.4 來源健康檢查

執行 `python check_sources.py` 可檢查所有來源狀態：
```bash
python check_sources.py
```

輸出範例：
```
==========================================
來源健康檢查
==========================================
taiwanbuying     ✅ 正常     (18 筆)
gov_pcc          ✅ 正常     (965 筆)
g0v              ⚠️ 無資料   (0 筆)
==========================================
```

## 11. 後續可擴充方向
- ✅ 已實作：多來源容錯、列表頁 fallback、快速探測
- 🔄 進行中：開放資料 API 整合
- 將 selector 設定改為 Azure App Configuration 或 Key Vault 管理
- 增加人工審核 UI / Teams 通知
- 加入快照測試（HTML regression）與整合測試

## 12. HTML 結構變動容錯設計
- 每個來源採「多組 selector 候選」策略。
- selector 透過環境變數可熱調整。
- 程式內含 TODO 註解提醒：若來源 DOM 大改，優先調整 selector 與查詢參數。

## 13. 反偵測/Stealth 機制說明

本專案已預設全面啟用 Playwright + Stealth 反偵測強化層，顯著提升動態網頁抓取成功率，降低被封鎖/驗證碼機率。

### 13.1 功能亮點
- **瀏覽器指紋隱匿**：自動遮蔽 `navigator.webdriver`、plugins、languages、WebGL 等自動化特徵，並隨機選用真實桌面 Chrome 指紋組合。
- **人類行為模擬**：自動隨機捲動、滑鼠移動、hover/click、停留時間，避免機械式操作，並可於 `verify_stealth.py` 驗證。
- **Identity/Proxy 輪轉**：自動切換多組身份與 Proxy，降低單一來源被封鎖風險。
- **Session 持久化**：自動儲存/載入 cookies 與 localStorage，讓每次執行都像「回訪用戶」而非新機器人。
- **自適應請求節奏**：完全取代固定 sleep，改用 jitter、cooldown window、指數退避，降低異常流量偵測。
- **偵測事件記錄**：自動分類成功/封鎖/驗證碼/挑戰頁，失敗時自動截圖與 HTML 快照，便於除錯。

### 13.2 啟用方式
- **已預設啟用**（`STEALTH_ENABLED=true`），如需關閉可設 `STEALTH_ENABLED=false`。
- Proxy/identity 輪轉功能可於 `.env` 設定 `PROXY_ENABLED=true` 並填入 `PROXY_LIST`。
- 所有參數皆可於 `.env` 或 Azure App Settings 熱調整。

### 13.3 主要檔案結構
（見上方「專案結構」）

### 13.4 相關環境變數
- `STEALTH_ENABLED`：是否啟用反偵測（預設 true）
- `STEALTH_HUMAN_BEHAVIOR`：啟用人類行為模擬（預設 true）
- `STEALTH_SESSION_PERSISTENCE`：啟用 session 持久化
- `STEALTH_MAX_RETRIES`：失敗重試次數
- `STEALTH_THROTTLE_DELAY_MIN/MAX`：每次請求最小/最大間隔
- `STEALTH_THROTTLE_COOLDOWN_AFTER`：每 N 次請求後 cooldown
- `PROXY_ENABLED`、`PROXY_LIST`、`PROXY_STRATEGY`：Proxy 輪轉設定
## 14. 常見 Stealth 問題排解
- 若遇驗證碼/封鎖，建議：
  - 增加 Proxy/identity 組數，調整 `STEALTH_THROTTLE_DELAY_MAX` 增加間隔
  - 檢查 log 內 `batch_fetch_error`、`blocked`、`captcha` 訊息
  - 執行 `python verify_stealth.py` 驗證環境與參數
  - 如仍失敗，請參考 `STEALTH_MIGRATION_COMPLETE.md` 或聯絡維護者

詳細請見 `local.settings.json.example`。
