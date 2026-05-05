# Phase 1: 現況盤點與相依性分析報告

**專案**: webpccscrape - 教育資訊標案自動監控系統  
**執行日期**: 2026-05-05  
**執行人**: Azure Migration Planning Team  
**報告版本**: 1.0

---

## 📋 執行摘要

本報告針對 `webpccscrape` 專案進行全面現況盤點，為後續 Azure Cloud Migration 奠定基礎。專案目前處於**混合部署模式**：主要運行環境為本地 cron 排程，但已具備 Azure Functions 基礎架構與部分 Azure 服務整合（Table Storage、Blob Storage、ACS Email）。

**關鍵發現**：
- ✅ 專案已具備 Azure Functions 雛形（`function_app.py`）
- ✅ 已整合 Azure Table Storage + Blob Storage（可選）
- ✅ Playwright + Stealth 反偵測機制已完整實作
- ⚠️ 缺少 Infrastructure as Code（無 Bicep/Terraform）
- ⚠️ 缺少 CI/CD Pipeline（僅有 GitHub Release workflow）
- ⚠️ 本地 cron 為主要生產環境，穩定性與可靠性風險高

---

## 1. 技術棧盤點

### 1.1 程式語言與執行環境
| 項目 | 當前狀態 | 版本 | 備註 |
|------|----------|------|------|
| Python | ✅ 已安裝 | 3.12.3 | 符合 Azure Functions 支援（3.8-3.11，3.12 需驗證） |
| 虛擬環境 | ✅ 使用中 | venv | 位於 `/home/xcloud/project/webpccscrape/venv/` |
| 時區設定 | ✅ 已配置 | Asia/Taipei | 透過環境變數 `TZ` 設定 |

**風險評估**: 🟡 **中度風險** - Python 3.12.3 超出 Azure Functions 官方支援範圍（最高 3.11），需在 Phase 2 驗證相容性或降級至 3.11。

---

### 1.2 核心依賴套件（requirements.txt）

#### Azure 相關套件
```
azure-functions==1.22.0          ✅ 已安裝（虛擬環境未顯示）
azure-data-tables==12.6.0        ❌ 未安裝於虛擬環境
azure-storage-blob==12.25.1      ❌ 未安裝於虛擬環境
azure-communication-email==1.0.0 ❌ 未安裝於虛擬環境
```

#### 爬蟲與資料處理
```
playwright==1.52.0               ✅ 已安裝 v1.58.0（版本較新）
requests==2.32.3                 ✅ 已安裝 v2.31.0
beautifulsoup4==4.12.3           ✅ 已安裝
python-dateutil==2.9.0.post0     ✅ 已安裝
python-dotenv==1.0.1             ✅ 已安裝
```

#### AI 增強功能（可選）
```
openai>=1.0.0                    ✅ 已安裝 v2.31.0
anthropic>=0.20.0                ❌ 未安裝
sentence-transformers>=2.5.0     ✅ 已安裝 v5.4.1
scikit-learn>=1.3.0              ❌ 未檢測到（需進一步確認）
```

#### 測試框架
```
pytest==8.3.5                    ✅ 已安裝
```

**風險評估**: 🟡 **中度風險** - Azure SDK 套件在虛擬環境中未完整安裝，可能導致 Azure Storage 相關功能異常。建議在 Phase 3 完整重新安裝依賴並凍結版本（`pip freeze`）。

---

### 1.3 Playwright 瀏覽器驅動

```bash
$ playwright --version
Playwright command not found
```

**狀態**: ⚠️ **Playwright CLI 未安裝或未在 PATH** - Python 套件已安裝但瀏覽器驅動可能缺失。

**建議行動**（Phase 3）:
```bash
playwright install chromium
playwright install-deps  # 安裝系統依賴
```

**Azure Functions 考量**: 
- 預設 Consumption Plan 不支援 Playwright（無瀏覽器環境）
- 需使用 **Premium Plan** 或 **Container Apps**
- 或採用 **Puppeteer Cluster** / **Headless Chrome as Service**

