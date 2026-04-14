#!/usr/bin/env python3
"""Check all bid sources health status."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from core.config import Settings

logging.basicConfig(
    level=logging.WARNING,  # Suppress verbose logs
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("source-check")

# Import source fetchers
from crawler.taiwanbuying import fetch_bids as fetch_tw
from crawler.gov import fetch_bids as fetch_gov
from crawler.g0v import fetch_bids as fetch_g0v


def main() -> None:
    settings = Settings.from_env()
    
    sources = [
        ("taiwanbuying", fetch_tw, "台灣採購公報"),
        ("gov_pcc", fetch_gov, "政府電子採購網"),
        ("g0v", fetch_g0v, "開放資料 API"),
    ]
    
    print("=" * 70)
    print("📊 標案來源健康檢查")
    print("=" * 70)
    print()
    
    total_count = 0
    success_count = 0
    
    for name, fetch_fn, display_name in sources:
        try:
            # Create a minimal logger for this check
            check_log = logging.getLogger(f"check-{name}")
            check_log.setLevel(logging.ERROR)  # Only show errors
            
            records = fetch_fn(settings, check_log)
            count = len(records)
            total_count += count
            
            if count > 0:
                status = "✅ 正常"
                success_count += 1
            else:
                status = "⚠️  無資料"
            
            print(f"{display_name:20} {status:12} ({count:4} 筆)")
            
        except Exception as e:
            print(f"{display_name:20} ❌ 失敗       {str(e)[:40]}")
    
    print()
    print("=" * 70)
    print(f"總計: {success_count}/{len(sources)} 來源正常，共 {total_count} 筆標案")
    print("=" * 70)
    
    if success_count == 0:
        print()
        print("⚠️  警告：所有來源都失敗！請檢查：")
        print("  1. 網路連線是否正常")
        print("  2. Playwright 是否已安裝（playwright install chromium）")
        print("  3. .env 設定是否正確")
        sys.exit(1)
    
    if total_count < 5:
        print()
        print("⚠️  警告：標案數量過少，可能有來源故障")
        sys.exit(1)


if __name__ == "__main__":
    main()
