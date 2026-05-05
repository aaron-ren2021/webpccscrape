# Azure Container Apps Jobs 遷移計劃

**更新日期**：2026-05-05  
**目標**：從 Azure Functions 遷移到 Azure Container Apps Jobs，保持本地 cron 雙軌備援

---

## 🎯 架構決策

### 首選方案：Azure Container Apps Jobs（最佳實踐補強）


```
GitHub Actions
  ↓
Build Docker Image (Playwright 版本鎖定)
  ↓
Azure Container Registry（ACR，建議正式用 managed identity，開發可用 ghcr 省成本）
  ↓
Azure Container Apps Job
  ├─ Schedule: Mon-Fri 08:30 Asia/Taipei (UTC 00:30)
  ├─ Runtime: Python + Playwright + Chromium (版本一致)
  ├─ Logs: stdout → Log Analytics（JSON 結構化）
  ├─ Retry: 1~2 次
  ├─ Manual trigger: 可手動補跑
  └─ Image tag: commit SHA（production 不用 always latest）

State / Data
  ├─ Azure Table Storage：notified state（staging/prod 分離）
  ├─ Azure Blob Storage：HTML snapshot、截圖、state backup（staging/prod 分離）
  └─ 本地 JSON：只保留為開發或緊急 fallback

Secrets
  ├─ Azure Key Vault
  └─ Managed Identity 授權讀取

Monitoring
  ├─ Log Analytics（查 log 與 execution 狀態）
  ├─ Azure Monitor Alert（log/error/無執行紀錄/exit code）
  └─ Email / Teams 告警
```

### 為何選擇 Container Apps Jobs？

| 考量 | Azure Functions Premium | **Container Apps Jobs** |
|------|-------------------------|-------------------------|
| **排程模式** | ⚠️ Timer Trigger（冷啟動風險） | ✅ Cron-based scheduled job（最接近現狀） |
| **Playwright 支援** | ⚠️ 需 Premium Plan + 複雜設定 | ✅ 任意 Docker image，完整 Chromium |
| **執行模式** | ⚠️ Serverless（timeout 限制） | ✅ 長時間任務友善（可配置 timeout） |
| **成本** | ⚠️ Premium Plan 固定費用高 | ✅ 只在執行時計費（估算較優） |
| **日誌** | ⚠️ Application Insights 強制綁定 | ✅ Log Analytics（更靈活） |
| **手動觸發** | ⚠️ 需透過 Portal/API | ✅ 內建 manual trigger |
| **執行歷史** | ⚠️ 有限 | ✅ 完整 execution history |
| **狀態管理** | 兩者相同（Table/Blob） | 兩者相同（Table/Blob） |

**結論**：Container Apps Jobs 更符合「定時批次任務」特性，省成本且易維護。

---

## 📋 雙軌漸進式遷移（4 階段）

### Phase A：本地容器化（Docker first）

**目標**：讓服務在 Docker 容器內穩定運行，不依賴雲端

#### 1. 創建 Dockerfile

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
  TZ=Asia/Taipei

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "run_local.py"]
```

#### 2. 創建 .dockerignore

```
.env
.env.example
#### 3. 本地測試
```
.env
venv/
__pycache__/
*.pyc
.pytest_cache/
.git/
.github/
logs/
output/
state/notified_state.json
docs/
```bash
```
# 建立映像檔
docker build -t webpccscrape:dev .

# 測試執行（不寄信，僅產生預覽）
docker run --rm \
  --env-file .env \
  -v $(pwd)/output:/app/output \
  webpccscrape:dev \
  python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state

# 完整執行（實際寄信，使用 Azure Storage）
docker run --rm --env-file .env webpccscrape:dev
```

#### 4. 調整程式碼

- ✅ **日誌輸出 stdout**：所有 `logging` 輸出到 console，移除 file handler，建議 JSON 格式（方便 Log Analytics 查詢）
- ✅ **優先使用 Azure Storage**：`storage/` fallback 順序為 Table → Blob → Memory，且 staging/prod 分離
- ✅ **Playwright 瀏覽器確認**：測試 Chromium 在容器內可正常啟動
- ✅ **環境變數驗證**：啟動時檢查必要變數，缺少時提前失敗
- ✅ **狀態遷移腳本**：提供 `state/notified_state.json` 匯入 Table Storage 工具

**完成條件**：
- [ ] Dockerfile 建立並通過本地測試
- [ ] Playwright + Chromium 在容器內可執行
- [ ] 所有 pytest 通過（Table/Blob storage/staging/prod 分離）
- [ ] 日誌輸出 JSON 格式到 stdout
- [ ] 狀態遷移腳本可用