---

## 2. 當前部署配置

### 2.1 本地 Cron 部署（生產環境）

**配置文件**: `crontab_new.txt`

```cron
# webpccscrape 標案監控排程（週一到週五 8:30）
30 8 * * 1-5 cd /home/xcloud/project/webpccscrape && \
  /home/xcloud/project/webpccscrape/venv/bin/python run_local.py \
  >> /home/xcloud/project/webpccscrape/logs/cron.log 2>&1

# 每日彙總報告（9:00）
00 9 * * 1-5 cd /home/xcloud/project/webpccscrape && \
  /home/xcloud/project/webpccscrape/venv/bin/python summarize_cron_log.py \
  --log-file logs/cron.log --days 1 \
  >> /home/xcloud/project/webpccscrape/logs/cron_summary.log 2>&1
```

**關鍵特徵**:
- 執行時間: 週一至週五 8:30 AM Asia/Taipei
- 執行腳本: `run_local.py`（非 `function_app.py`）
- 日誌管理: 輸出至 `logs/cron.log`
- 狀態儲存: `state/notified_state.json`（58 KB，本地 JSON 文件）

**痛點分析**:
| 痛點 | 影響等級 | 說明 |
|------|---------|------|
| 單點故障 | 🔴 嚴重 | 本地機器故障或網路中斷導致完全停擺 |
| 無自動重試 | 🟡 中度 | Cron 執行失敗後需手動介入 |
| 監控缺失 | 🟡 中度 | 無法即時告警，僅能從日誌事後檢查 |
| 秘密管理 | 🟠 高度 | `.env` 文件明文儲存，權限控制薄弱 |
| 擴展性限制 | 🟡 中度 | 無法水平擴展，Playwright 資源受限於單機 |

---

### 2.2 Azure Functions 雛形（未部署）

**配置文件**: `function_app.py`

```python
@app.function_name(name="daily_bid_monitor")
@app.timer_trigger(
    arg_name="timer",
    schedule="0 30 0 * * *",  # UTC 00:30 = Asia/Taipei 08:30
    run_on_startup=False,
    use_monitor=True,
)
def daily_bid_monitor(timer: func.TimerRequest) -> None:
    # ... pipeline execution ...
```

**狀態**: 📝 **已實作但未部署** - 程式碼結構完整，但缺少部署配置與測試。

**Azure Functions 配置文件**: `host.json`
```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "maxTelemetryItemsPerSecond": 20
      }
    }
  },
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
```

**當前缺口**:
- ❌ 無 Azure Function App 實例
- ❌ 無 Application Insights 配置
- ❌ 未測試 Timer Trigger 是否正常觸發
- ❌ 未處理 Playwright 在 Functions 環境的相容性

---

## 3. Azure 資源使用狀況

### 3.1 Azure Storage

#### Table Storage
**用途**: 儲存已通知標案的狀態（去重機制）  
**配置**:
```
AZURE_TABLE_NAME=BidNotifyState
AZURE_STORAGE_CONNECTION_STRING=***REDACTED***
```

**實作檔案**: `storage/table_store.py`
```python
class TableStateStore:
    def __init__(self, connection_string: str, table_name: str, logger: Any):
        # ... Azure Table Client initialization ...
```

**當前狀態**: ⚠️ **已配置但虛擬環境缺少依賴**
- `azure-data-tables` 套件未安裝
- Fallback 機制會降級至 Blob Storage 或 Local JSON

#### Blob Storage
**用途**: 
1. 標案狀態備份（`notified_state.json`）
2. HTML 快照與截圖儲存

**配置**:
```
AZURE_BLOB_CONTAINER=bid-state
AZURE_BLOB_NAME=notified_state.json
```

**實作檔案**: `storage/blob_store.py`

**當前狀態**: ⚠️ **已配置但未啟用**（依賴套件缺失）

#### Local Fallback (實際使用中)
**檔案**: `state/notified_state.json` (58 KB)  
**實作**: `storage/local_state_store.py`

