from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from crawler.gov import fetch_bids as fetch_gov_bids
from crawler.gov import enrich_detail as enrich_gov_detail
from crawler.taiwanbuying import fetch_bids as fetch_taiwanbuying_bids
from core.ai_classifier import AIClassification, build_ai_clients, classify_bids_batch
from core.config import Settings
from core.dedup import deduplicate_bids
from core.filters import filter_bids
from core.formatter import render_email_html, render_email_subject
from core.models import BidRecord, RunResult, SourceRunStatus
from core.normalize import build_bid_uid
from notify.dispatcher import send_email
from notify.github_notify import create_bid_issues
from storage.blob_store import BlobStateStore
from storage.table_store import TableStateStore


class InMemoryStateStore:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    def get_notified_keys(self) -> set[str]:
        return set(self._keys)

    def mark_notified(self, records: list[BidRecord]) -> None:
        for record in records:
            self._keys.add(record.uid)


def run_monitor(settings: Settings, logger: Any | None = None, persist_state: bool = True) -> RunResult:
    logger = logger or logging.getLogger("bid-monitor")
    now_tw = datetime.now(ZoneInfo(settings.timezone))
    today = now_tw.date()

    source_status: list[SourceRunStatus] = []
    all_records: list[BidRecord] = []

    for source_name, fn in [
        ("taiwanbuying", fetch_taiwanbuying_bids),
        ("gov_pcc", fetch_gov_bids),
    ]:
        try:
            records = fn(settings, logger)
            all_records.extend(records)
            source_status.append(SourceRunStatus(source=source_name, success=True, count=len(records)))
        except Exception as exc:
            logger.exception("source_failed", extra={"source": source_name, "error": str(exc)})
            source_status.append(SourceRunStatus(source=source_name, success=False, count=0, error=str(exc)))

    # --- Phase 1: keyword-based filter + dedup ---
    filtered = filter_bids(all_records)
    deduped = deduplicate_bids(filtered)

    for record in deduped:
        record.uid = build_bid_uid(
            title=record.title,
            org=record.organization,
            bid_date=record.bid_date,
            amount=record.amount_value,
            amount_raw=record.amount_raw,
        )

    # --- Phase 1.5: Enrich detail fields (budget, bid bond) for filtered records ---
    gov_records = [r for r in deduped if r.source == "gov_pcc"]
    if gov_records:
        try:
            enrich_gov_detail(gov_records, settings, logger)
            logger.info("gov_detail_enriched", extra={"count": len(gov_records)})
        except Exception as exc:
            logger.warning("gov_detail_enrich_failed", extra={"error": str(exc)})

    # --- Phase 2: AI-enhanced classification (optional) ---
    ai_enabled = getattr(settings, 'enable_ai_classification', False)
    if ai_enabled and deduped:
        try:
            openai_client, anthropic_client = build_ai_clients(settings)
            if openai_client or anthropic_client:
                ai_model = getattr(settings, 'ai_model', '')
                classifications = classify_bids_batch(
                    deduped,
                    openai_client=openai_client,
                    anthropic_client=anthropic_client,
                    model=ai_model,
                    log=logger,
                )
                for record, cls in zip(deduped, classifications):
                    record.ai_edu_score = cls.edu_score
                    record.ai_it_score = cls.it_score
                    record.ai_priority = cls.priority
                    record.ai_summary = cls.ai_summary
                    record.ai_reason = f"{cls.edu_reason} | {cls.it_reason}"
                    record.ai_model = cls.model_used
                    if cls.suggested_tags:
                        for tag in cls.suggested_tags:
                            if tag not in record.tags:
                                record.tags.append(tag)
                logger.info("ai_classification_done", extra={"count": len(classifications)})
            else:
                logger.info("ai_classification_skipped_no_client")
        except Exception as exc:
            logger.warning("ai_classification_failed", extra={"error": str(exc)})

    state_store = _resolve_state_store(settings, logger)
    notified_keys = state_store.get_notified_keys()

    recent_cutoff = today - timedelta(days=max(settings.recent_days, 1))
    new_records: list[BidRecord] = []
    for record in deduped:
        if record.uid in notified_keys:
            continue

        # 日期優先抓最近，但保留未通知過項目以降低漏抓風險。
        if record.bid_date and record.bid_date < recent_cutoff:
            logger.info(
                "include_old_unnotified_bid",
                extra={
                    "title": record.title,
                    "bid_date": record.bid_date.isoformat(),
                },
            )
        new_records.append(record)

    # Sort by AI priority first (if available), then date and amount
    priority_order = {"high": 3, "medium": 2, "low": 1, "": 0}
    new_records.sort(
        key=lambda item: (
            priority_order.get(item.ai_priority, 0),
            item.bid_date or today,
            item.amount_value or 0,
        ),
        reverse=True,
    )

    notification_backend = "none"
    notification_sent = False
    errors: list[str] = []

    if not new_records:
        logger.info("no new bids")
    else:
        html_content = render_email_html(
            records=new_records,
            run_date=today,
            high_amount_threshold=settings.high_amount_threshold,
        )

        _write_preview_html_if_needed(settings.preview_html_path, html_content, logger)

        try:
            subject = render_email_subject(settings.email_subject_prefix, today, len(new_records))
            notification_backend = send_email(settings, subject, html_content, logger)
            notification_sent = notification_backend in {"acs", "smtp", "dry_run"}
        except Exception as exc:
            logger.exception("notification_failed", extra={"error": str(exc)})
            errors.append(f"notification_failed: {exc}")

        # --- GitHub Issue tracking for high-priority bids ---
        if getattr(settings, 'github_token', '') and getattr(settings, 'github_repo', ''):
            high_priority = [r for r in new_records if r.ai_priority == "high"]
            if high_priority:
                try:
                    created = create_bid_issues(
                        records=high_priority,
                        token=settings.github_token,
                        repo=settings.github_repo,
                        labels=getattr(settings, 'github_labels', []),
                        logger=logger,
                    )
                    logger.info("github_issues_created", extra={"count": created})
                except Exception as exc:
                    logger.warning("github_issues_failed", extra={"error": str(exc)})

        if persist_state and notification_sent:
            try:
                state_store.mark_notified(new_records)
            except Exception as exc:
                logger.exception("state_mark_failed", extra={"error": str(exc)})
                errors.append(f"state_mark_failed: {exc}")

    return RunResult(
        crawled_count=len(all_records),
        filtered_count=len(filtered),
        deduped_count=len(deduped),
        new_count=len(new_records),
        source_status=source_status,
        notification_sent=notification_sent,
        notification_backend=notification_backend,
        errors=errors,
    )


def _resolve_state_store(settings: Settings, logger: Any) -> Any:
    if settings.azure_storage_connection_string:
        try:
            store = TableStateStore(
                connection_string=settings.azure_storage_connection_string,
                table_name=settings.azure_table_name,
                logger=logger,
            )
            logger.info("state_store_selected", extra={"backend": "table"})
            return store
        except Exception as exc:
            logger.exception("table_store_failed_fallback_blob", extra={"error": str(exc)})

        try:
            store = BlobStateStore(
                connection_string=settings.azure_storage_connection_string,
                container=settings.azure_blob_container,
                blob_name=settings.azure_blob_name,
                logger=logger,
            )
            logger.info("state_store_selected", extra={"backend": "blob"})
            return store
        except Exception as exc:
            logger.exception("blob_store_failed_fallback_memory", extra={"error": str(exc)})

    logger.warning("state_store_selected", extra={"backend": "memory"})
    return InMemoryStateStore()


def _write_preview_html_if_needed(path_str: str, html: str, logger: Any) -> None:
    if not path_str:
        return
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    logger.info("preview_html_written", extra={"path": str(path)})