---

### Phase B：上 Azure Container Apps Jobs（測試環境）

**目標**：將容器部署到 Azure，但不發送正式通知

#### 1. 建立 Azure 資源

```bash
# 設定變數
RG="rg-webpccscrape-prod"
LOCATION="japaneast"
ACR_NAME="acrwebpccscrape"
ENV_NAME="env-webpccscrape"
JOB_NAME="job-bid-monitor-staging"

# 建立資源群組
az group create --name $RG --location $LOCATION

# 建立 Container Registry
az acr create --resource-group $RG --name $ACR_NAME --sku Basic --admin-enabled true

# 建立 Container Apps Environment（with Log Analytics）
az containerapp env create \
  --name $ENV_NAME \
  --resource-group $RG \
  --location $LOCATION \
  --logs-destination log-analytics

# 建立 Key Vault
az keyvault create --name kv-webpccscrape --resource-group $RG --location $LOCATION

# 上傳 secrets
az keyvault secret set --vault-name kv-webpccscrape --name smtp-username --value "your-email@outlook.com"
az keyvault secret set --vault-name kv-webpccscrape --name smtp-password --value "your-app-password"
az keyvault secret set --vault-name kv-webpccscrape --name openai-api-key --value "sk-..."
```

#### 2. 建立 GitHub Actions Workflow

`.github/workflows/deploy-staging.yml`:

```yaml
name: Deploy to Azure Container Apps (Staging)

on:
  workflow_dispatch:  # 手動觸發
  push:
    branches: [develop]

env:
  ACR_NAME: acrwebpccscrape
  IMAGE_NAME: webpccscrape

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Login to ACR
        uses: azure/docker-login@v1
        with:
          login-server: ${{ env.ACR_NAME }}.azurecr.io
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}
      
      - name: Build and Push
        run: |
          docker build -t ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }} .
          docker tag ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }} \
                     ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:staging
          docker push ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }}
          docker push ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:staging
      
      - name: Deploy to Container Apps Job
        uses: azure/container-apps-deploy-action@v1
        with:
          acrName: ${{ env.ACR_NAME }}
          containerAppName: job-bid-monitor-staging
          resourceGroup: rg-webpccscrape-prod
          imageToDeploy: ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }}
```

#### 3. 建立 Container Apps Job（Staging）

```bash
# 取得 ACR 密碼
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

# 建立 staging job（使用測試收件人）
az containerapp job create \
  --name $JOB_NAME \
  --resource-group $RG \
  --environment $ENV_NAME \
  --trigger-type "Schedule" \
  --cron-expression "30 0 * * 1-5" \
  --replica-timeout 1800 \
  --replica-retry-limit 1 \
  --image "$ACR_NAME.azurecr.io/webpccscrape:staging" \
  --registry-server "$ACR_NAME.azurecr.io" \
  --registry-username $ACR_NAME \
  --registry-password $ACR_PASSWORD \
  --cpu 1.0 \
  --memory 2.0Gi \
  --secrets \
    smtp-username=keyvaultref:https://kv-webpccscrape.vault.azure.net/secrets/smtp-username,identityref:system \
    smtp-password=keyvaultref:https://kv-webpccscrape.vault.azure.net/secrets/smtp-password,identityref:system \
  --env-vars \
    "EMAIL_TO=your-test-email@example.com" \
    "SMTP_USERNAME=secretref:smtp-username" \
    "SMTP_PASSWORD=secretref:smtp-password" \
    "AZURE_STORAGE_CONNECTION_STRING=..." \
    "LOG_LEVEL=INFO"
```

#### 4. 測試驗證（與本地 cron 並行 1-2 週）

| 檢查項目 | 本地 Cron | Azure Job | 比對結果 |
|---------|-----------|-----------|---------|
| 每日標案數 | 1600+ | ? | ✅ / ❌ |
| 篩選後筆數 | 12-18 | ? | ✅ / ❌ |
| 去重準確度 | 100% | ? | ✅ / ❌ |
| AI 分類成功率 | 95%+ | ? | ✅ / ❌ |
| 執行時間 | 60-90s | ? | ✅ / ❌ |
| 錯誤率 | 0% | ? | ✅ / ❌ |

**完成條件**：
- [ ] staging job 連續 7 天無失敗
- [ ] 每日抓取數量與本地一致（±5%）
- [ ] 去重狀態與本地同步（無重複通知，staging/prod state 隔離）
- [ ] Log Analytics 查詢正常（log/error/無執行紀錄/exit code）