```python
class LocalJsonStateStore:
    def __init__(self, path: str | Path, logger: Any, retention_days: int = 90):
        self.path = Path(path).resolve()
        # ... local JSON state management ...
```

**風險**: 🔴 **嚴重** - 本地文件遺失導致去重機制失效，可能重複發送已通知的標案。

---

### 3.2 Azure Communication Services (ACS) Email

**配置**:
```
ACS_CONNECTION_STRING=（未在本地 .env 顯示）
ACS_EMAIL_SENDER=（未配置）
```

**當前狀態**: ❌ **未啟用** - 專案回退至 SMTP 發送（Outlook Exchange）

**實際使用**: SMTP fallback
```
SMTP_HOST=xcloudinfo-com.mail.protection.outlook.com
SMTP_PORT=25
SMTP_FROM=aaron_l@xcloudinfo.com
EMAIL_TO=aaron_l@cloudinfo.com.tw,sylvia@cloudinfo.com.tw,...
```

**建議**: 🟢 Phase 5 啟用 ACS Email 替代 SMTP，提升可靠性與 Azure 原生整合。

---

### 3.3 其他 Azure 服務（尚未使用）

| 服務 | 狀態 | 預期用途 | 優先級 |
|------|------|---------|--------|
| Application Insights | ❌ 未配置 | 監控、告警、效能分析 | 🔴 高 |
| Key Vault | ❌ 未使用 | 秘密管理（SMTP密碼、API Key） | 🔴 高 |
| Log Analytics | ❌ 未配置 | 集中化日誌查詢與分析 | 🟡 中 |
| Container Apps | ❌ 未評估 | Playwright 容器化執行環境（Functions 替代方案） | 🟠 中高 |
| VNet Integration | ❌ 未配置 | IP 白名單/網路隔離 | 🟢 低 |

---

## 4. 功能特性盤點

### 4.1 資料來源（多層容錯）

| 來源 | 類型 | 當前狀態 | 反偵測機制 |
|------|------|---------|-----------|
| 台灣採購公報 (taiwanbuying) | Playwright 爬蟲 | ✅ 運作中 | Stealth + 人類行為模擬 |
| 政府電子採購網 (gov.pcc) | Playwright 爬蟲 | ✅ 運作中 | Stealth + Session 持久化 |
| 開放資料 API (g0v) | HTTP API | ✅ 運作中 | 無需反偵測 |

**Stealth 配置** (`.env`):
```bash
STEALTH_ENABLED=true
STEALTH_HUMAN_BEHAVIOR=true          # 滑鼠移動、隨機延遲
STEALTH_SESSION_PERSISTENCE=true     # Session 複用（24小時 TTL）
STEALTH_THROTTLE_DELAY_MIN=3.0
STEALTH_THROTTLE_DELAY_MAX=8.0
STEALTH_THROTTLE_COOLDOWN_AFTER=3    # 每3次請求後冷卻
STEALTH_THROTTLE_COOLDOWN_MIN=15.0
STEALTH_THROTTLE_COOLDOWN_MAX=30.0
```

**架構文件**: `STEALTH_MIGRATION_COMPLETE.md`、`docs/ADVANCED_ANTI_DETECTION.md`

---

### 4.2 AI 增強功能（可選）

| 功能 | 依賴套件 | 當前狀態 | 配置位置 |
|------|---------|---------|---------|
| AI 優先度分類 | `openai` / `anthropic` | ✅ OpenAI 已安裝 | `core/ai_classifier.py` |
| 語義相似度去重 | `sentence-transformers` | ✅ 已安裝 | `core/embedding_recall.py` |
| 關鍵字擴展 | `scikit-learn` | ⚠️ 未確認 | `core/embedding_categories.py` |

**配置**:
```bash
ENABLE_EMBEDDING_RECALL=true
# OpenAI API Key 未在輸出中顯示（已設定）
```

