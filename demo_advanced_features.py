#!/usr/bin/env python3
"""Demo: Advanced anti-detection features.

This script demonstrates the advanced optimizations:
1. Fail Fast + Reset (60-180s cooldown on terminal failures)
2. Success Rate Adaptive Throttling (auto-adjust delays)
3. Behavior Pattern Elimination (randomized actions)
"""
from __future__ import annotations

import logging

from crawler.behavior.throttle import ThrottleController, ThrottleConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def demo_adaptive_throttling():
    """Demonstrate adaptive throttling based on success rate."""
    print("=" * 70)
    print("Demo: Adaptive Throttling")
    print("=" * 70)
    print()
    
    config = ThrottleConfig(delay_min=2.0, delay_max=5.0, jitter_factor=0.4)
    throttle = ThrottleController(config)
    
    # Simulate 15 requests with varying success rates
    results = [
        True, True, True,      # First 3: success
        False, False,          # 4-5: failures (成功率下降)
        False, False,          # 6-7: more failures (延遲應該增加)
        True, True,            # 8-9: recovering
        True, True, True,      # 10-12: good (延遲應該降回)
        True, True, True,      # 13-15: excellent
    ]
    
    print("Simulating requests with varying success rates:")
    print()
    
    for i, success in enumerate(results, 1):
        wait = throttle.wait_before_request()
        
        if success:
            throttle.reset_failure_streak()
        else:
            throttle.record_failure()
        
        # Get current stats
        window = throttle._recent_results[-10:] if len(throttle._recent_results) >= 5 else throttle._recent_results
        success_rate = sum(1 for r in window if r) / len(window) if window else 0.0
        
        status = "✅" if success else "❌"
        print(
            f"Request {i:2d}: {status} | "
            f"Wait: {wait:5.2f}s | "
            f"Multiplier: {throttle._adaptive_multiplier:4.2f} | "
            f"Success Rate: {success_rate*100:5.1f}%"
        )
    
    print()
    print("Notice how the multiplier increases when success rate drops,")
    print("and decreases when success rate recovers!")
    print()


def demo_behavior_randomization():
    """Demonstrate behavior pattern randomization."""
    print("=" * 70)
    print("Demo: Behavior Pattern Elimination")
    print("=" * 70)
    print()
    
    print("Simulating 10 page reads to show behavior diversity:")
    print()
    
    # Mock page object
    class MockPage:
        def __init__(self):
            self.viewport_size = {"width": 1280, "height": 720}
        
        class Mouse:
            @staticmethod
            def wheel(x, y):
                pass
            
            @staticmethod
            def move(x, y, steps=1):
                pass
        
        mouse = Mouse()
    
    from crawler.behavior.human_behavior import simulate_page_read, simulate_idle_reading
    import random
    import time
    
    for i in range(1, 11):
        page = MockPage()
        start = time.time()
        
        # 30% chance of idle reading, 70% active reading
        if random.random() < 0.3:
            behavior_type = "Idle Reading (少互動)"
            simulate_idle_reading(page)
        else:
            behavior_type = "Active Reading (滾動+滑鼠)"
            simulate_page_read(page)
        
        duration = time.time() - start
        print(f"Page {i:2d}: {behavior_type:30s} | Duration: {duration:5.2f}s")
    
    print()
    print("Notice the variation in:")
    print("  - Behavior type (idle vs active)")
    print("  - Duration (varies significantly)")
    print("  - Action sequence (randomized each time)")
    print()


def demo_fail_fast_concept():
    """Demonstrate fail fast concept (conceptual, not actual crawling)."""
    print("=" * 70)
    print("Demo: Fail Fast + Reset Concept")
    print("=" * 70)
    print()
    
    print("Simulating detection of terminal failures:")
    print()
    
    scenarios = [
        ("SUCCESS", "Normal", 0),
        ("SUCCESS", "Normal", 0),
        ("CAPTCHA", "Terminal - Fail Fast", 120),
        ("RATE_LIMITED", "Recoverable", 40),
        ("SUCCESS", "Normal", 0),
        ("HARD_BLOCK", "Terminal - Fail Fast", 150),
        ("ACCESS_DENIED", "Terminal - Fail Fast", 90),
    ]
    
    for i, (outcome, action, cooldown) in enumerate(scenarios, 1):
        status = "✅" if outcome == "SUCCESS" else "❌"
        print(f"Request {i}: {status} {outcome:20s} → {action:25s}", end="")
        
        if cooldown > 0:
            print(f" → Cooldown: {cooldown}s + Close Context + Rotate Identity")
        else:
            print()
    
    print()
    print("Key Points:")
    print("  ✅ Terminal failures (CAPTCHA, HARD_BLOCK, ACCESS_DENIED):")
    print("     → Immediately close context (Fail Fast)")
    print("     → Long cooldown (60-180s)")
    print("     → Force identity rotation")
    print()
    print("  ✅ Recoverable failures (RATE_LIMITED, SOFT_BLOCK):")
    print("     → Moderate cooldown (20-60s)")
    print("     → May rotate identity")
    print()
    print("  ✅ Success:")
    print("     → No cooldown, continue normally")
    print()


if __name__ == "__main__":
    demo_adaptive_throttling()
    print("\n" + "=" * 70 + "\n")
    
    demo_behavior_randomization()
    print("\n" + "=" * 70 + "\n")
    
    demo_fail_fast_concept()
