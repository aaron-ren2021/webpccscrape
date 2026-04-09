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
    delay_min: float = 2.0
    delay_max: float = 6.0

    # After this many consecutive requests, apply a cooldown
    cooldown_after_n: int = 5
    cooldown_min: float = 8.0
    cooldown_max: float = 15.0

    # Exponential backoff on detection events
    backoff_base: float = 5.0
    backoff_max: float = 120.0
    backoff_multiplier: float = 2.0

    # Jitter factor (0.0 – 1.0): proportion of delay added/removed as noise
    jitter_factor: float = 0.3


class ThrottleController:
    """Manages adaptive request timing with jitter, cooldowns, and backoff."""

    def __init__(self, config: ThrottleConfig | None = None) -> None:
        self._config = config or ThrottleConfig()
        self._request_count: int = 0
        self._consecutive_failures: int = 0

    @property
    def config(self) -> ThrottleConfig:
        return self._config

    def _add_jitter(self, base: float) -> float:
        jitter = base * self._config.jitter_factor
        return base + random.uniform(-jitter, jitter)

    def wait_before_request(self) -> float:
        """Sleep before next request. Returns actual wait time in seconds."""
        self._request_count += 1

        # Cooldown window
        if (
            self._config.cooldown_after_n > 0
            and self._request_count % self._config.cooldown_after_n == 0
        ):
            base = random.uniform(self._config.cooldown_min, self._config.cooldown_max)
            wait = self._add_jitter(base)
            logger.debug(
                "throttle_cooldown",
                extra={"request_count": self._request_count, "wait": round(wait, 2)},
            )
            time.sleep(max(wait, 0))
            return wait

        # Normal delay
        base = random.uniform(self._config.delay_min, self._config.delay_max)
        wait = self._add_jitter(base)
        logger.debug("throttle_delay", extra={"wait": round(wait, 2)})
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

    def reset(self) -> None:
        """Reset all counters (e.g. for a new crawl run)."""
        self._request_count = 0
        self._consecutive_failures = 0