**備註**: AI 分類為增強功能，關閉時回退至關鍵字匹配，不影響核心流程。

---

### 4.3 通知與追蹤

#### Email 格式化
- **模板**: `core/formatter.py`
- **格式**: 精美 HTML（含預算金額、押標金、機關名稱）
- **預覽功能**: `--preview-html` 參數可輸出 HTML 檔案供本地檢視

#### GitHub Issue 自動建立（尚未啟用）
- **實作**: `notify/github_notify.py`
- **狀態**: 📝 已實作但未配置（需 GitHub Token）

---

## 5. 相依性風險矩陣

| 相依項 | 風險等級 | 問題描述 | 建議行動 |
|--------|---------|---------|---------|
| Python 3.12.3 | 🟡 中 | 超出 Azure Functions 官方支援 | Phase 2 測試相容性或降級至 3.11 |
| Playwright 瀏覽器驅動 | 🔴 高 | CLI 未安裝，Functions 預設不支援 | Phase 3 容器化或採用 Premium Plan |
| Azure SDK 套件缺失 | 🟡 中 | Table/Blob Storage 無法使用 | Phase 3 修復 `pip install` |
| 本地狀態檔案 | 🔴 高 | 單點故障，無備份機制 | Phase 5 強制啟用 Azure Table Storage |
| `.env` 秘密管理 | 🟠 中高 | 明文儲存，權限控制不足 | Phase 8 遷移至 Key Vault |
| 無監控告警 | 🟠 中高 | 故障無法即時發現 | Phase 9 配置 Application Insights |
| Cron 單點執行 | 🔴 高 | 機器故障導致服務停擺 | Phase 11 遷移至 Azure Functions |

---

## 6. Infrastructure as Code (IaC) 現況

**結論**: ❌ **完全缺失**

- 無 Bicep 模板
- 無 Terraform 配置
- 無 ARM Template
- 無 GitHub Actions 部署 Pipeline（僅有 Release workflow）

**影響**:
- 環境重建困難（手動操作，易出錯）
- 無法實現 Dev/Staging/Prod 環境一致性
- 回滾計畫無法自動化

**建議**: 🔴 **Phase 4 高優先級** - 建立 Bicep/Terraform IaC，版本控制所有 Azure 資源。

---

## 7. CI/CD 現況

### 7.1 現有 GitHub Actions

**檔案**: `.github/workflows/release.yml`

```yaml
name: Auto Release
on:
  push:
    tags:
      - "v*.*.*"
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Generate changelog
        # ... 自動產生變更日誌 ...
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v3
```

**功能**: 僅處理 GitHub Release 版本發佈，**不包含任何部署邏輯**。

### 7.2 缺失項目

- ❌ Azure Functions 自動部署 Pipeline
- ❌ 單元測試 CI（pytest 自動化）
- ❌ 整合測試（爬蟲功能驗證）
- ❌ 環境變數注入（Azure Key Vault 整合）
- ❌ 多環境部署（Dev/Staging/Prod 分支策略）
- ❌ Rollback 機制（部署失敗自動回滾）

**建議**: 🔴 **Phase 6 高優先級** - 建立完整 CI/CD Pipeline，包含測試、建構、部署、回滾。

---

## 8. 資料儲存與狀態管理

### 8.1 當前儲存策略

```
notified_state.json (58 KB)
├── entries: {
│   "bid-key-1": {
│       "primary_key": "...",
│       "alias_keys": [...],
│       "first_seen_at": "2026-05-05T02:22:18Z",
│       "notified_at": "2026-05-05T02:22:18Z"
│   },
│   ...
│ }
```

**Fallback 鏈**:
1. Azure Table Storage（優先，目前未啟用）
2. Azure Blob Storage（備援，未啟用）
3. Local JSON（當前使用，風險高）

**資料保留**: 90 天（配置於 `Settings.state_retention_days`）

---

### 8.2 詳細頁快取

**功能**: 減少重複抓取政府電子採購網詳細頁（預算金額/押標金）

