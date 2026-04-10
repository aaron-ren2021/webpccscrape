# 身份輪換策略整合指南

## 核心概念：累積風險 vs 單次風險

### 問題診斷
您遇到的問題是**累積風險（Cumulative Detection）**：
- ✅ 前 5 筆成功 
- ❌ 後 8 筆被封鎖
- 🔍 原因：同一個「身份」被反覆使用，網站累積懷疑度

### 什麼是「身份」？
網站看到的不是你的程式碼，而是：
```
Identity = IP Address + Cookies + Browser Fingerprint + TLS + Behavior History
```

當同一個身份執行太多請求時，即使每次請求看起來都像真人，網站仍會察覺異常。

## 解決方案：Identity Rotation

### 核心參數
```python
MAX_REQUESTS_PER_IDENTITY = 4  # 每個身份最多執行 4 次請求
```

**為什麼是 4？**
- 觀察：第 6 次開始被封 → 安全閾值約在 4-5 次
- 保守策略：在達到風險閾值前就輪換
- 可調整：根據實際測試結果調整（建議範圍：3-6）

### 三種使用方式

#### 方式一：批次爬蟲（推薦，最簡單）

```python
from crawler.batch_crawler import batch_stealth_fetch

urls = [
    "https://example.com/page1",
    "https://example.com/page2",
    # ... 13 個 URLs
]

result = batch_stealth_fetch(
    urls,
    max_requests_per_identity=4,  # 🔥 每 4 筆就換身份
    headless=True,
    enable_human_behavior=True,
)

# 處理結果
for url, html in result.successful:
    # 解析 HTML...
    pass
```

**優點：**
- ✅ 自動管理身份輪換
- ✅ 自動管理 browser context 重用
- ✅ 自動清理 session
- ✅ 內建進度追蹤
- ✅ 不需要手動管理 Playwright 生命週期

#### 方式二：手動身份管理（進階）

```python
from crawler.identity_manager import IdentityManager
from crawler.stealth_runner import stealth_fetch_html

identity_mgr = IdentityManager(max_requests_per_identity=4)

for idx, url in enumerate(urls):
    # 獲取當前身份（自動輪換）
    identity = identity_mgr.get_identity()
    
    try:
        html = stealth_fetch_html(
            url,
            profile=identity.fingerprint,
            # 如果有 proxy：proxy=identity.proxy
        )
        identity_mgr.record_request(success=True)
        # 處理成功...
    except Exception:
        identity_mgr.record_request(success=False)
        # 處理失敗...
```

**優點：**
- ✅ 更細緻的控制
- ✅ 可整合到現有流程

#### 方式三：簡化版（快速驗證）

```python
from playwright.sync_api import sync_playwright
from crawler.stealth.fingerprint_profiles import pick_profile
from crawler.stealth.browser_stealth import create_stealth_context

MAX_PER_SESSION = 4

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    
    for i, url in enumerate(urls):
        # 每 4 筆就換身份
        if i % MAX_PER_SESSION == 0:
            if 'context' in locals():
                context.close()
            
            profile = pick_profile()  # 隨機選擇新指紋
            context, _ = create_stealth_context(browser, profile=profile)
            page = context.new_page()
        
        page.goto(url)
        # 處理頁面...
    
    browser.close()
```

**優點：**
- ✅ 最小改動
- ✅ 快速驗證概念

## 實際整合範例

### 整合到現有的 gov.py 或 taiwanbuying.py

**Before（單次爬取）：**
```python
def fetch_bids(settings: Settings) -> list[BidRecord]:
    records = []
    for url in detail_urls:
        html = requests.get(url).text
        # 解析並添加到 records...
    return records
```

**After（批次+身份輪換）：**
```python
from crawler.batch_crawler import batch_stealth_fetch

def fetch_bids(settings: Settings) -> list[BidRecord]:
    records = []
    
    # Step 1: 收集所有需要爬取的 URLs
    detail_urls = get_all_detail_urls()  # 你的邏輯
    
    # Step 2: 使用批次爬蟲（自動輪換身份）
    result = batch_stealth_fetch(
        detail_urls,
        max_requests_per_identity=4,
        enable_human_behavior=True,
        wait_selector=settings.SELECTOR_DETAIL_TITLE[0],
    )
    
    # Step 3: 解析成功的頁面
    for url, html in result.successful:
        record = parse_bid_detail(html)  # 你的解析邏輯
        if record:
            records.append(record)
    
    return records
```