---

### Phase C：正式切換通知，保留本地備援

**目標**：Azure 成為主要系統，本地降為 dry-run 備援

#### 1. 建立 Production Job

```bash
# 複製 staging job 設定，調整為正式收件人
az containerapp job create \
  --name job-bid-monitor-prod \
  --resource-group $RG \
  --environment $ENV_NAME \
  --trigger-type "Schedule" \
  --cron-expression "30 0 * * 1-5" \
  --replica-timeout 1800 \
  --replica-retry-limit 2 \
  --image "$ACR_NAME.azurecr.io/webpccscrape:latest" \
  --registry-server "$ACR_NAME.azurecr.io" \
  --registry-username $ACR_NAME \
  --registry-password $ACR_PASSWORD \
  --cpu 1.0 \
  --memory 2.0Gi \
  --secrets \
    smtp-username=keyvaultref:https://kv-webpccscrape.vault.azure.net/secrets/smtp-username,identityref:system \
    smtp-password=keyvaultref:https://kv-webpccscrape.vault.azure.net/secrets/smtp-password,identityref:system \
  --env-vars \
    "EMAIL_TO=實際收件人清單" \
    "SMTP_USERNAME=secretref:smtp-username" \
    "SMTP_PASSWORD=secretref:smtp-password" \
    "AZURE_STORAGE_CONNECTION_STRING=..." \
    "LOG_LEVEL=INFO"
```

#### 2. 設定 Azure Monitor Alert

```bash
# 建立 Action Group（寄信通知失敗）
az monitor action-group create \
  --name ag-bid-monitor-alert \
  --resource-group $RG \
  --short-name bidAlert \
  --email-receiver name=admin email=admin@example.com

# 建立 Alert Rule（job 執行失敗時觸發）
az monitor scheduled-query create \
  --name "Bid Monitor Job Failed" \
  --resource-group $RG \
  --scopes $(az containerapp env show -n $ENV_NAME -g $RG --query id -o tsv) \
  --condition "count > 0" \
  --condition-query "ContainerAppConsoleLogs_CL | where ContainerAppName_s == 'job-bid-monitor-prod' | where Log_s contains 'ERROR' | where TimeGenerated > ago(2h)" \
  --description "標案監控 Job 執行失敗或出現錯誤" \
  --evaluation-frequency 1h \
  --window-size 2h \
  --severity 2 \
  --action-groups $(az monitor action-group show -n ag-bid-monitor-alert -g $RG --query id -o tsv)
```

#### 3. 調整本地 Crontab（改為 dry-run）

```bash
# 編輯 crontab
crontab -e

# 修改為 dry-run 模式（不寄信，僅記錄）
35 8 * * 1-5 cd /home/xcloud/project/webpccscrape && source venv/bin/activate && python run_local.py --no-send --preview-html ./output/backup_preview.html >> logs/cron_backup.log 2>&1
```

#### 4. Rollback SOP（緊急回退程序）

**觸發條件**：Azure job 連續 2 天失敗或 execution 無紀錄

```bash
# 1. 立即恢復本地 cron 正式寄信
crontab -e
# 移除 --no-send 參數

# 2. 停用 Azure job
az containerapp job update \
  --name job-bid-monitor-prod \
  --resource-group $RG \
  --set properties.configuration.triggerType=Manual

# 3. 調查失敗原因（檢查 Log Analytics/execution history）
az containerapp job execution list \
  --name job-bid-monitor-prod \
  --resource-group $RG \
  --output table

# 4. 修復後重新啟用
az containerapp job update \
  --name job-bid-monitor-prod \
  --resource-group $RG \
  --set properties.configuration.triggerType=Schedule
```

**完成條件**：
- [ ] production job 連續 14 天穩定運行
- [ ] 收件人未回報遺漏或重複通知
- [ ] 本地 dry-run 與雲端結果一致
- [ ] Alert 正常運作（人工觸發測試，log/error/無執行紀錄/exit code）
---

## Go / No-Go 檢查表（正式切換前必檢）

| 檢查項              | Go 條件                   |
| ---------------- | ----------------------- |
| Docker dry-run   | 連續 5 次成功                |
| Staging job      | 連續 7 個工作天成功             |
| Playwright crash | 0 次或 retry 後成功          |
| 抓取數量             | 與本地差異 ±5%               |
| 去重狀態             | 無重複通知                   |
| Email            | 測試收件成功                  |
| Key Vault        | 不再使用明文 secrets          |
| Log Analytics    | 可查完整 execution          |
| Alert            | 人工觸發測試成功                |
| Rollback         | 本地 cron 可在 15 分鐘內恢復正式寄信 |
---

