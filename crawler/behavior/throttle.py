from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ThrottleConfig:
    """Configuration for request throttle controller."""

    # Base delay range (seconds) between requests
    delay_min: float = 1.5
    delay_max: float = 7.5

    # After this many consecutive requests, apply a cooldown
    cooldown_after_n: int = 5
    cooldown_min: float = 10.0
    cooldown_max: float = 25.0

    # Exponential backoff on detection events
    backoff_base: float = 5.0
    backoff_max: float = 120.0
    backoff_multiplier: float = 2.0

    # Jitter factor (0.0 – 1.0): proportion of delay added/removed as noise
    jitter_factor: float = 0.4


class ThrottleController:
    """Manages adaptive request timing with jitter, cooldowns, and backoff."""

    def __init__(self, config: ThrottleConfig | None = None) -> None:
        self._config = config or ThrottleConfig()
        self._request_count: int = 0
        self._consecutive_failures: int = 0
        self._recent_results: list[bool] = []  # Track recent success/failure for adaptive throttling
        self._adaptive_multiplier: float = 1.0  # Dynamic adjustment based on success rate

    @property
    def config(self) -> ThrottleConfig:
        return self._config

    def _add_jitter(self, base: float) -> float:
        jitter = base * self._config.jitter_factor
        return base + random.uniform(-jitter, jitter)
    
    def _update_adaptive_multiplier(self) -> None:
        """Update delay multiplier based on recent success rate.
        
        If success rate is low, increase delays to reduce detection risk.
        Uses a sliding window of last 10 requests.
        """
        if len(self._recent_results) < 5:
            return  # Not enough data yet
        
        # Calculate success rate from recent window (last 10 requests)
        window = self._recent_results[-10:]
        success_rate = sum(1 for r in window if r) / len(window)
        
        # Adjust multiplier based on success rate
        if success_rate < 0.5:
            # Low success rate: increase delays significantly
            self._adaptive_multiplier = min(self._adaptive_multiplier * 1.3, 3.0)
            logger.warning(
                "throttle_adaptive_increase",
                extra={
                    "success_rate": round(success_rate, 2),
                    "new_multiplier": round(self._adaptive_multiplier, 2),
                },
            )
        elif success_rate < 0.7:
            # Moderate success rate: increase delays moderately
            self._adaptive_multiplier = min(self._adaptive_multiplier * 1.1, 2.0)
            logger.info(
                "throttle_adaptive_adjust",
                extra={
                    "success_rate": round(success_rate, 2),
                    "new_multiplier": round(self._adaptive_multiplier, 2),
                },
            )
        elif success_rate > 0.9 and self._adaptive_multiplier > 1.0:
            # High success rate: can slightly reduce delays
            self._adaptive_multiplier = max(self._adaptive_multiplier * 0.95, 1.0)
            logger.debug(
                "throttle_adaptive_decrease",
                extra={
                    "success_rate": round(success_rate, 2),
                    "new_multiplier": round(self._adaptive_multiplier, 2),
                },
            )

    def wait_before_request(self) -> float:
        """Sleep before next request. Returns actual wait time in seconds."""
        self._request_count += 1
        self._update_adaptive_multiplier()

        # Cooldown window
        if (
            self._config.cooldown_after_n > 0
            and self._request_count % self._config.cooldown_after_n == 0
        ):
            base = random.uniform(self._config.cooldown_min, self._config.cooldown_max)
            wait = self._add_jitter(base) * self._adaptive_multiplier
            logger.debug(
                "throttle_cooldown",
                extra={
                    "request_count": self._request_count,
                    "wait": round(wait, 2),
                    "adaptive_multiplier": round(self._adaptive_multiplier, 2),
                },
            )
            time.sleep(max(wait, 0))
            return wait

        # Normal delay (with adaptive multiplier)
        base = random.uniform(self._config.delay_min, self._config.delay_max)
        wait = self._add_jitter(base) * self._adaptive_multiplier
        logger.debug(
            "throttle_delay",
            extra={
                "wait": round(wait, 2),
                "adaptive_multiplier": round(self._adaptive_multiplier, 2),
            },
        )
        time.sleep(max(wait, 0))
        return wait

    def backoff_after_detection(self) -> float:
        """Apply exponential backoff after a detection event. Returns wait time."""
        self._consecutive_failures += 1
        delay = min(
            self._config.backoff_base * (self._config.backoff_multiplier ** (self._consecutive_failures - 1)),
            self._config.backoff_max,
        )
        wait = self._add_jitter(delay)
        logger.warning(
            "throttle_backoff",
            extra={
                "consecutive_failures": self._consecutive_failures,
                "wait": round(wait, 2),
            },
        )
        time.sleep(max(wait, 0))
        return wait

    def reset_failure_streak(self) -> None:
        """Call after a successful request to reset backoff counter."""
        self._consecutive_failures = 0
        self._record_result(success=True)
    
    def record_failure(self) -> None:
        """Record a failure for adaptive throttling."""
        self._consecutive_failures += 1
        self._record_result(success=False)
    
    def _record_result(self, success: bool) -> None:
        """Record request result for adaptive throttling."""
        self._recent_results.append(success)
        # Keep only last 20 results to prevent unbounded growth
        if len(self._recent_results) > 20:
            self._recent_results = self._recent_results[-20:]

    def reset(self) -> None:
        """Reset all counters (e.g. for a new crawl run)."""
        self._request_count = 0
        self._consecutive_failures = 0
        self._recent_results = []
        self._adaptive_multiplier = 1.0