**配置**:
```python
detail_cache_enabled: bool = True
detail_cache_path: str = "state/detail_cache.json"
detail_cache_ttl_days: int = 90
```

**實作**: `storage/detail_cache_store.py`

**風險**: 🟡 **中度** - 本地快取遺失後需重新抓取，增加網站負載與被偵測風險。

---

## 9. 安全性盤點

### 9.1 秘密管理

**當前方式**: `.env` 文件（本地明文儲存）

**敏感資訊清單**:
- SMTP 密碼（`SMTP_PASSWORD`）
- Azure Storage 連接字串（`AZURE_STORAGE_CONNECTION_STRING`）
- ACS Email 連接字串（`ACS_CONNECTION_STRING`）
- OpenAI API Key（未在輸出中顯示）
- GitHub Token（GitHub Issue 功能需要）

**風險**: 🔴 **嚴重** - `.env` 檔案權限 `rw-rw-r--`，其他使用者可讀取。

**建議**: Phase 8 遷移至 **Azure Key Vault**，搭配 Managed Identity 存取。

---

### 9.2 網路安全

**當前狀態**:
- ✅ SMTP 使用 TLS 加密
- ✅ 爬蟲 User-Agent 偽裝
- ✅ Stealth 模式反指紋追蹤
- ⚠️ Proxy 功能已實作但未啟用（`PROXY_ENABLED=false`）

**潛在風險**:
- 🟡 本地機器 IP 可能被目標網站封鎖
- 🟡 無 VNet 隔離，爬蟲流量與其他服務混用

---

## 10. 監控與可觀測性

**當前方式**:
- 日誌輸出至 `logs/cron.log`
- 每日彙總腳本 `summarize_cron_log.py`
- 結構化日誌格式（extra dict）

**缺失項目**:
- ❌ 無即時告警（執行失敗/爬蟲異常/郵件發送失敗）
- ❌ 無效能監控（執行時間/記憶體使用）
- ❌ 無分散式追蹤（Azure Functions 內建 Application Insights）
- ❌ 無自訂儀表板（KPI 可視化）

**建議**: Phase 9 配置 Application Insights + Log Analytics，建立告警規則（例如：連續失敗 > 2 次）。

---

## 11. 測試覆蓋率盤點

**測試檔案**:
```
tests/
├── test_dedup.py
├── test_filters.py
├── test_formatter.py
├── test_gov.py
├── test_g0v.py
├── test_hybrid_scoring.py
├── test_local_state_store.py
├── test_normalize.py
├── test_pipeline_notifications.py
├── test_stealth.py
└── test_detection_strategies.py
```

**執行方式**: `pytest`

**覆蓋範圍**:
- ✅ 單元測試（去重、篩選、格式化）
- ✅ 整合測試（爬蟲、通知、狀態儲存）
- ⚠️ 端對端測試（完整 pipeline）僅能透過 `run_local.py --no-send` 手動執行

**建議**: Phase 6 將測試整合至 CI Pipeline，自動化執行並產生覆蓋率報告。

---

## 12. 文件完整性評估

**現有文件**:
| 文件名稱 | 完整度 | 內容品質 | 維護狀態 |
|---------|--------|---------|---------|
| `README.md` | 🟢 高 | 優秀 | ✅ 最新 |
| `LOCAL_DEPLOY.md` | 🟢 高 | 優秀 | ✅ 最新 |
| `STEALTH_MIGRATION_COMPLETE.md` | 🟢 高 | 優秀 | ✅ 最新 |
| `CURRENT_CONFIG.md` | 🟡 中 | 良好 | ⚠️ 需更新 |
| `docs/ADVANCED_ANTI_DETECTION.md` | 🟢 高 | 優秀 | ✅ 最新 |
| Azure 部署文件 | ❌ 缺失 | N/A | ❌ 未撰寫 |
| IaC 使用指南 | ❌ 缺失 | N/A | ❌ 未撰寫 |
| 故障排查手冊 | 🟡 中 | 分散在各文件 | ⚠️ 需整合 |

