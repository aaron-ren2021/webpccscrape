from __future__ import annotations

from collections import Counter
from datetime import date
from html import escape
from typing import Optional

from core.filters import count_by_unit_type
from core.models import BidRecord


def render_email_subject(prefix: str, run_date: date, count: int, earliest_deadline: Optional[date] = None) -> str:
    """Render email subject with optional earliest deadline."""
    base = f"{prefix} {run_date.isoformat()} 新增 {count} 筆"
    if earliest_deadline:
        return f"{base}｜最緊急截止 {earliest_deadline.isoformat()}"
    return base




def render_email_html(records: list[BidRecord], run_date: date, high_amount_threshold: float) -> str:
    """Render email HTML with card-based layout."""
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

    cards = "\n".join(_render_card(idx + 1, record) for idx, record in enumerate(records))

    return f"""
<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
      body {{
        font-family: 'Noto Sans TC', 'Microsoft JhengHei', sans-serif;
        color: #1f2937;
        line-height: 1.6;
        margin: 0;
        padding: 16px;
        background: #f9fafb;
      }}
      .container {{
        max-width: 800px;
        margin: 0 auto;
        background: #ffffff;
        padding: 24px;
        border-radius: 8px;
      }}
      .header {{
        border-bottom: 2px solid #e5e7eb;
        padding-bottom: 16px;
        margin-bottom: 20px;
      }}
      .header h2 {{
        margin: 0 0 8px 0;
        color: #111827;
        font-size: 24px;
      }}
      .header .meta {{
        color: #6b7280;
        font-size: 14px;
      }}
      .summary {{
        margin-bottom: 24px;
        padding: 16px;
        background: #f3f4f6;
        border-radius: 8px;
        border-left: 4px solid #3b82f6;
      }}
      .summary div {{
        margin: 4px 0;
        font-size: 14px;
      }}
      .bid-card {{
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        transition: box-shadow 0.2s;
      }}
      .bid-card:hover {{
        box-shadow: 0 4px 6px rgba(0,0,0,0.15);
      }}
      .card-header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 12px;
        gap: 12px;
      }}
      .card-title {{
        font-size: 16px;
        font-weight: bold;
        color: #111827;
        flex: 1;
        line-height: 1.4;
      }}
      .card-index {{
        background: #e5e7eb;
        color: #374151;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: bold;
        white-space: nowrap;
      }}
      .card-body {{
        display: grid;
        gap: 8px;
      }}
      .card-row {{
        display: flex;
        gap: 8px;
        font-size: 14px;
      }}
      .card-label {{
        color: #6b7280;
        min-width: 80px;
        flex-shrink: 0;
      }}
      .card-value {{
        color: #1f2937;
        flex: 1;
      }}
      .amount-bold {{
        font-weight: bold;
        color: #059669;
        font-size: 15px;
      }}
      .deadline-red {{
        font-weight: bold;
        color: #dc2626;
      }}
      .priority-badge {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: bold;
      }}
      .priority-high {{
        background: #fee2e2;
        color: #dc2626;
      }}
      .priority-medium {{
        background: #fef3c7;
        color: #d97706;
      }}
      .priority-low {{
        background: #f3f4f6;
        color: #6b7280;
      }}
      .tag {{
        display: inline-block;
        background: #dbeafe;
        color: #1e40af;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        margin-right: 4px;
      }}
      .tag.software {{
        background: #dcfce7;
        color: #166534;
      }}
      .link-button {{
        display: inline-block;
        background: #3b82f6;
        color: #ffffff;
        padding: 6px 12px;
        border-radius: 4px;
        text-decoration: none;
        font-size: 13px;
        transition: background 0.2s;
      }}
      .link-button:hover {{
        background: #2563eb;
      }}
      .footer {{
        margin-top: 32px;
        padding-top: 16px;
        border-top: 1px solid #e5e7eb;
        color: #6b7280;
        font-size: 13px;
        text-align: center;
      }}
      @media (max-width: 600px) {{
        body {{
          padding: 8px;
        }}
        .container {{
          padding: 16px;
        }}
        .card-row {{
          flex-direction: column;
          gap: 2px;
        }}
        .card-label {{
          min-width: auto;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="container">
      <div class="header">
        <h2>📧 教育資訊標案每日監控</h2>
        <div class="meta">查詢日期：{escape(run_date.isoformat())} | 系統自動通知，請勿直接回覆</div>
      </div>

      <div class="summary">
        <div><strong>📊 今日新增：</strong>{len(records)} 筆</div>
        <div><strong>🏫 單位類型：</strong>{unit_summary}</div>
        <div><strong>🏷️ 主題標籤：</strong>{tag_summary}</div>
        <div><strong>💰 高金額案件：</strong>{escape(high_amount_summary)}</div>
      </div>

      <div class="cards-container">
        {cards}
      </div>

      <div class="footer">
        <p>本郵件由標案監控系統自動寄出，請勿直接回覆。</p>
        <p style="font-size: 11px; color: #9ca3af;">如有問題請聯繫系統管理員。</p>
      </div>
    </div>
  </body>
</html>
""".strip()