## 參數調優指南

### 身份輪換頻率

| `max_requests_per_identity` | 適用場景 | 風險 | 效率 |
|:--:|---|:--:|:--:|
| 2-3 | 高風險網站、已被封鎖過 | 低 | 低 |
| 4-5 | 一般政府網站（推薦） | 中 | 中 |
| 6-8 | 寬鬆網站、內部測試 | 高 | 高 |

### 結合策略模式

```python
from crawler.stealth_runner import CrawlStrategy

# 高隱蔽模式：慢但安全
result = batch_stealth_fetch(
    urls,
    max_requests_per_identity=3,
    strategy=CrawlStrategy.STEALTH,  # 長延遲 + 完整行為
)

# 平衡模式：推薦用於生產環境
result = batch_stealth_fetch(
    urls,
    max_requests_per_identity=4,
    strategy=CrawlStrategy.BALANCED,
)

# 快速模式：僅用於測試或寬鬆網站
result = batch_stealth_fetch(
    urls,
    max_requests_per_identity=6,
    strategy=CrawlStrategy.AGGRESSIVE,
)
```

### 加入代理輪換（可選但推薦）

```python
proxy_list = [
    "http://proxy1.example.com:8080",
    "http://proxy2.example.com:8080",
    "http://proxy3.example.com:8080",
]

result = batch_stealth_fetch(
    urls,
    max_requests_per_identity=4,
    proxy_list=proxy_list,  # 每次身份輪換時也換 proxy
)
```

## 效果預期

### Before（無身份輪換）
```
Request 1-5:   ✅✅✅✅✅  (同一身份，累積風險↑)
Request 6-13:  ❌❌❌❌❌❌❌❌  (被識別為 bot)
成功率: 5/13 = 38.5%
```

### After（每 4 筆輪換）
```
Identity A (Req 1-4):   ✅✅✅✅
Identity B (Req 5-8):   ✅✅✅✅
Identity C (Req 9-12):  ✅✅✅✅
Identity D (Req 13):    ✅
成功率: 13/13 = 100% 🎉
```

## 監控與調優

### 使用 KPI 分析工具

```python
from crawler.analytics.kpi_analyzer import KPIAnalyzer

# 在批次爬取後
analyzer = KPIAnalyzer()
analyzer.load_events_from_logger(det_logger)
metrics = analyzer.analyze()

print(f"Success Rate: {metrics.success_rate:.1f}%")
print(f"Identities Used: {metrics.get_statistics()['total_identities']}")
print(f"Avg Requests per Identity: {metrics.get_statistics()['avg_requests_per_identity']:.1f}")
```

### 關鍵指標

1. **Success Rate**: 應該 >90%
2. **Terminal Failure Rate**: 應該 <5%（CAPTCHA/HARD_BLOCK）
3. **Avg Requests per Identity**: 應該接近 `max_requests_per_identity`

如果成功率仍然低：
- 降低 `max_requests_per_identity` (4 → 3)
- 增加延遲時間（使用 STEALTH 策略）
- 啟用代理輪換

## 最佳實踐

✅ **DO**
- 使用批次爬蟲處理多個 URL
- 保守設定 `max_requests_per_identity` (3-5)
- 結合人類行為模擬
- 啟用 session 持久化
- 記錄並分析 KPI

❌ **DON'T**
- 不要在同一身份下爬超過 5 筆
- 不要禁用人類行為模擬
- 不要忽略失敗日誌
- 不要使用固定延遲時間
- 不要重複使用被封鎖的身份

## 故障排除

### 問題：仍然被封鎖
- 降低 `max_requests_per_identity` 到 2-3
- 檢查是否正確輪換了 fingerprint
- 確認 session 已正確清除
- 考慮啟用代理

### 問題：太慢
- 增加 `max_requests_per_identity` 到 5-6
- 使用 AGGRESSIVE 策略
- 並行處理（多個 browser 實例）

### 問題：記憶體佔用高
- 確保 context 正確關閉
- 降低並行度
- 使用 headless 模式