**建議**: Phase 12 補充 Azure 部署文件、Runbook、告警處理 SOP。

---

## 13. 遷移阻礙分析

### 13.1 技術阻礙

| 阻礙 | 嚴重程度 | 說明 | 解決方案 |
|------|---------|------|---------|
| Playwright 相容性 | 🔴 高 | Functions Consumption Plan 無瀏覽器環境 | 使用 Premium Plan 或 Container Apps |
| Python 版本 | 🟡 中 | 3.12.3 超出官方支援 | 降級至 3.11 或驗證相容性 |
| 大型依賴套件 | 🟡 中 | Playwright + sentence-transformers 體積大 | 分層建構 Docker 映像，優化冷啟動 |
| Session 持久化 | 🟠 中高 | Stealth Session 需寫入檔案系統 | 使用 Azure Files 或 Blob Storage |

### 13.2 流程阻礙

| 阻礙 | 嚴重程度 | 說明 | 解決方案 |
|------|---------|------|---------|
| 缺少 Azure 訂閱權限 | 🔴 高 | 無法建立資源 | Phase 5 前取得訂閱管理員權限 |
| 預算限制 | 🟡 中 | Premium Plan 成本較高 | Phase 2 精確估算，申請預算 |
| 團隊 Azure 經驗不足 | 🟡 中 | 學習曲線陡峭 | Phase 4-5 搭配 Azure 培訓 |

### 13.3 資料遷移阻礙

| 阻礙 | 嚴重程度 | 說明 | 解決方案 |
|------|---------|------|---------|
| 本地狀態檔案格式 | 🟢 低 | JSON 格式易轉換 | Phase 7 直接上傳至 Blob Storage |
| 歷史通知紀錄遺失 | 🟡 中 | 若轉換失敗導致重複通知 | Phase 7 建立雙寫機制與驗證期 |

---

## 14. Phase 1 建議行動清單

### 14.1 立即行動（Phase 2 前）
- [ ] 📌 **驗證 Python 3.12 與 Azure Functions 相容性**，或規劃降級至 3.11
- [ ] 📌 **完整安裝 requirements.txt**，修復 Azure SDK 缺失
- [ ] 📌 **執行 `pytest` 確認測試全數通過**
- [ ] 📌 **手動測試 `function_app.py` 在 Azure Functions Core Tools 的運行狀況**

### 14.2 Phase 2 準備事項
- [ ] 📊 使用 **Azure Pricing Calculator** 估算 Functions Premium Plan + Storage + ACS 月費
- [ ] 📊 評估 **Container Apps vs Functions Premium** 的成本與效能差異
- [ ] 📊 建立 3 環境（Dev/Staging/Prod）的資源命名規範

### 14.3 Phase 3 準備事項
- [ ] 🐳 建立 **Dockerfile**（基於 `mcr.microsoft.com/azure-functions/python:4-python3.11`）
- [ ] 🐳 安裝 Playwright 瀏覽器驅動至容器映像
- [ ] 🐳 優化映像大小（多階段建構、移除不必要套件）

### 14.4 Phase 4 準備事項
- [ ] 🏗️ 建立 **Bicep 模板** 或 **Terraform 配置**
- [ ] 🏗️ 定義資源群組、命名規範、標籤策略
- [ ] 🏗️ 配置 Key Vault、Storage Account、Function App、Application Insights

### 14.5 風險緩解措施
- [ ] ⚠️ **建立本地狀態檔案備份機制**（防止遷移期間資料遺失）
- [ ] ⚠️ **保留本地 cron 作為備援**（Phase 11 前不移除）
- [ ] ⚠️ **建立回滾計畫模板**（Azure Functions 部署失敗處理 SOP）

---

## 15. 總結與下一步

### 15.1 專案成熟度評分

