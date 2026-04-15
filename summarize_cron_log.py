#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+"
    r"(?P<level>\w+)\s+(?P<logger>\S+)\s+(?P<event>\S+)(?P<extra>.*)$"
)


@dataclass
class DayStats:
    runs: int = 0
    latest_run: dict[str, Any] = field(default_factory=dict)
    keyword_high: int | None = None
    keyword_boundary: int | None = None
    keyword_included_total: int | None = None
    embedding_applied_runs: int = 0
    embedding_recall_done_runs: int = 0
    embedding_candidates_total: int = 0
    embedding_recalled_total: int = 0
    embedding_model_load_failures: int = 0
    embedding_recall_failures: int = 0
    embedding_duration_warnings: int = 0
    embedding_memory_warnings: int = 0
    embedding_ab_summary_count: int = 0
    failure_events: set[str] = field(default_factory=set)


def _extract_number(extra: str, key: str) -> int | None:
    m = re.search(rf"\b{re.escape(key)}=(\d+)\b", extra)
    if not m:
        return None
    return int(m.group(1))


def _extract_result_dict(extra: str) -> dict[str, Any] | None:
    anchor = "result="
    start = extra.find(anchor)
    if start < 0:
        return None

    payload = extra[start + len(anchor):]
    brace_start = payload.find("{")
    if brace_start < 0:
        return None

    depth = 0
    end_idx = None
    for idx, ch in enumerate(payload[brace_start:], start=brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = idx + 1
                break

    if end_idx is None:
        return None

    raw = payload[brace_start:end_idx]
    try:
        data = ast.literal_eval(raw)
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def _build_summary(path: Path) -> dict[str, DayStats]:
    summary: dict[str, DayStats] = defaultdict(DayStats)
    if not path.exists():
        return summary

    previous_line = None
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue
            if line == previous_line:
                continue
            previous_line = line

            m = LINE_RE.match(line)
            if not m:
                continue

            day = m.group("ts").split(" ", 1)[0]
            event = m.group("event")
            extra = m.group("extra")
            s = summary[day]

            if event == "local_run_finished":
                s.runs += 1
                run = _extract_result_dict(extra)
                if run:
                    s.latest_run = run
            elif event == "keyword_screen_distribution":
                s.keyword_high = _extract_number(extra, "high_confidence")
                s.keyword_boundary = _extract_number(extra, "boundary")
                s.keyword_included_total = _extract_number(extra, "included_total")
            elif event == "embedding_recall_applied":
                s.embedding_applied_runs += 1
                original = _extract_number(extra, "original") or 0
                recalled = _extract_number(extra, "recalled") or 0
                s.embedding_candidates_total += original
                s.embedding_recalled_total += recalled
            elif event == "embedding_recall_done":
                s.embedding_recall_done_runs += 1
                candidates = _extract_number(extra, "candidate_count")
                recalled = _extract_number(extra, "recalled")
                if candidates is not None:
                    s.embedding_candidates_total += candidates
                if recalled is not None:
                    s.embedding_recalled_total += recalled
            elif event == "embedding_model_load_failed":
                s.embedding_model_load_failures += 1
                s.failure_events.add(event)
            elif event == "embedding_recall_failed":
                s.embedding_recall_failures += 1
                s.failure_events.add(event)
            elif event == "embedding_duration_warning":
                s.embedding_duration_warnings += 1
            elif event == "embedding_memory_warning":
                s.embedding_memory_warnings += 1
            elif event == "embedding_ab_summary":
                s.embedding_ab_summary_count += 1
            elif event in {"source_failed", "notification_failed", "embedding_ab_failed"}:
                s.failure_events.add(event)

    return summary


def _is_zero_recall_day(stats: DayStats) -> bool:
    embedding_observed = (stats.embedding_applied_runs + stats.embedding_recall_done_runs) > 0
    if not embedding_observed:
        return False
    if stats.embedding_candidates_total <= 0:
        return False
    return stats.embedding_recalled_total == 0


def _compute_zero_recall_streak(days: list[str], summary: dict[str, DayStats]) -> int:
    streak = 0
    for day in reversed(days):
        stats = summary[day]
        embedding_observed = (stats.embedding_applied_runs + stats.embedding_recall_done_runs) > 0
        if not embedding_observed:
            break
        if _is_zero_recall_day(stats):
            streak += 1
        else:
            break
    return streak


def _render_text(days: list[str], summary: dict[str, DayStats], zero_recall_warn_days: int) -> str:
    lines: list[str] = []
    lines.append("=== Cron Daily Summary ===")

    for day in days:
        s = summary[day]
        run = s.latest_run or {}
        source_status = run.get("source_status") if isinstance(run, dict) else []
        source_ok = 0
        source_fail = 0
        if isinstance(source_status, list):
            for item in source_status:
                if not isinstance(item, dict):
                    continue
                if item.get("success"):
                    source_ok += 1
                else:
                    source_fail += 1

        lines.append(f"{day}")
        lines.append(
            "  run="
            f"{s.runs} crawled={run.get('crawled_count', '-') } filtered={run.get('filtered_count', '-') } "
            f"deduped={run.get('deduped_count', '-') } new={run.get('new_count', '-') }"
        )
        lines.append(
            "  source="
            f"ok:{source_ok} fail:{source_fail} "
            f"keyword_high:{s.keyword_high if s.keyword_high is not None else '-'} "
            f"boundary:{s.keyword_boundary if s.keyword_boundary is not None else '-'}"
        )
        lines.append(
            "  embedding="
            f"candidates:{s.embedding_candidates_total} recalled:{s.embedding_recalled_total} "
            f"ab_runs:{s.embedding_ab_summary_count}"
        )
        lines.append(
            "  alerts="
            f"model_load_failed:{s.embedding_model_load_failures} "
            f"recall_failed:{s.embedding_recall_failures} "
            f"timeout_warn:{s.embedding_duration_warnings} "
            f"memory_warn:{s.embedding_memory_warnings}"
        )
        if s.failure_events:
            lines.append("  failures=" + ",".join(sorted(s.failure_events)))

    streak = _compute_zero_recall_streak(days, summary)
    lines.append("=== Health ===")
    lines.append(f"zero_recall_streak={streak}")
    if streak >= zero_recall_warn_days:
        lines.append(
            f"ALERT: zero_recall_streak({streak}) >= EMBEDDING_ZERO_RECALL_WARN_DAYS({zero_recall_warn_days})"
        )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize daily monitor metrics from logs/cron.log")
    parser.add_argument("--log-file", default="logs/cron.log", help="Path to cron log")
    parser.add_argument("--days", type=int, default=7, help="Number of recent days to show")
    parser.add_argument(
        "--zero-recall-warn-days",
        type=int,
        default=3,
        help="Warn when consecutive zero-recall days reach this threshold",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()

    path = Path(args.log_file)
    summary = _build_summary(path)

    days = sorted(summary.keys())
    if args.days > 0:
        days = days[-args.days:]

    if args.json:
        payload = {
            "days": days,
            "zero_recall_streak": _compute_zero_recall_streak(days, summary),
            "zero_recall_warn_days": args.zero_recall_warn_days,
            "daily": {
                d: {
                    "runs": summary[d].runs,
                    "latest_run": summary[d].latest_run,
                    "keyword_high": summary[d].keyword_high,
                    "keyword_boundary": summary[d].keyword_boundary,
                    "keyword_included_total": summary[d].keyword_included_total,
                    "embedding_candidates_total": summary[d].embedding_candidates_total,
                    "embedding_recalled_total": summary[d].embedding_recalled_total,
                    "embedding_ab_summary_count": summary[d].embedding_ab_summary_count,
                    "embedding_model_load_failures": summary[d].embedding_model_load_failures,
                    "embedding_recall_failures": summary[d].embedding_recall_failures,
                    "embedding_duration_warnings": summary[d].embedding_duration_warnings,
                    "embedding_memory_warnings": summary[d].embedding_memory_warnings,
                    "failure_events": sorted(summary[d].failure_events),
                }
                for d in days
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(_render_text(days, summary, args.zero_recall_warn_days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
