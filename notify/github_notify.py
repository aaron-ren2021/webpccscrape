"""GitHub Issue integration for high-priority bid tracking.

Creates GitHub Issues for important bids so teams can track and discuss
whether to submit proposals.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from core.models import BidRecord

logger = logging.getLogger("bid-monitor.github")

ISSUE_BODY_TEMPLATE = """\
## 標案追蹤

| 項目 | 內容 |
|------|------|
| **機關** | {org} |
| **標案名稱** | {title} |
| **日期** | {bid_date} |
| **金額** | {amount} |
| **來源** | {source} |
| **連結** | {url} |
| **AI 優先度** | {priority} |
| **AI 摘要** | {ai_summary} |

### AI 分析
- 教育相關分數：{edu_score}/10
- 資訊相關分數：{it_score}/10
- 分析理由：{ai_reason}
- 標籤：{tags}

---
*此 Issue 由標案監控系統自動建立*
"""


def create_bid_issues(
    records: list[BidRecord],
    token: str,
    repo: str,
    labels: list[str] | None = None,
    logger: Any | None = None,
) -> int:
    """Create GitHub Issues for high-priority bid records.

    Args:
        records: list of BidRecord to create issues for
        token: GitHub personal access token
        repo: owner/repo format (e.g. "aaron-ren2021/webpccscrape")
        labels: optional list of labels to apply
        logger: optional logger

    Returns:
        number of issues created
    """
    log = logger or globals()["logger"]
    created = 0

    for record in records:
        try:
            _create_single_issue(record, token, repo, labels or [], log)
            created += 1
        except Exception as exc:
            log.warning(
                "github_issue_create_failed",
                extra={"title": record.title, "error": str(exc)},
            )

    return created


def _create_single_issue(
    record: BidRecord,
    token: str,
    repo: str,
    labels: list[str],
    log: Any,
) -> None:
    """Create a single GitHub Issue for a bid record."""
    title = f"[標案] {record.organization} - {record.title}"
    if len(title) > 256:
        title = title[:253] + "..."

    body = ISSUE_BODY_TEMPLATE.format(
        org=record.organization,
        title=record.title,
        bid_date=record.bid_date.isoformat() if record.bid_date else "未知",
        amount=f"NT$ {int(record.amount_value):,}" if record.amount_value else record.amount_raw or "未公開",
        source=record.source,
        url=record.url or "無",
        priority=record.ai_priority or "未評估",
        ai_summary=record.ai_summary or "無",
        edu_score=record.ai_edu_score,
        it_score=record.ai_it_score,
        ai_reason=record.ai_reason or "無",
        tags=", ".join(record.tags) if record.tags else "無",
    )

    issue_labels = list(labels)
    if record.ai_priority == "high":
        issue_labels.append("high-priority")
    issue_labels.append("bid-tracking")

    payload = json.dumps({
        "title": title,
        "body": body,
        "labels": issue_labels,
    }).encode("utf-8")

    url = f"https://api.github.com/repos/{repo}/issues"
    req = Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            log.info(
                "github_issue_created",
                extra={
                    "issue_number": result.get("number"),
                    "html_url": result.get("html_url"),
                    "title": title,
                },
            )
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        log.error(
            "github_api_error",
            extra={"status": exc.code, "body": error_body[:500]},
        )
        raise
