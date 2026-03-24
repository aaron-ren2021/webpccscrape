from __future__ import annotations

from collections import Counter
from datetime import date
from html import escape

from core.filters import count_by_unit_type
from core.models import BidRecord


def render_email_subject(prefix: str, run_date: date, count: int) -> str:
    return f"{prefix} {run_date.isoformat()} 新增 {count} 筆"


def render_email_html(records: list[BidRecord], run_date: date, high_amount_threshold: float) -> str:
    unit_counts = count_by_unit_type(records)
    tag_counter: Counter[str] = Counter()
    for record in records:
        tag_counter.update(record.tags)

    high_amount_rows = [
        record
        for record in records
        if record.amount_value is not None and record.amount_value >= high_amount_threshold
    ]

    unit_summary = "、".join(f"{escape(k)}: {v}" for k, v in sorted(unit_counts.items())) or "無"
    tag_summary = "、".join(f"{escape(tag)}({count})" for tag, count in tag_counter.most_common()) or "無"

    high_amount_summary = "；".join(
        f"{escape(item.organization)} / {escape(item.title)} / {format_amount(item)}"
        for item in high_amount_rows[:5]
    )
    if not high_amount_summary:
        high_amount_summary = "無"

    rows = "\n".join(_render_row(idx + 1, record) for idx, record in enumerate(records))

    return f"""
<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8" />
    <style>
      body {{ font-family: 'Noto Sans TC', 'Microsoft JhengHei', sans-serif; color: #1f2937; line-height: 1.5; }}
      .summary {{ margin-bottom: 14px; padding: 12px; background: #f3f4f6; border-radius: 8px; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; vertical-align: top; }}
      th {{ background: #111827; color: #f9fafb; }}
      .small {{ color: #6b7280; font-size: 12px; }}
    </style>
  </head>
  <body>
    <h2>教育資訊標案每日監控</h2>
    <p class="small">查詢日期：{escape(run_date.isoformat())}</p>
    <div class="summary">
      <div><strong>今日新增：</strong>{len(records)} 筆</div>
      <div><strong>單位類型：</strong>{unit_summary}</div>
      <div><strong>主題標籤：</strong>{tag_summary}</div>
      <div><strong>高金額案件：</strong>{escape(high_amount_summary)}</div>
    </div>

    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>標案名稱</th>
          <th>單位</th>
          <th>日期</th>
          <th>金額</th>
          <th>來源</th>
          <th>連結</th>
          <th>標籤</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </body>
</html>
""".strip()


def _render_row(index: int, record: BidRecord) -> str:
    bid_date = record.bid_date.isoformat() if record.bid_date else ""
    tags = ", ".join(record.tags)
    source_text = record.source
    if record.backup_source:
        source_text = f"{record.source} (backup: {record.backup_source})"

    link = escape(record.url or "")
    title = escape(record.title)
    org = escape(record.organization)
    amount = escape(format_amount(record))

    if link:
        link_html = f'<a href="{link}" target="_blank" rel="noreferrer">查看</a>'
    else:
        link_html = ""

    return f"""
<tr>
  <td>{index}</td>
  <td>{title}</td>
  <td>{org}</td>
  <td>{escape(bid_date)}</td>
  <td>{amount}</td>
  <td>{escape(source_text)}</td>
  <td>{link_html}</td>
  <td>{escape(tags)}</td>
</tr>
""".strip()


def format_amount(record: BidRecord) -> str:
    if record.amount_value is not None:
        return f"NT$ {int(record.amount_value):,}"
    return record.amount_raw or ""
