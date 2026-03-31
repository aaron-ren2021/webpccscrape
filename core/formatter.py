from __future__ import annotations

from collections import Counter
from datetime import date
from html import escape

from core.filters import count_by_unit_type
from core.models import BidRecord


def render_email_subject(prefix: str, run_date: date, count: int) -> str:
    return f"{prefix} {run_date.isoformat()} 新增 {count} 筆"


def render_markdown(records: list[BidRecord], run_date: date, high_amount_threshold: float) -> str:
    """Render bid records as Markdown table."""
    unit_counts = count_by_unit_type(records)
    tag_counter: Counter[str] = Counter()
    for record in records:
        tag_counter.update(record.tags)

    high_amount_rows = [
        record
        for record in records
        if record.amount_value is not None and record.amount_value >= high_amount_threshold
    ]

    unit_summary = "、".join(f"{k}: {v}" for k, v in sorted(unit_counts.items())) or "無"
    tag_summary = "、".join(f"{tag}({count})" for tag, count in tag_counter.most_common()) or "無"

    high_amount_summary = "；".join(
        f"{item.organization} / {item.title} / {format_amount(item)}"
        for item in high_amount_rows[:5]
    )
    if not high_amount_summary:
        high_amount_summary = "無"

    # AI classification summary
    ai_records = [r for r in records if r.ai_priority]
    ai_high = [r for r in ai_records if r.ai_priority == "high"]
    ai_summary_md = ""
    if ai_records:
        ai_summary_md = f"""
🤖 **AI 分析：**已評估 {len(ai_records)} 筆，高優先 {len(ai_high)} 筆
**AI 模型：**{ai_records[0].ai_model if ai_records else '未使用'}
"""

    # Build markdown table
    header = "| # | 優先度 | 標案名稱 | 單位 | 日期 | 預算金額 | 押標金 | 來源 | 連結 | 標籤 |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    rows = "\n".join(_render_markdown_row(idx + 1, record) for idx, record in enumerate(records))

    return f"""# 教育資訊標案每日監控

**查詢日期：**{run_date.isoformat()}

## 📊 統計摘要
- **今日新增：**{len(records)} 筆
- **單位類型：**{unit_summary}
- **主題標籤：**{tag_summary}
- **高金額案件：**{high_amount_summary}
{ai_summary_md}

## 📋 標案清單

{header}
{rows}
""".strip()


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

    # AI classification summary
    ai_records = [r for r in records if r.ai_priority]
    ai_high = [r for r in ai_records if r.ai_priority == "high"]
    ai_summary_html = ""
    if ai_records:
        ai_summary_html = f"""
      <div><strong>🤖 AI 分析：</strong>已評估 {len(ai_records)} 筆，高優先 {len(ai_high)} 筆</div>
      <div><strong>AI 模型：</strong>{escape(ai_records[0].ai_model) if ai_records else '未使用'}</div>
        """

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
      {ai_summary_html}
    </div>

    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>優先度</th>
          <th>標案名稱</th>
          <th>單位</th>
          <th>日期</th>
          <th>預算金額</th>
          <th>押標金</th>
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
    budget = escape(record.budget_amount) if record.budget_amount else "無提供"
    bid_bond = escape(record.bid_bond) if record.bid_bond else "無提供"

    # Priority badge
    priority_map = {
        "high": '<span style="color:#dc2626;font-weight:bold">🔴 高</span>',
        "medium": '<span style="color:#d97706">🟡 中</span>',
        "low": '<span style="color:#6b7280">⚪ 低</span>',
    }
    priority_html = priority_map.get(record.ai_priority, "—")

    if link:
        link_html = f'<a href="{link}" target="_blank" rel="noreferrer">查看</a>'
    else:
        link_html = ""

    return f"""
<tr>
  <td>{index}</td>
  <td>{priority_html}</td>
  <td>{title}</td>
  <td>{org}</td>
  <td>{escape(bid_date)}</td>
  <td>{budget}</td>
  <td>{bid_bond}</td>
  <td>{escape(source_text)}</td>
  <td>{link_html}</td>
  <td>{escape(tags)}</td>
</tr>
""".strip()


def format_amount(record: BidRecord) -> str:
    if record.amount_value is not None:
        return f"NT$ {int(record.amount_value):,}"
    return record.amount_raw or ""
