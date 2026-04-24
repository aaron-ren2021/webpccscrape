from __future__ import annotations

from crawler.detection.detection_logger import CrawlOutcome
from crawler.detection.strategies import get_retry_strategy


def test_single_runner_terminal_abort():
    plan = get_retry_strategy(
        CrawlOutcome.CAPTCHA,
        attempt=1,
        context={"runner": "single", "max_retries": 3},
    )
    assert plan.retry is False
    assert "abort" in plan.actions


def test_single_runner_recoverable_retry_and_rotation():
    plan = get_retry_strategy(
        CrawlOutcome.RATE_LIMITED,
        attempt=1,
        context={"runner": "single", "max_retries": 3},
    )
    assert plan.retry is True
    assert "backoff" in plan.actions
    assert "rotate_profile" in plan.actions
    assert "rotate_proxy" in plan.actions


def test_single_runner_exhausted_attempt_stops_retry():
    plan = get_retry_strategy(
        CrawlOutcome.SOFT_BLOCK,
        attempt=3,
        context={"runner": "single", "max_retries": 3},
    )
    assert plan.retry is False


def test_batch_runner_terminal_failure_plan():
    plan = get_retry_strategy(
        CrawlOutcome.CLOUDFLARE_CHALLENGE,
        attempt=1,
        context={"runner": "batch"},
    )
    assert "rotate_identity" in plan.actions
    assert "backoff" in plan.actions
    assert plan.cooldown_range == (5.0, 15.0)


def test_batch_runner_recoverable_failure_plan():
    plan = get_retry_strategy(
        CrawlOutcome.RATE_LIMITED,
        attempt=1,
        context={"runner": "batch"},
    )
    assert "backoff" in plan.actions
    assert plan.cooldown_range == (20.0, 60.0)
