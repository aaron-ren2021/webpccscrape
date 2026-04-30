from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from crawler.gov import fetch_bids as fetch_gov_bids
from crawler.gov import enrich_detail as enrich_gov_detail
from crawler.taiwanbuying import fetch_bids as fetch_taiwanbuying_bids
from crawler.g0v import fetch_bids as fetch_g0v_bids
from crawler.g0v import enrich_record as enrich_g0v_record
from core.ai_classifier import AIClassification, build_ai_clients, classify_bids_batch
from core.config import Settings
from core.dedup import deduplicate_bids
from core.filters import filter_bids
from core.formatter import find_earliest_deadline, render_email_html, render_email_subject
from core.models import BidRecord, RunResult, SourceRunStatus
from core.normalize import is_bid_deadline_expired
from core.stable_keys import effective_record_date, notification_keys, primary_notification_key
from notify.dispatcher import send_email
from notify.github_notify import create_bid_issues
from storage.blob_store import BlobStateStore
from storage.local_state_store import LocalJsonStateStore
from storage.table_store import TableStateStore
from crawler.common import build_session


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

    # Define sources to fetch
    sources = [
        ("taiwanbuying", fetch_taiwanbuying_bids),
        ("gov_pcc", fetch_gov_bids),
    ]
    
    # Add g0v if enabled
    if settings.g0v_enabled:
        sources.append(("g0v", fetch_g0v_bids))

    for source_name, fn in sources:
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
        _assign_stable_uid(record)

    # --- Phase 1.5: Enrich detail fields (budget, bid bond) for filtered records ---
    gov_records = [r for r in deduped if r.source == "gov_pcc"]
    if gov_records:
        try:
            enrich_gov_detail(gov_records, settings, logger)
            logger.info("gov_detail_enriched", extra={"count": len(gov_records)})
        except Exception as exc:
            logger.warning("gov_detail_enrich_failed", extra={"error": str(exc)})

        summary = _build_bid_bond_unparsed_summary(gov_records, settings)
        logger.info("bid_bond_unparsed_summary", extra=summary)

    g0v_records = [r for r in deduped if r.source == "g0v"]
    g0v_link_counts = {
        "resolved_official": 0,
        "fallback_api": 0,
        "unresolved": 0,
    }
    if g0v_records:
        try:
            session = build_session(settings)
            for record in g0v_records:
                enrich_g0v_record(record, settings, logger, session=session)
                state = str(record.metadata.get("g0v_link_resolution_state", "")).strip().lower()
                if state not in g0v_link_counts:
                    state = "unresolved"
                g0v_link_counts[state] += 1
            logger.info(
                "g0v_link_resolution_summary",
                extra={
                    "count": len(g0v_records),
                    "g0v_link_resolved_count": g0v_link_counts["resolved_official"],
                    "g0v_link_fallback_api_count": g0v_link_counts["fallback_api"],
                    "g0v_link_unresolved_count": g0v_link_counts["unresolved"],
                },
            )
        except Exception as exc:
            logger.warning("g0v_link_resolution_failed", extra={"error": str(exc)})

    active_records = _exclude_expired_deadline_records(deduped, now_tw, logger)
    for record in active_records:
        _assign_stable_uid(record)

    # --- Phase 2: AI-enhanced classification (optional) ---
    ai_enabled = getattr(settings, 'enable_ai_classification', False)
    if ai_enabled and active_records:
        try:
            openai_client, anthropic_client = build_ai_clients(settings)
            if openai_client or anthropic_client:
                ai_model = getattr(settings, 'ai_model', '')
                classifications = classify_bids_batch(
                    active_records,
                    openai_client=openai_client,
                    anthropic_client=anthropic_client,
                    model=ai_model,
                    log=logger,
                )
                for record, cls in zip(active_records, classifications):
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
    for record in active_records:
        keys = notification_keys(record)
        if any(key in notified_keys for key in keys):
            continue

        record_date = effective_record_date(record)
        if record_date is None:
            reason = "catch_up_unknown_date"
        elif record_date >= recent_cutoff:
            reason = "new_recent"
        else:
            reason = "catch_up_unnotified"

        record.metadata["notification_candidate_reason"] = reason
        if reason != "new_recent":
            logger.info(
                "include_old_unnotified_bid",
                extra={
                    "title": record.title,
                    "bid_date": record.bid_date.isoformat() if record.bid_date else "",
                    "announcement_date": record.announcement_date.isoformat() if record.announcement_date else "",
                    "reason": reason,
                },
            )
        new_records.append(record)

    # Sort by AI priority first (if available), then date and amount
    priority_order = {"high": 3, "medium": 2, "low": 1, "": 0}
    new_records.sort(
        key=lambda item: (
            priority_order.get(item.ai_priority, 0),
            1 if effective_record_date(item) else 0,
            effective_record_date(item) or date.min,
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
            # Find earliest deadline for subject line (normalized to CE format)
            earliest_deadline = find_earliest_deadline(new_records)
            
            subject = render_email_subject(
                settings.email_subject_prefix,
                today,
                len(new_records),
                earliest_deadline=earliest_deadline,
            )
            logger.info("email_subject_generated", extra={"subject": subject})
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


def _exclude_expired_deadline_records(
    records: list[BidRecord],
    now_tw: datetime,
    logger: Any,
) -> list[BidRecord]:
    active_records: list[BidRecord] = []
    for record in records:
        deadline = (record.bid_deadline or "").strip()
        if deadline and is_bid_deadline_expired(deadline, now_tw):
            logger.info(
                "expired_bid_deadline_skipped",
                extra={
                    "title": record.title,
                    "deadline": deadline,
                    "source": record.source,
                },
            )
            continue
        active_records.append(record)
    return active_records


def _assign_stable_uid(record: BidRecord) -> None:
    record.uid = primary_notification_key(record)


def _build_bid_bond_unparsed_summary(
    records: list[BidRecord],
    settings: Settings,
) -> dict[str, Any]:
    unparsed_defaults = {"需繳納", "未公開"}
    unparsed_records: list[BidRecord] = []

    for record in records:
        raw = str(record.metadata.get("bid_bond_raw", "")).strip()
        if not raw:
            continue
        bid_bond = (record.bid_bond or "").strip()
        if not bid_bond or bid_bond in unparsed_defaults:
            unparsed_records.append(record)

    raw_limit = max(settings.bid_bond_unparsed_raw_truncate, 0)
    sample_size = max(settings.bid_bond_unparsed_sample_size, 0)
    top_n = max(settings.bid_bond_unparsed_top_n, 0)

    raw_counter: Counter[str] = Counter()
    for record in unparsed_records:
        raw_value = _sanitize_bid_bond_raw(
            str(record.metadata.get("bid_bond_raw", "")),
            raw_limit,
        )
        if raw_value:
            raw_counter[raw_value] += 1

    top_patterns: list[dict[str, Any]] = []
    if top_n > 0:
        for raw, count in raw_counter.most_common(top_n):
            top_patterns.append({"raw": raw, "count": count})

    samples: list[dict[str, Any]] = []
    if sample_size > 0:
        for record in unparsed_records[:sample_size]:
            raw_value = _sanitize_bid_bond_raw(
                str(record.metadata.get("bid_bond_raw", "")),
                raw_limit,
            )
            samples.append(
                {
                    "title": record.title[:200],
                    "organization": record.organization[:120],
                    "url": record.url,
                    "bid_bond_raw": raw_value,
                    "bid_bond": record.bid_bond,
                }
            )

    return {
        "unparsed_count": len(unparsed_records),
        "top_patterns": top_patterns,
        "sample_count": len(samples),
        "samples": samples,
    }


def _sanitize_bid_bond_raw(value: str, limit: int) -> str:
    cleaned = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    cleaned = " ".join(cleaned.split())
    if limit > 0:
        cleaned = cleaned[:limit]
    return (
        cleaned.replace("[", "(")
        .replace("]", ")")
        .replace("{", "(")
        .replace("}", ")")
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

    store = LocalJsonStateStore(
        path=Path("state/notified_state.json"),
        logger=logger,
        retention_days=getattr(settings, "state_retention_days", 90),
    )
    logger.info("state_store_selected", extra={"backend": "local_json", "path": "state/notified_state.json"})
    return store


def _write_preview_html_if_needed(path_str: str, html: str, logger: Any) -> None:
    if not path_str:
        return
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    logger.info("preview_html_written", extra={"path": str(path)})