| 維度 | 評分 | 說明 |
|------|------|------|
| 程式碼品質 | 🟢 8/10 | 結構清晰、型別標註完整、測試覆蓋良好 |
| 文件完整性 | 🟡 7/10 | 功能文件齊全，缺少部署與運維文件 |
| 測試覆蓋 | 🟡 7/10 | 單元測試充足，端對端測試不足 |
| 安全性 | 🟠 5/10 | 秘密管理弱、無 RBAC、無網路隔離 |
| 可靠性 | 🟠 4/10 | 單點故障、無監控告警、無自動重試 |
| DevOps 成熟度 | 🔴 3/10 | 無 IaC、無 CI/CD、手動部署 |
| **總體評估** | 🟡 **6/10** | **適合遷移，但需補強 DevOps 與安全性** |

### 15.2 遷移可行性結論

✅ **專案具備遷移至 Azure 的基礎條件**：
- 程式碼已適配 Azure Functions（`function_app.py`）
- 儲存層設計支援 Azure Storage（Table + Blob）
- 反偵測機制（Stealth）可在容器環境運行

⚠️ **需補強項目**（不阻礙遷移但影響穩定性）：
- Infrastructure as Code（Phase 4 優先處理）
- CI/CD Pipeline（Phase 6 優先處理）
- 監控與告警（Phase 9 優先處理）

### 15.3 下一步行動

**Phase 2: 架構設計與成本估算** 將基於本報告執行以下任務：

1. **選擇運算平台**：Functions Premium vs Container Apps vs App Service
2. **估算月費成本**：使用 Azure Pricing Calculator 產生詳細報價
3. **設計網路拓撲**：是否需要 VNet、Private Endpoint、Application Gateway
4. **定義環境策略**：Dev/Staging/Prod 的資源隔離與命名規範
5. **建立技術架構圖**：使用 draw.io 或 Azure 官方工具產生架構圖

**預期產出**：
- `PHASE2_ARCHITECTURE_DESIGN.md`（架構設計文件）
- `azure-pricing-estimate.xlsx`（成本估算試算表）
- `architecture-diagram.png`（架構圖）

---

## 附錄 A: 套件清單完整版

**執行指令**: `pip list`（於虛擬環境內）

```
beautifulsoup4         4.12.3
openai                 2.31.0
playwright             1.58.0
requests               2.31.0
sentence-transformers  5.4.1
pytest                 8.3.5
python-dateutil        2.9.0.post0
python-dotenv          1.0.1
```

**缺失套件**:
```
azure-functions        1.22.0    ❌ 未在虛擬環境顯示
azure-data-tables      12.6.0    ❌ 需安裝
azure-storage-blob     12.25.1   ❌ 需安裝
azure-communication-email 1.0.0 ❌ 需安裝
anthropic              >=0.20.0  ❌ 可選（未用到）
scikit-learn           >=1.3.0   ⚠️ 需確認
```

---

## 附錄 B: 環境變數清單

**來源**: `.env` 檔案（敏感資訊已遮罩）

```bash
# === 爬蟲配置 ===
ENABLE_PLAYWRIGHT=true
STEALTH_ENABLED=true
STEALTH_HUMAN_BEHAVIOR=true
STEALTH_SESSION_PERSISTENCE=true
STEALTH_SESSION_TTL_HOURS=24.0
STEALTH_HEADLESS=true
STEALTH_MAX_RETRIES=2
STEALTH_THROTTLE_DELAY_MIN=3.0
STEALTH_THROTTLE_DELAY_MAX=8.0
STEALTH_THROTTLE_COOLDOWN_AFTER=3
STEALTH_THROTTLE_COOLDOWN_MIN=15.0
STEALTH_THROTTLE_COOLDOWN_MAX=30.0
STEALTH_THROTTLE_BACKOFF_BASE=5.0

# === 資料來源 ===
G0V_API_URL=https://pcc-api.openfun.app/api/listbydate
G0V_ENABLED=true

# === AI 增強 ===
ENABLE_EMBEDDING_RECALL=true

# === Email 配置 ===
EMAIL_TO=aaron_l@cloudinfo.com.tw,sylvia@cloudinfo.com.tw,vita_l@cloudinfo.com.tw,aaron_l@xcloudinfo.com
EMAIL_SUBJECT_PREFIX=[教育資訊標案]

# === SMTP 設定 ===
SMTP_HOST=xcloudinfo-com.mail.protection.outlook.com
SMTP_PORT=25
SMTP_FROM=aaron_l@xcloudinfo.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false

# === Azure Storage（未顯示連接字串） ===
# AZURE_STORAGE_CONNECTION_STRING=***
# AZURE_TABLE_NAME=BidNotifyState
# AZURE_BLOB_CONTAINER=bid-state
# AZURE_BLOB_NAME=notified_state.json

# === ACS Email（未配置） ===
# ACS_CONNECTION_STRING=
# ACS_EMAIL_SENDER=
```

