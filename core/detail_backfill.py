from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crawler.g0v import enrich_record as enrich_g0v_record
from crawler.gov import enrich_detail as enrich_gov_detail
from core.config import Settings
from core.models import BidRecord
from storage.detail_cache_store import DetailCacheStore


@dataclass(slots=True)
class DetailBackfillResult:
    selected_count: int
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)


def run_detail_backfill(
    settings: Settings,
    logger: Any,
    *,
    limit: int | None = None,
    sources: set[str] | None = None,
    dry_run: bool = False,
) -> DetailBackfillResult:
    store = DetailCacheStore(
        cache_path=settings.detail_cache_path,
        queue_path=settings.detail_backfill_queue_path,
        logger=logger,
        ttl_days=settings.detail_cache_ttl_days,
        max_attempts=settings.detail_backfill_max_attempts,
    )
    records = store.get_pending_records(
        limit=settings.detail_backfill_limit if limit is None else limit,
        sources=sources,
    )
    result = DetailBackfillResult(selected_count=len(records))
    logger.info(
        "detail_backfill_started",
        extra={"count": len(records), "sources": ",".join(sorted(sources or [])), "dry_run": dry_run},
    )

    if dry_run:
        for record in records:
            logger.info(
                "detail_backfill_dry_run_item",
                extra={"title": record.title, "source": record.source, "url": record.url},
            )
        return result

    g0v_records = [record for record in records if record.source == "g0v"]
    gov_records = [record for record in records if record.source == "gov_pcc"]
    skipped_records = [record for record in records if record.source not in {"g0v", "gov_pcc"}]

    for record in skipped_records:
        result.skipped_count += 1
        logger.info("detail_backfill_skipped", extra={"reason": "unsupported_source", "source": record.source})

    _backfill_g0v_records(g0v_records, settings, logger, store, result)
    _backfill_gov_records(gov_records, settings, logger, store, result)

    logger.info(
        "detail_backfill_finished",
        extra={
            "selected": result.selected_count,
            "success": result.success_count,
            "failed": result.failed_count,
            "skipped": result.skipped_count,
            "error_count": len(result.errors),
        },
    )
    return result


def _backfill_g0v_records(
    records: list[BidRecord],
    settings: Settings,
    logger: Any,
    store: DetailCacheStore,
    result: DetailBackfillResult,
) -> None:
    for record in records:
        try:
            enriched = enrich_g0v_record(record, settings, logger)
            if enriched or _has_detail_data(record):
                store.mark_success(record)
                result.success_count += 1
                logger.info("detail_backfill_success", extra={"source": record.source, "title": record.title})
            else:
                store.mark_failure(record, "g0v_not_enriched")
                result.failed_count += 1
        except Exception as exc:
            reason = f"g0v_error:{exc}"
            store.mark_failure(record, reason)
            result.failed_count += 1
            result.errors.append(reason)


def _backfill_gov_records(
    records: list[BidRecord],
    settings: Settings,
    logger: Any,
    store: DetailCacheStore,
    result: DetailBackfillResult,
) -> None:
    if not records:
        return
    try:
        enrich_gov_detail(records, settings, logger)
    except Exception as exc:
        reason = f"gov_error:{exc}"
        for record in records:
            store.mark_failure(record, reason)
            result.failed_count += 1
        result.errors.append(reason)
        return

    for record in records:
        if _has_detail_data(record):
            store.mark_success(record)
            result.success_count += 1
            logger.info("detail_backfill_success", extra={"source": record.source, "title": record.title})
        else:
            reason = str(record.metadata.get("detail_fetch_mode") or "gov_not_enriched")
            store.mark_failure(record, reason)
            result.failed_count += 1


def _has_detail_data(record: BidRecord) -> bool:
    return any(
        str(value or "").strip()
        and str(value or "").strip() not in {"無提供", "無", "none", "null"}
        for value in [
            record.budget_amount,
            record.bid_bond,
            record.bid_deadline,
            record.bid_opening_time,
        ]
    )
