from __future__ import annotations

import logging
import os
import resource
import time
import copy
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
from core.filters import screen_bids
from core.formatter import render_email_html, render_email_subject
from core.models import BidRecord, RunResult, SourceRunStatus
from core.normalize import build_bid_uid
from notify.dispatcher import send_email
from notify.github_notify import create_bid_issues
from storage.blob_store import BlobStateStore
from storage.table_store import TableStateStore

MAX_G0V_ENRICH_PER_RUN = 40
MAX_GOV_FALLBACK_PER_RUN = 12


def _process_memory_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if os.name == "posix" and "darwin" in os.sys.platform:
        return usage / (1024 * 1024)
    return usage / 1024


def _log_perf_warning(logger: Any, settings: Settings, *, step_name: str, duration_ms: float, memory_mb: float) -> None:
    if duration_ms >= settings.embedding_timeout_warn_ms:
        logger.warning(
            "embedding_duration_warning",
            extra={
                "step_name": step_name,
                "duration_ms": round(duration_ms, 2),
                "memory_mb": round(memory_mb, 2),
                "warn_threshold_ms": settings.embedding_timeout_warn_ms,
            },
        )
    if memory_mb >= settings.embedding_memory_warn_mb:
        logger.warning(
            "embedding_memory_warning",
            extra={
                "step_name": step_name,
                "duration_ms": round(duration_ms, 2),
                "memory_mb": round(memory_mb, 2),
                "warn_threshold_mb": settings.embedding_memory_warn_mb,
            },
        )


