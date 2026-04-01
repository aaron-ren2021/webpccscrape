from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass(slots=True)
class BidRecord:
    title: str
    organization: str
    bid_date: Optional[date]
    amount_raw: str
    amount_value: Optional[float]
    source: str
    url: str
    summary: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    unit_type: str = "其他"
    original_source: str = ""
    backup_source: Optional[str] = None
    uid: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # Detail page fields
    budget_amount: str = ""
    bid_bond: str = ""
    bid_deadline: str = ""  # 截止投標時間
    bid_opening_time: str = ""  # 開標時間

    # AI classification fields
    ai_edu_score: int = 0
    ai_it_score: int = 0
    ai_priority: str = ""
    ai_summary: str = ""
    ai_reason: str = ""
    ai_model: str = ""

    def __post_init__(self) -> None:
        if not self.original_source:
            self.original_source = self.source


@dataclass(slots=True)
class SourceRunStatus:
    source: str
    success: bool
    count: int
    error: str = ""


@dataclass(slots=True)
class RunResult:
    crawled_count: int
    filtered_count: int
    deduped_count: int
    new_count: int
    source_status: list[SourceRunStatus]
    notification_sent: bool
    notification_backend: str
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "crawled_count": self.crawled_count,
            "filtered_count": self.filtered_count,
            "deduped_count": self.deduped_count,
            "new_count": self.new_count,
            "notification_sent": self.notification_sent,
            "notification_backend": self.notification_backend,
            "errors": self.errors,
            "source_status": [
                {
                    "source": s.source,
                    "success": s.success,
                    "count": s.count,
                    "error": s.error,
                }
                for s in self.source_status
            ],
        }