def _render_card(index: int, record: BidRecord) -> str:
    """Render a single bid as a card instead of table row."""
    title = escape(record.title)
    org = escape(record.organization)
    
    # Budget amount - bold formatting
    if record.budget_amount:
        budget = f'<span class="amount-bold">{escape(record.budget_amount)}</span>'
    else:
        budget = "無提供"
    
    # Bid bond - infer "免繳" if zero or empty
    bid_bond_raw = (record.bid_bond or "").strip()
    if not bid_bond_raw or bid_bond_raw == "0" or bid_bond_raw.lower() in ["無", "無提供", "none"]:
        bid_bond = '<span style="color:#059669;">免繳</span>'
    else:
        bid_bond = escape(bid_bond_raw)
    
    # Deadline - red formatting
    bid_deadline_raw = (record.bid_deadline or "").strip()
    if bid_deadline_raw and bid_deadline_raw != "無提供":
        bid_deadline = f'<span class="deadline-red">{escape(bid_deadline_raw)}</span>'
    else:
        bid_deadline = "無提供"
    
    bid_opening = escape(record.bid_opening_time) if record.bid_opening_time else "無提供"
    
    # Source
    source_text = record.source
    if record.backup_source:
        source_text = f"{record.source} (backup: {record.backup_source})"
    
    # Tags - highlight "軟體"
    tags_html = ""
    if record.tags:
        tag_items = []
        for tag in record.tags:
            tag_class = "tag software" if "軟體" in tag else "tag"
            tag_items.append(f'<span class="{tag_class}">{escape(tag)}</span>')
        tags_html = " ".join(tag_items)
    else:
        tags_html = "<span style='color:#9ca3af;'>無標籤</span>"
    
    # Link button
    link = escape(record.url or "")
    if link:
        link_html = f'<a href="{link}" target="_blank" rel="noreferrer" class="link-button">📄 查看詳情</a>'
    else:
        link_html = "<span style='color:#9ca3af;'>無連結</span>"
    
    return f"""
<div class="bid-card">
  <div class="card-header">
    <div class="card-title">{title}</div>
    <div class="card-index">#{index}</div>
  </div>
  <div class="card-body">
    <div class="card-row">
      <div class="card-label">🏫 機關</div>
      <div class="card-value">{org}</div>
    </div>
    <div class="card-row">
      <div class="card-label">💰 預算金額</div>
      <div class="card-value">{budget}</div>
    </div>
    <div class="card-row">
      <div class="card-label">⏰ 截止投標</div>
      <div class="card-value">{bid_deadline}</div>
    </div>
    <div class="card-row">
      <div class="card-label">📌 開標時間</div>
      <div class="card-value">{bid_opening}</div>
    </div>
    <div class="card-row">
      <div class="card-label">💳 押標金</div>
      <div class="card-value">{bid_bond}</div>
    </div>
    <div class="card-row">
      <div class="card-label">🏷️ 標籤</div>
      <div class="card-value">{tags_html}</div>
    </div>
    <div class="card-row" style="margin-top:8px;">
      <div class="card-label">🔗 連結</div>
      <div class="card-value">{link_html}</div>
    </div>
    <div class="card-row">
      <div class="card-label">📡 來源</div>
      <div class="card-value">{escape(source_text)}</div>
    </div>
  </div>
</div>
""".strip()


def format_amount(record: BidRecord) -> str:
    if record.amount_value is not None:
        return f"NT$ {int(record.amount_value):,}"
    return record.amount_raw or ""