def _build_ab_rows(records: list[BidRecord], *, model_name: str, threshold: float, decision_source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        metadata = record.metadata or {}
        rows.append(
            {
                "uid": record.uid,
                "title": record.title,
                "keyword_confidence": metadata.get("keyword_confidence", ""),
                "embedding_similarity": metadata.get("embedding_similarity"),
                "embedding_best_category": metadata.get("embedding_best_category", ""),
                "decision_source": decision_source,
                "model_name": model_name,
                "threshold": threshold,
            }
        )
    return rows


def _log_embedding_ab_comparison(
    logger: Any,
    *,
    primary_rows: list[dict[str, Any]],
    ab_rows: list[dict[str, Any]],
    primary_model: str,
    primary_threshold: float,
    ab_model: str,
    ab_threshold: float,
) -> None:
    for row in primary_rows:
        logger.info("embedding_ab_dataset_row", extra={**row, "variant": "primary"})
    for row in ab_rows:
        logger.info("embedding_ab_dataset_row", extra={**row, "variant": "ab"})

    primary_map = {row["uid"]: row for row in primary_rows}
    ab_map = {row["uid"]: row for row in ab_rows}
    all_uids = sorted(set(primary_map) | set(ab_map))
    changed = 0

    for uid in all_uids:
        primary = primary_map.get(uid)
        ab = ab_map.get(uid)
        primary_decision = "kept" if primary else "dropped"
        ab_decision = "kept" if ab else "dropped"
        if primary_decision != ab_decision:
            changed += 1
        sample = primary or ab or {}
        logger.info(
            "embedding_ab_row",
            extra={
                "uid": uid,
                "title": sample.get("title", ""),
                "keyword_confidence": sample.get("keyword_confidence", ""),
                "primary_decision_source": primary["decision_source"] if primary else "not_selected",
                "ab_decision_source": ab["decision_source"] if ab else "not_selected",
                "primary_embedding_similarity": primary["embedding_similarity"] if primary else None,
                "ab_embedding_similarity": ab["embedding_similarity"] if ab else None,
                "primary_embedding_best_category": primary["embedding_best_category"] if primary else "",
                "ab_embedding_best_category": ab["embedding_best_category"] if ab else "",
                "primary_model_name": primary_model,
                "ab_model_name": ab_model,
                "primary_threshold": primary_threshold,
                "ab_threshold": ab_threshold,
                "decision_changed": primary_decision != ab_decision,
            },
        )

    logger.info(
        "embedding_ab_summary",
        extra={
            "primary_model_name": primary_model,
            "ab_model_name": ab_model,
            "primary_threshold": primary_threshold,
            "ab_threshold": ab_threshold,
            "primary_count": len(primary_rows),
            "ab_count": len(ab_rows),
            "changed_count": changed,
        },
    )


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

    # API-only mode: 專門使用 openfun API 來源，避免直接爬兩個網站列表頁。
    if settings.api_only_mode:
        sources = [("g0v", fetch_g0v_bids)]
    else:
        sources = [
            ("taiwanbuying", fetch_taiwanbuying_bids),
            ("gov_pcc", fetch_gov_bids),
        ]
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

    # --- Phase 1: keyword screen + dedup ---
    keyword_high, keyword_boundary, keyword_stats = screen_bids(all_records)
    filtered = keyword_high + keyword_boundary
    logger.info(
        "keyword_screen_distribution",
        extra={
            "high_confidence": len(keyword_high),
            "boundary": len(keyword_boundary),
            "excluded_low_score": keyword_stats.get("excluded_low_score", 0),
            "excluded_strong": keyword_stats.get("excluded_strong", 0),
            "included_total": len(filtered),
        },
    )
    deduped = deduplicate_bids(filtered)

    for record in deduped:
        record.uid = build_bid_uid(
            title=record.title,
            org=record.organization,
            bid_date=record.bid_date,
            amount=record.amount_value,
            amount_raw=record.amount_raw,
        )

    keyword_high_confidence = [record for record in deduped if record.metadata.get("keyword_confidence") == "high_confidence"]
    keyword_boundary_candidates = [record for record in deduped if record.metadata.get("keyword_confidence") == "boundary"]

    # --- Phase 1.75: Embedding semantic recall (optional) ---
    embedding_enabled = getattr(settings, 'enable_embedding_recall', False)
    final_candidates = keyword_high_confidence
    if embedding_enabled and keyword_boundary_candidates:
        try:
            from core.embedding_recall import recall_bids_with_embedding
            
            original_count = len(keyword_boundary_candidates)
            primary_model = settings.embedding_model
            primary_top_k = settings.embedding_top_k
            primary_threshold = settings.embedding_similarity_threshold
            recall_start = time.perf_counter()
            recalled_boundary = recall_bids_with_embedding(
                keyword_boundary_candidates,
                model_name=primary_model,
                top_k=primary_top_k,
                similarity_threshold=primary_threshold,
                log=logger,
            )
            recall_duration_ms = (time.perf_counter() - recall_start) * 1000
            recall_memory_mb = _process_memory_mb()
            logger.info(
                "embedding_recall_pipeline_step",
                extra={
                    "step_name": "embedding_recall_pipeline",
                    "duration_ms": round(recall_duration_ms, 2),
                    "candidate_count": original_count,
                    "result_count": len(recalled_boundary),
                    "memory_mb": round(recall_memory_mb, 2),
                    "model_name": primary_model,
                    "threshold": primary_threshold,
                    "top_k": primary_top_k,
                },
            )
            _log_perf_warning(
                logger,
                settings,
                step_name="embedding_recall_pipeline",
                duration_ms=recall_duration_ms,
                memory_mb=recall_memory_mb,
            )
            for record in recalled_boundary:
                record.metadata["filter_source"] = "keyword_boundary_embedding"
                record.metadata["keyword_confidence"] = "high_confidence"
            final_candidates = keyword_high_confidence + recalled_boundary
            logger.info(
                "embedding_recall_applied",
                extra={
                    "original": original_count,
                    "recalled": len(recalled_boundary),
                    "filtered_out": original_count - len(recalled_boundary),
                }
            )

            if settings.embedding_enable_ab_test:
                ab_model = settings.embedding_ab_model or primary_model
                ab_threshold = settings.embedding_ab_similarity_threshold
                ab_top_k = settings.embedding_ab_top_k
                try:
                    ab_recalled = recall_bids_with_embedding(
                        copy.deepcopy(keyword_boundary_candidates),
                        model_name=ab_model,
                        top_k=ab_top_k,
                        similarity_threshold=ab_threshold,
                        log=logger,
                    )
                    primary_rows = _build_ab_rows(
                        recalled_boundary,
                        model_name=primary_model,
                        threshold=primary_threshold,
                        decision_source="keyword_boundary_embedding_primary",
                    )
                    ab_rows = _build_ab_rows(
                        ab_recalled,
                        model_name=ab_model,
                        threshold=ab_threshold,
                        decision_source="keyword_boundary_embedding_ab",
                    )
                    _log_embedding_ab_comparison(
                        logger,
                        primary_rows=primary_rows,
                        ab_rows=ab_rows,
                        primary_model=primary_model,
                        primary_threshold=primary_threshold,
                        ab_model=ab_model,
                        ab_threshold=ab_threshold,
                    )
                except Exception as exc:
                    logger.warning("embedding_ab_failed", extra={"error": str(exc)})
        except ImportError:
            logger.warning(
                "embedding_recall_skipped_dependency_missing",
                extra={"hint": "Install: pip install sentence-transformers scikit-learn"}
            )
        except Exception as exc:
            logger.warning("embedding_recall_failed", extra={"error": str(exc)})
            # Graceful fallback: continue with original deduped list
            final_candidates = keyword_high_confidence
    elif keyword_boundary_candidates:
        logger.info(
            "embedding_boundary_skipped",
            extra={"count": len(keyword_boundary_candidates), "reason": "embedding_disabled"},
        )

    deduped = final_candidates

    # --- Phase 2: AI-enhanced classification (optional) ---
    ai_enabled = getattr(settings, 'enable_ai_classification', False)
    if ai_enabled and deduped:
        try:
            openai_client, anthropic_client = build_ai_clients(settings)
            if openai_client or anthropic_client:
                ai_model = getattr(settings, 'ai_model', '') or getattr(settings, 'ollama_model', 'qwen2.5:3b')
                
                # 🔥 決定是否使用驗證模式（Ollama 用驗證模式，OpenAI/Anthropic 用完整模式）
                use_validation = getattr(settings, 'use_validation_mode', False)
                is_ollama = bool(getattr(settings, 'ollama_base_url', ''))
                validation_mode = use_validation and is_ollama
                
                logger.info(
                    "ai_classification_starting",
                    extra={
                        "mode": "validation" if validation_mode else "full",
                        "model": ai_model,
                        "is_ollama": is_ollama,
                    }
                )
                
                classifications = classify_bids_batch(
                    deduped,
                    openai_client=openai_client,
                    anthropic_client=anthropic_client,
                    model=ai_model,
                    log=logger,
                    validation_mode=validation_mode,
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
    new_records = _collect_notification_candidates(deduped, notified_keys, today, settings, logger)

    # --- Phase 1.9: Hybrid enrichment (g0v API first, gov detail fallback) ---
    # 只對最終通知候選做補值，避免把 API/爬蟲時間花在不會發送的資料。
    if new_records:
        _run_hybrid_enrichment(new_records, settings, logger)

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
            # Find earliest deadline for subject line
            earliest_deadline = None
            for record in new_records:
                if record.bid_date:
                    if earliest_deadline is None or record.bid_date < earliest_deadline:
                        earliest_deadline = record.bid_date
            
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


def _run_hybrid_enrichment(records: list[BidRecord], settings: Settings, logger: Any) -> None:
    target_records = _prioritize_enrichment_targets(records)
    throttle_limit = _resolve_int_setting(settings, "hybrid_g0v_enrich_max", MAX_G0V_ENRICH_PER_RUN)
    g0v_targets = target_records[:throttle_limit]
    throttled_records = target_records[throttle_limit:]

    if throttled_records:
        logger.info(
            "hybrid_g0v_throttled",
            extra={
                "attempting": len(g0v_targets),
                "skipped": len(throttled_records),
                "limit": throttle_limit,
            },
        )
        for record in throttled_records:
            if not str(record.metadata.get("enrichment_source", "")).strip():
                _set_enrichment_marker(record, "list_only", "throttled_before_g0v_enrichment")

    g0v_attempted = 0
    g0v_enriched = 0
    gov_fallback_candidates: list[BidRecord] = []

    for record in g0v_targets:
        if _needs_enrichment(record):
            g0v_attempted += 1
            try:
                if settings.g0v_enabled and enrich_g0v_record(record, settings, logger):
                    g0v_enriched += 1
            except Exception as exc:
                logger.warning("hybrid_g0v_enrich_failed", extra={"error": str(exc), "title": record.title})

        if _needs_enrichment(record) and _can_use_gov_detail_fallback(record):
            gov_fallback_candidates.append(record)

    logger.info(
        "hybrid_g0v_pass_done",
        extra={
            "attempted": g0v_attempted,
            "enriched": g0v_enriched,
            "missing_after_g0v": len(gov_fallback_candidates),
        },
    )

    gov_limit = _resolve_int_setting(settings, "hybrid_gov_fallback_max", MAX_GOV_FALLBACK_PER_RUN)
    if len(gov_fallback_candidates) > gov_limit:
        logger.info(
            "hybrid_gov_fallback_throttled",
            extra={
                "attempting": gov_limit,
                "skipped": len(gov_fallback_candidates) - gov_limit,
                "limit": gov_limit,
            },
        )
    gov_fallback_targets = gov_fallback_candidates[:gov_limit]

    if gov_fallback_targets:
        before_state = {
            id(record): (record.budget_amount or "", record.bid_bond or "")
            for record in gov_fallback_targets
        }
        try:
            enrich_gov_detail(gov_fallback_targets, settings, logger)
        except Exception as exc:
            logger.warning("hybrid_gov_fallback_failed", extra={"error": str(exc)})

        gov_enriched = 0
        for record in gov_fallback_targets:
            prev_budget, prev_bond = before_state[id(record)]
            if _has_detail_progress(prev_budget, prev_bond, record):
                gov_enriched += 1
                _set_enrichment_marker(record, "gov_detail", "gov_detail_fallback_after_g0v")

        logger.info(
            "hybrid_gov_fallback_done",
            extra={
                "attempted": len(gov_fallback_targets),
                "enriched": gov_enriched,
            },
        )

    for record in records:
        if str(record.metadata.get("enrichment_source", "")).strip():
            continue
        if _needs_enrichment(record):
            _set_enrichment_marker(record, "list_only", "detail_missing_after_hybrid")
        else:
            _set_enrichment_marker(record, "list_only", "detail_already_present")


def _can_use_gov_detail_fallback(record: BidRecord) -> bool:
    if not record.url:
        return False
    if "web.pcc.gov.tw" not in record.url:
        return False

    if record.source == "gov_pcc":
        return True
    if record.backup_source:
        return "gov_pcc" in {s.strip() for s in record.backup_source.split(",")}
    return False


def _has_detail_progress(previous_budget: str, previous_bond: str, record: BidRecord) -> bool:
    budget_progress = _is_missing_detail_value(previous_budget) and (not _is_missing_detail_value(record.budget_amount))
    bond_progress = _is_missing_detail_value(previous_bond) and (not _is_missing_detail_value(record.bid_bond))
    return budget_progress or bond_progress


def _needs_enrichment(record: BidRecord) -> bool:
    return _is_missing_detail_value(record.budget_amount) or _is_missing_detail_value(record.bid_bond)


def _is_missing_detail_value(value: str) -> bool:
    text = value.strip().lower() if value else ""
    return text in {"", "none", "null", "無", "無提供", "n/a", "詳見連結"}


def _set_enrichment_marker(record: BidRecord, source: str, note: str) -> None:
    current_source = str(record.metadata.get("enrichment_source", "")).strip()
    if current_source:
        parts = [part for part in current_source.split("+") if part]
        if source not in parts:
            parts.append(source)
        record.metadata["enrichment_source"] = "+".join(parts)
    else:
        record.metadata["enrichment_source"] = source
    record.metadata["enrichment_note"] = note


def _collect_notification_candidates(
    records: list[BidRecord],
    notified_keys: set[str],
    today: date,
    settings: Settings,
    logger: Any,
) -> list[BidRecord]:
    recent_cutoff = today - timedelta(days=max(settings.recent_days, 1))
    candidates: list[BidRecord] = []
    for record in records:
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
        candidates.append(record)
    return candidates


def _prioritize_enrichment_targets(records: list[BidRecord]) -> list[BidRecord]:
    return sorted(
        [record for record in records if _needs_enrichment(record)],
        key=lambda item: (
            item.bid_date or datetime.max.date(),
            0 if item.source == "gov_pcc" else 1,
            item.title,
        ),
    )


def _resolve_int_setting(settings: Settings, field_name: str, default: int) -> int:
    value = getattr(settings, field_name, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0)


def _write_preview_html_if_needed(path_str: str, html: str, logger: Any) -> None:
    if not path_str:
        return
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    logger.info("preview_html_written", extra={"path": str(path)})