## Log 結構化範例與 Alert 條件

建議所有 pipeline log 輸出 JSON 結構，方便 Log Analytics 查詢與 alert：

```json
{
  "event": "pipeline_completed",
  "env": "prod",
  "source_count": 1680,
  "filtered_count": 16,
  "notified_count": 4,
  "duplicate_count": 12,
  "duration_seconds": 87,
  "status": "success"
}
```

**Alert 條件建議**：
- Job failed（execution failed 或 exit code != 0）
- 無執行紀錄（工作日 09:00 後沒有 execution）
- ERROR log（2 小時內出現 ERROR）
- 抓取筆數異常（今日總筆數低於近 7 日均值 50%）
- Email 發送失敗（SMTP / ACS 發送失敗）

---

### Phase D：補齊 IaC 與 CI/CD

**目標**：所有基礎設施即程式碼，可快速重建環境

#### 1. 建立 Bicep/Terraform 範本

選擇一：**Bicep**（Azure 原生，推薦）

`infra/main.bicep`:

```bicep
param location string = 'japaneast'
param envName string = 'prod'

// Container Registry
resource acr 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: 'acrwebpccscrape${envName}'
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// Container Apps Environment
resource env 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: 'env-webpccscrape-${envName}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// Container Apps Job
resource job 'Microsoft.App/jobs@2023-05-01' = {
  name: 'job-bid-monitor-${envName}'
  location: location
  properties: {
    environmentId: env.id
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: '30 0 * * 1-5'
        parallelism: 1
        replicaCompletionCount: 1
      }
      replicaTimeout: 1800
      replicaRetryLimit: 2
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        // ... 其他 secrets
      ]
    }
    template: {
      containers: [
        {
          name: 'bid-monitor'
          image: '${acr.properties.loginServer}/webpccscrape:latest'
          resources: {
            cpu: 1
            memory: '2Gi'
          }
          env: [
            // ... 環境變數
          ]
        }
      ]
    }
  }
}

// ... Log Analytics, Key Vault, Storage Account, Alerts
```

部署：

```bash
az deployment group create \
  --resource-group rg-webpccscrape-prod \
  --template-file infra/main.bicep \
  --parameters envName=prod
```

#### 2. 完整 CI/CD Pipeline

`.github/workflows/deploy-prod.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  AZURE_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
  RESOURCE_GROUP: rg-webpccscrape-prod

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium
      - name: Run tests
        run: pytest --cov=. --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    outputs:
      image-tag: ${{ steps.meta.outputs.tags }}
    steps:
      - uses: actions/checkout@v4
      - name: Login to ACR
        uses: azure/docker-login@v1
        with:
          login-server: acrwebpccscrape.azurecr.io
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}
      - name: Docker meta
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: acrwebpccscrape.azurecr.io/webpccscrape
          tags: |
            type=sha,prefix=,format=long
            type=raw,value=latest
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=registry,ref=acrwebpccscrape.azurecr.io/webpccscrape:cache
          cache-to: type=registry,ref=acrwebpccscrape.azurecr.io/webpccscrape:cache,mode=max

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Update Container App Job
        run: |
          az containerapp job update \
            --name job-bid-monitor-prod \
            --resource-group ${{ env.RESOURCE_GROUP }} \
            --image ${{ needs.build-and-push.outputs.image-tag }} \
            --revision-suffix $(date +%Y%m%d-%H%M%S)
      - name: Trigger test execution
        run: |
          az containerapp job start \
            --name job-bid-monitor-prod \
            --resource-group ${{ env.RESOURCE_GROUP }}
```

#### 3. 文檔補完

- [ ] **RUNBOOK.md**：維運手冊（查日誌、手動觸發、troubleshooting）
- [ ] **COST_ANALYSIS.md**：每月成本追蹤與優化建議
- [ ] **SECURITY.md**：安全性檢查清單（Key Vault 存取、RBAC、網路規則）

**完成條件**：
- [ ] Bicep/Terraform 可完整重建環境
- [ ] CI/CD pipeline 包含測試、建置、部署
- [ ] 文檔完整，新人可依文檔部署

---

## 💰 成本估算（需使用 Azure Pricing Calculator）

### Container Apps Jobs

