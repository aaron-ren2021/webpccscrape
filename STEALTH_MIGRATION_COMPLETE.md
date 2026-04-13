# Playwright + Stealth 重構完成摘要

## ✅ 已完成的修改

### 1. **core/config.py**
- ✅ 新增 `gov_detail_max_per_identity: int = 3` 參數
- ✅ 在 `from_env()` 中新增環境變數讀取邏輯

### 2. **crawler/gov.py** (最關鍵)
- ✅ 修改 `fetch_bids()` - 優先使用 Stealth，失敗 fallback 到 requests
- ✅ 修改 `enrich_detail()` - 作為入口，判斷使用 Stealth 或 requests
- ✅ 新增 `enrich_detail_stealth()` - 🔥 使用 `batch_stealth_fetch` 批次抓取，每 3 筆換身份
- ✅ 新增 `enrich_detail_requests()` - 原有的 requests 邏輯作為 fallback
- ✅ 保留所有解析邏輯 (`_parse_records`, `_extract_detail_fields`) 不變

### 3. **crawler/taiwanbuying.py**
- ✅ 修改 `fetch_bids()` - 優先使用 Stealth，失敗 fallback 到 requests
- ✅ 保留解析邏輯 `_parse_records` 不變

### 4. **.env**
- ✅ `ENABLE_PLAYWRIGHT_FALLBACK=true`
- ✅ `STEALTH_ENABLED=true`
- ✅ `STEALTH_HUMAN_BEHAVIOR=true`
- ✅ `STEALTH_SESSION_PERSISTENCE=true`
- ✅ `STEALTH_THROTTLE_DELAY_MIN=3.0` (增加延遲避免 CAPTCHA)
- ✅ `STEALTH_THROTTLE_DELAY_MAX=8.0`
- ✅ `STEALTH_THROTTLE_COOLDOWN_AFTER=3` (每 3 筆就 cooldown)
- ✅ `STEALTH_THROTTLE_COOLDOWN_MIN=15.0` (更長的冷卻時間)
- ✅ `STEALTH_THROTTLE_COOLDOWN_MAX=30.0`
- ✅ `GOV_DETAIL_DELAY_SECONDS=5.0` (從 2.0 增加到 5.0)
- ✅ `GOV_DETAIL_MAX_PER_IDENTITY=3` (🔥 每 3 筆換身份，避免累積偵測)
- ✅ `PLAYWRIGHT_TIMEOUT_MS=30000` (從 20000 增加到 30000)

## 🎯 核心改進

### 問題根因
- **gov.pcc 的 `enrich_detail()` 逐筆抓取詳細頁時**，在第 5-6 筆開始觸發 CAPTCHA
- 原因：同一身份累積請求過多，被識別為爬蟲

### 解決方案
- 🔥 使用 `batch_stealth_fetch` 批次抓取，**每 3 筆自動換身份**（指紋+Session+Proxy）
- 🔥 啟用**人類行為模擬**（隨機滾動、滑鼠移動、停留時間）
- 🔥 **自適應節流**（根據成功率動態調整延遲）
- 🔥 **Fail Fast + Long Reset**（遇到 CAPTCHA 立即停止，冷卻 60-180 秒）
- 🔥 **Session 持久化**（模擬回訪用戶）

### 預期效果
- ❌ **Before**: 5/13 成功（38.5%），第 6 筆開始被 CAPTCHA 封鎖
- ✅ **After**: 12-13/13 成功（92-100%），無 CAPTCHA

## 📋 驗證步驟

### Step 1: 確認設定
```bash
python verify_stealth.py
```

### Step 2: 安裝 Playwright（如尚未安裝）
```bash
# 在虛擬環境中
source venv/bin/activate
playwright install chromium
```

### Step 3: 本地測試（不寄信）
```bash
python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state
```

### Step 4: 檢查結果
- ✅ Log 中無 `gov_detail_captcha_detected`
- ✅ Log 中有 `gov_detail_enriching_stealth`、`batch_crawl_complete`
- ✅ Log 中成功率 >90%
- ✅ `preview.html` 中預算金額、押標金已正確填入
- ✅ Log 中有 `identities_used: 3-5`（表示有正確輪替身份）

### Step 5: 觀察 Log 關鍵訊息
```
✅ 正常流程：
gov_detail_enriching_stealth (count: 10, max_per_identity: 3)
batch_context_created (identity_id: 1)
batch_fetch_success × 3
batch_context_created (identity_id: 2)  # 🔥 身份輪替
batch_fetch_success × 3
batch_context_created (identity_id: 3)
batch_fetch_success × 4
gov_detail_enriched_stealth (success_rate: 100.0%)

❌ 如果失敗：
gov_detail_captcha_detected
gov_detail_stealth_failed_fallback_requests
→ 可能需要降低 GOV_DETAIL_MAX_PER_IDENTITY 到 2
```

## 🔧 故障排除

### 問題 1: 仍然被 CAPTCHA 封鎖
**解決方案**：
```bash
# 降低每身份請求數
GOV_DETAIL_MAX_PER_IDENTITY=2

# 增加延遲
STEALTH_THROTTLE_DELAY_MIN=5.0
STEALTH_THROTTLE_DELAY_MAX=12.0
```

### 問題 2: Playwright 未安裝
```bash
playwright install chromium
```

### 問題 3: 速度太慢
```bash
# 這是正常的！Stealth 模式會慢很多，但能避免被封鎖
# 如果需要加快，可以：
GOV_DETAIL_MAX_PER_IDENTITY=5  # 風險增加
STEALTH_THROTTLE_DELAY_MIN=2.0  # 風險增加
```

### 問題 4: 記憶體佔用高
```bash
# Playwright 會佔用較多記憶體，可以：
STEALTH_HEADLESS=true  # 確保 headless 模式
# 確保 context 正確關閉（已在程式碼中處理）
```

## 📚 相關文件

- [ADVANCED_ANTI_DETECTION.md](docs/ADVANCED_ANTI_DETECTION.md) - 完整反偵測策略說明
- [IDENTITY_ROTATION_GUIDE.md](docs/IDENTITY_ROTATION_GUIDE.md) - 身份輪替指南
- [batch_crawler.py](crawler/batch_crawler.py) - 批次爬蟲實作
- [stealth_runner.py](crawler/stealth_runner.py) - Stealth 進入點

## 🎉 完成！

Playwright + Stealth 重構已完成並啟用。系統現在會：
1. ✅ 主列表優先用 Stealth 抓取（gov.pcc, taiwanbuying）
2. ✅ 詳細頁使用批次 Stealth + 身份輪替（gov.pcc）
3. ✅ 自動模擬人類行為（滾動、滑鼠、停留）
4. ✅ 失敗時自動 fallback 到 requests
5. ✅ 遇到 CAPTCHA 自動冷卻並換身份

執行 `python verify_stealth.py` 開始驗證！
