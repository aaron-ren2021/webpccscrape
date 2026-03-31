# 本地部署指南（完全繞過 Azure）

## ✅ 已完成步驟
1. ✅ Python 3.12.3 環境確認
2. ✅ 虛擬環境 `venv/` 已創建
3. ✅ 核心依賴已安裝（已移除 Azure 套件）
4. ✅ 配置文件已創建並設定為 Outlook SMTP

## 📝 剩餘步驟

### 1. 編輯 .env 設定你的 Outlook 帳號資訊

開啟 `.env` 檔案，修改以下三個欄位：

```bash
EMAIL_TO=收件人@example.com
SMTP_USERNAME=你的outlook帳號@outlook.com
SMTP_PASSWORD=你的outlook密碼
SMTP_FROM=你的outlook帳號@outlook.com
```

**重要提示：**
- 如果你的 Outlook 帳號啟用了雙重驗證（2FA），需要使用「應用程式密碼」而不是帳號密碼。
- 申請應用程式密碼：登入 Outlook → 安全性設定 → 應用程式密碼

### 2. 測試執行（不寄信，僅產生 HTML 預覽）

```bash
source venv/bin/activate
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state
```

這個指令會：
- 抓取標案資料
- 篩選教育相關案件  
- 產生 HTML 預覽到 `./output/preview.html`
- **不會寄信**
- **不會儲存狀態**（使用記憶體儲存，無需 Azure）

### 3. 完整執行（實際寄信）

確認預覽 HTML 內容正確後，執行完整流程：

```bash
source venv/bin/activate
python run_local.py
```

這個指令會：
- 抓取標案資料
- 篩選教育相關案件
- **透過 Outlook 寄信**
- 使用記憶體儲存（每次執行獨立，不記錄歷史通知）

### 4. 設定 crontab 定時排程

每天早上 8:35 自動執行（✅ 已設定完成）：

```bash
crontab -e
```

已設定的內容：

```
35 8 * * * cd /home/xcloud/project/webpccscrape && /home/xcloud/project/webpccscrape/venv/bin/python run_local.py >> /home/xcloud/project/webpccscrape/logs/cron.log 2>&1
```

說明：
- `35 8 * * *` = 每天 8:35 執行
- 使用虛擬環境中的 Python
- 日誌輸出到 `logs/cron.log`
- 預計 8:37-8:40 完成並寄出信件

## 🔍 故障排除

### 問題 1：SMTP 認證失敗
**解決方式：** 
- 檢查 Outlook 帳號/密碼是否正確
- 如有 2FA，使用應用程式密碼
- 確認 SMTP_USE_TLS=true

### 問題 2：抓不到資料
**解決方式：**
- 檢查網路連線
- 查看 log 中的 `source_failed` 訊息
- 某一來源失敗不影響另一來源

### 問題 3：無新案件但沒收到信
**正常現象：** 當日若無新案件，程式設計為不寄信，僅在 log 記錄 `no new bids`。

## 📌 重要說明

### 關於狀態記錄
- **本地部署預設使用記憶體儲存**（InMemoryStateStore）
- 每次執行都是獨立的，不會記錄「已通知過的案件」
- 如果需要持久化狀態避免重複通知，可以：
  - 選項 1：設定 Azure Storage（需要 Azure 帳號）
  - 選項 2：自行實作本地文件儲存（需修改程式碼）

### 優缺點
✅ **優點：**
- 無需 Azure 帳號
- 完全本地運行
- 成本為零

⚠️ **缺點：**
- 每次執行獨立，可能重複通知相同案件
- 建議：搭配 crontab 每天定時執行，以日期作為自然去重

## 🚀 快速啟動指令集

```bash
# 進入專案目錄
cd /home/xcloud/project/webpccscrape

# 啟動虛擬環境
source venv/bin/activate

# 測試模式（不寄信）
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state

# 正式執行
python run_local.py

# 離開虛擬環境
deactivate
```