| 項目 | 規格 | 單價 | 每月用量 | 月費用 |
|------|------|------|---------|--------|
| vCPU (Japan East) | 1 vCPU | ~$0.000012/vCPU-second | ~90 秒/天 × 22 天 = 1980 秒 | $0.02 |
| Memory | 2 GiB | ~$0.0000013/GiB-second | 1980 秒 × 2 GiB | $0.005 |
| **小計** | | | | **$0.03/月** ✅ |

### Azure Container Registry

| SKU | 儲存空間 | 月費用 |
|-----|---------|--------|
| Basic | 10 GiB 內 | $5.00 |

### Azure Storage Account

| 服務 | 用量 | 月費用 |
|------|------|--------|
| Table Storage | 100 MB 熱層 | $0.01 |
| Blob Storage | 500 MB (snapshots) | $0.02 |
| **小計** | | **$0.03/月** |

### Log Analytics

| 項目 | 用量 | 月費用 |
|------|------|--------|
| 資料擷取 | < 5 GB/月（每天 ~50 MB） | 免費額度內 |
| 資料保留 | 31 天 | 免費額度內 |
| **小計** | | **$0/月** ✅ |

### Key Vault

| 項目 | 用量 | 月費用 |
|------|------|--------|
| Secret operations | < 10,000 次/月 | 免費額度內 |

### **總計估算**

```
Container Apps Jobs:   $0.03
Container Registry:    $5.00
Storage Account:       $0.03
Log Analytics:         $0.00
Key Vault:             $0.00
Azure Monitor Alerts:  $0.10 (email action)
─────────────────────────────
總計:                  ~$5.16 USD/月
```

**💡 成本優化建議**：
1. **降低 ACR 成本**：改用 GitHub Container Registry（免費）
2. **Log 保留期**：縮短到 7 天（減少儲存費用）
3. **開發環境**：使用 Manual trigger，避免排程執行

---

## 📊 Phase 進度追蹤

| Phase | 狀態 | 開始日期 | 完成日期 | 備註 |
|-------|------|---------|---------|------|
| **A: 本地容器化** | ⏳ 待開始 | - | - | 建立 Dockerfile + 本地測試 |
| **B: Azure 測試環境** | ⏳ 待開始 | - | - | staging job + 測試收件人 |
| **C: 正式切換** | ⏳ 待開始 | - | - | production job + 本地備援 |
| **D: IaC & CI/CD** | ⏳ 待開始 | - | - | Bicep + GitHub Actions |

---

## 🎯 下一步行動

### 立即可開始（Phase A）

```bash
# 1. 建立 Dockerfile
cat > Dockerfile << 'EOF'
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "run_local.py"]
EOF

# 2. 建立 .dockerignore
cat > .dockerignore << 'EOF'
.env
venv/
__pycache__/
*.pyc
logs/*.log
output/*.html
state/notified_state.json
docs/
tests/
EOF

# 3. 本地測試
docker build -t webpccscrape:dev .
docker run --rm --env-file .env -v $(pwd)/output:/app/output \
  webpccscrape:dev python run_local.py --no-send --preview-html ./output/preview.html
```

### 需準備資料（Phase B）

- [ ] Azure 訂閱 ID
- [ ] 決定 Resource Group 名稱和 region
- [ ] 確認 ACR 名稱可用性（全域唯一）
- [ ] 準備測試收件人 email

### 需決策事項

1. **是否使用 Bicep 或 Terraform？**  
   建議：**Bicep**（Azure 原生，學習曲線低）

2. **是否保留 Azure Functions？**  
   建議：**Phase C 後退役**（避免雙重維護）

3. **Log 保留期限？**  
   建議：**31 天**（成本影響小，debug 友善）

4. **是否需要 Application Insights？**  
   建議：**使用 Log Analytics 即可**（成本更低）

---

## 📚 相關文件

- [Azure Container Apps Jobs 官方文檔](https://learn.microsoft.com/azure/container-apps/jobs)
- [Playwright Docker 映像檔](https://playwright.dev/docs/docker)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
- [Container Apps Job CLI](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest)
- [Manage secrets in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Microsoft Artifact Registry](https://mcr.microsoft.com/en-us/product/playwright/python/about)
- [LOCAL_DEPLOY.md](./LOCAL_DEPLOY.md)
- [SYSTEM_STATUS.md](./SYSTEM_STATUS.md)
- [STEALTH_MIGRATION_COMPLETE.md](./STEALTH_MIGRATION_COMPLETE.md)
- [RUNBOOK.md]（建議補齊）
- [COST_ANALYSIS.md]（建議補齊）
- [SECURITY.md]（建議補齊）