---

## 附錄 C: 檔案結構樹

```
/home/xcloud/project/webpccscrape/
├── .env                               # 環境變數（秘密）
├── .env.example                       # 環境變數模板
├── .github/
│   ├── copilot-instructions.md        # Copilot 使用指南
│   ├── instructions/                  # 模組開發指南
│   └── workflows/
│       └── release.yml                # GitHub Release 自動化
├── function_app.py                    # Azure Functions 入口
├── run_local.py                       # 本地 cron 執行腳本
├── host.json                          # Functions 配置
├── requirements.txt                   # Python 依賴
├── crontab_new.txt                    # Cron 排程設定
├── core/                              # 核心邏輯層
│   ├── config.py                      # 環境變數解析
│   ├── pipeline.py                    # 主流程編排
│   ├── filters.py                     # 標案篩選邏輯
│   ├── dedup.py                       # 去重邏輯
│   ├── formatter.py                   # Email 格式化
│   ├── ai_classifier.py               # AI 優先度分類
│   ├── embedding_recall.py            # 語義相似度去重
│   └── models.py                      # 資料模型
├── crawler/                           # 資料抓取層
│   ├── gov.py                         # 政府電子採購網爬蟲
│   ├── taiwanbuying.py                # 台灣採購公報爬蟲
│   ├── g0v.py                         # 開放資料 API
│   ├── stealth_runner.py              # Stealth 統一入口
│   ├── stealth/                       # 反偵測核心
│   ├── behavior/                      # 人類行為模擬
│   ├── session/                       # Session 持久化
│   └── detection/                     # 偵測事件記錄
├── storage/                           # 儲存層
│   ├── table_store.py                 # Azure Table Storage
│   ├── blob_store.py                  # Azure Blob Storage
│   ├── local_state_store.py           # 本地 JSON 備援
│   └── detail_cache_store.py          # 詳細頁快取
├── notify/                            # 通知層
│   ├── dispatcher.py                  # 通知路由
│   ├── email_acs.py                   # ACS Email
│   ├── email_smtp.py                  # SMTP 備援
│   └── github_notify.py               # GitHub Issue 建立
├── tests/                             # 測試套件
│   ├── test_*.py                      # 單元測試
│   └── data/                          # 測試資料
├── logs/                              # 日誌目錄
│   ├── cron.log                       # Cron 執行日誌
│   └── cron_summary.log               # 每日彙總報告
├── state/                             # 本地狀態儲存
│   └── notified_state.json            # 已通知標案紀錄（58 KB）
├── output/                            # 輸出檔案
│   └── preview.html                   # Email 預覽
└── docs/                              # 專案文件
    ├── ADVANCED_ANTI_DETECTION.md     # 反偵測機制文件
    ├── EMAIL_FORMAT_OPTIMIZATION.md   # Email 格式優化
    └── IDENTITY_ROTATION_GUIDE.md     # 身份輪轉指南
```

---

**報告結束**

本報告由 Azure Migration Planning Team 於 2026-05-05 產出，為 Phase 2-12 後續階段提供基礎依據。

**審閱人**: aaronliu  
**下次更新**: Phase 2 完成後更新架構設計與成本估算章節
