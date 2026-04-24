from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from crawler.detection.detection_logger import CrawlOutcome


@dataclass(slots=True)
class RetryStrategy:
    """Normalized retry/action decision returned by strategy engine."""

    retry: bool
    actions: tuple[str, ...] = field(default_factory=tuple)
    cooldown_range: tuple[float, float] | None = None
    human_behavior_intensity: str = "normal"


def _normalize_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
    if context is None:
        return {}
    return dict(context)


def _single_runner_strategy(
    outcome: CrawlOutcome,
    attempt: int,
    context: Mapping[str, Any] | None,
) -> RetryStrategy:
    ctx = _normalize_context(context)
    max_retries = int(ctx.get("max_retries", 1))
    can_retry = attempt < max_retries

    if outcome == CrawlOutcome.SUCCESS:
        return RetryStrategy(retry=False, actions=())

    if outcome in (
        CrawlOutcome.CAPTCHA,
        CrawlOutcome.HARD_BLOCK,
        CrawlOutcome.ACCESS_DENIED,
    ):
        return RetryStrategy(
            retry=False,
            actions=("abort",),
            human_behavior_intensity="elevated",
        )

    if outcome in (
        CrawlOutcome.RATE_LIMITED,
        CrawlOutcome.CLOUDFLARE_CHALLENGE,
        CrawlOutcome.SOFT_BLOCK,
    ):
        return RetryStrategy(
            retry=can_retry,
            actions=("backoff", "rotate_profile", "rotate_proxy"),
            human_behavior_intensity="elevated",
        )

    return RetryStrategy(
        retry=can_retry,
        actions=("backoff", "rotate_proxy"),
        human_behavior_intensity="elevated",
    )


def _batch_runner_strategy(outcome: CrawlOutcome) -> RetryStrategy:
    if outcome == CrawlOutcome.SUCCESS:
        return RetryStrategy(retry=False, actions=())

    if outcome in (
        CrawlOutcome.CAPTCHA,
        CrawlOutcome.HARD_BLOCK,
        CrawlOutcome.ACCESS_DENIED,
        CrawlOutcome.CLOUDFLARE_CHALLENGE,
    ):
        return RetryStrategy(
            retry=False,
            actions=("abort", "rotate_identity", "backoff"),
            cooldown_range=(5.0, 15.0),
            human_behavior_intensity="elevated",
        )

    if outcome in (
        CrawlOutcome.RATE_LIMITED,
        CrawlOutcome.SOFT_BLOCK,
    ):
        return RetryStrategy(
            retry=False,
            actions=("backoff",),
            cooldown_range=(20.0, 60.0),
            human_behavior_intensity="elevated",
        )

    return RetryStrategy(
        retry=False,
        actions=("backoff",),
        cooldown_range=(5.0, 15.0),
        human_behavior_intensity="elevated",
    )


def get_retry_strategy(
    outcome: CrawlOutcome,
    attempt: int,
    context: Mapping[str, Any] | None = None,
) -> RetryStrategy:
    """Return retry/action strategy for the given outcome and execution context."""
    ctx = _normalize_context(context)
    runner = str(ctx.get("runner", "single")).lower()

    if runner == "batch":
        return _batch_runner_strategy(outcome)
    return _single_runner_strategy(outcome, attempt, ctx)
