#!/usr/bin/env python3
"""Demo script for batch crawler with identity rotation.

This script demonstrates the recommended usage pattern for crawling
multiple URLs while avoiding cumulative detection through automatic
identity rotation.

Usage:
    python demo_batch_crawler.py
"""
from __future__ import annotations

import logging

from crawler.batch_crawler import batch_stealth_fetch
from crawler.behavior.throttle import ThrottleConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)


def progress_callback(current: int, total: int) -> None:
    """Print progress updates."""
    print(f"Progress: {current}/{total} ({current/total*100:.1f}%)")


def main() -> None:
    # Example URLs to crawl (replace with your actual targets)
    urls = [
        "https://web.pcc.gov.tw/prkms/tender/common/basic/readTenderBasic.do?primaryKey=12345",
        "https://web.pcc.gov.tw/prkms/tender/common/basic/readTenderBasic.do?primaryKey=12346",
        "https://web.pcc.gov.tw/prkms/tender/common/basic/readTenderBasic.do?primaryKey=12347",
        # ... add more URLs
    ]

    logger.info("Starting batch crawl with identity rotation")
    logger.info(f"Total URLs: {len(urls)}")

    # Configure throttle (adjust based on your needs)
    throttle = ThrottleConfig(
        delay_min=2.0,
        delay_max=5.0,
        cooldown_after_n=5,
        cooldown_min=10.0,
        cooldown_max=20.0,
        jitter_factor=0.4,
    )

    # Optional: uncomment to use proxies
    # proxy_list = [
    #     "http://proxy1.example.com:8080",
    #     "http://proxy2.example.com:8080",
    # ]

    # Run batch crawl with identity rotation
    result = batch_stealth_fetch(
        urls,
        max_requests_per_identity=4,  # 🔥 KEY PARAMETER: Rotate every 4 requests
        headless=True,
        timeout_ms=30000,
        wait_selector="body",
        enable_human_behavior=True,
        enable_session_persistence=True,
        session_dir=".sessions",
        artifact_dir=".detection_logs",
        throttle_config=throttle,
        # proxy_list=proxy_list,  # Uncomment to enable proxy rotation
        progress_callback=progress_callback,
    )

    # Print results
    print("\n" + "=" * 70)
    print("Batch Crawl Results")
    print("=" * 70)
    print(f"Total URLs: {result.total}")
    print(f"Successful: {result.success_count} ({result.success_rate * 100:.1f}%)")
    print(f"Failed: {result.failure_count}")
    print()

    if result.failed:
        print("Failed URLs:")
        for url, reason in result.failed:
            print(f"  - {url}: {reason}")
        print()

    # Process successful results
    if result.successful:
        print(f"Successfully fetched {len(result.successful)} pages")
        # Example: save to files or parse
        for idx, (url, html) in enumerate(result.successful):
            print(f"  {idx + 1}. {url} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
