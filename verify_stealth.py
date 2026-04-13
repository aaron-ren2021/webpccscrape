#!/usr/bin/env python3
"""驗證 Playwright + Stealth 重構是否正常運作"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import Settings


def main():
    print("🔍 驗證 Playwright + Stealth 設定...\n")
    
    # Load settings
    settings = Settings.from_env()
    
    # Check critical settings
    checks = {
        "✅ Playwright Fallback 已啟用": settings.enable_playwright_fallback,
        "✅ Stealth 已啟用": settings.stealth_enabled,
        "✅ 人類行為模擬已啟用": settings.stealth_human_behavior,
        "✅ Session 持久化已啟用": settings.stealth_session_persistence,
        "✅ Gov Detail 使用身份輪替": hasattr(settings, 'gov_detail_max_per_identity'),
    }
    
    all_passed = True
    for check_name, result in checks.items():
        if result:
            print(f"{check_name}")
        else:
            print(f"❌ {check_name.replace('✅', '')}")
            all_passed = False
    
    print(f"\n📊 設定摘要：")
    print(f"  - Gov Detail 每身份最多請求數: {getattr(settings, 'gov_detail_max_per_identity', 'N/A')}")
    print(f"  - Stealth 延遲範圍: {settings.stealth_throttle_delay_min}-{settings.stealth_throttle_delay_max}秒")
    print(f"  - Stealth Cooldown 間隔: 每{settings.stealth_throttle_cooldown_after}筆")
    print(f"  - Playwright Timeout: {settings.playwright_timeout_ms}ms")
    print(f"  - Headless 模式: {settings.stealth_headless}")
    
    if all_passed:
        print("\n✅ 所有設定檢查通過！")
        print("\n🚀 下一步：")
        print("  1. 確認已安裝 Playwright: playwright install chromium")
        print("  2. 執行測試: python run_local.py --no-send --preview-html ./output/preview.html --no-persist-state")
        print("  3. 檢查 log 中無 'gov_detail_captcha_detected'")
        print("  4. 檢查 preview.html 中預算金額與押標金已正確填入")
        return 0
    else:
        print("\n❌ 部分設定未正確啟用，請檢查 .env 檔案")
        return 1


if __name__ == "__main__":
    sys.exit(main())
