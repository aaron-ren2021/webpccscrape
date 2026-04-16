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
    """Render email HTML with horizontal card layout."""
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
        max-width: 1200px;
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
        background: #f5f5f5;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        padding: 10px 14px;
        margin-bottom: 10px;
        transition: all 0.2s;
      }}
      .bid-card:hover {{
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        background: #ffffff;
      }}
      .card-title-row {{
        margin-bottom: 8px;
        padding-bottom: 8px;
        border-bottom: 1px solid #e5e7eb;
      }}
      .card-index {{
        background: #6b7280;
        color: #ffffff;
        padding: 2px 8px;
        border-radius: 3px;
        font-size: 11px;
        font-weight: bold;
        margin-right: 8px;
      }}
      .card-title {{
        font-size: 15px;
        font-weight: 600;
        color: #111827;
      }}
      .card-info-row {{
        display: flex;
        align-items: center;
        gap: 20px;
        flex-wrap: wrap;
        font-size: 13px;
      }}
      .card-field {{
        display: flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
      }}
      .field-icon {{
        font-size: 14px;
      }}
      .field-label {{
        color: #6b7280;
        font-weight: 500;
        font-size: 12px;
      }}
      .field-value {{
        color: #1f2937;
        font-weight: 500;
      }}
      .amount-bold {{
        font-weight: bold;
        color: #059669;
      }}
      .deadline-red {{
        font-weight: bold;
        color: #dc2626;
      }}
      .bid-bond-free {{
        color: #059669;
        font-weight: 600;
      }}
      .tag {{
        display: inline-block;
        background: #dbeafe;
        color: #1e40af;
        padding: 2px 8px;
        border-radius: 3px;
        font-size: 11px;
        margin-right: 4px;
        font-weight: 500;
      }}
      .tag.software {{
        background: #dcfce7;
        color: #166534;
      }}
      .tag.ai {{
        background: #fef3c7;
        color: #92400e;
      }}
      .tag.hardware {{
        background: #e0e7ff;
        color: #3730a3;
      }}
      .tag.bid-bond-free-tag {{
        background: #d1fae5;
        color: #065f46;
      }}
      .link-button {{
        display: inline-block;
        background: #3b82f6;
        color: #ffffff;
        padding: 3px 12px;
        border-radius: 3px;
        text-decoration: none;
        font-size: 12px;
        white-space: nowrap;
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
      @media (max-width: 768px) {{
        body {{
          padding: 8px;
        }}
        .container {{
          padding: 12px;
        }}
        .card-info-row {{
          flex-direction: column;
          align-items: flex-start;
          gap: 8px;
        }}
        .card-field {{
          width: 100%;
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
    """Render a single bid card with compact horizontal layout."""
    title = escape(record.title)
    org = escape(record.organization)
    
    # Opening time
    bid_opening = escape(record.bid_opening_time) if record.bid_opening_time else "詳見連結"
    
    # Deadline - emphasized in red
    bid_deadline_raw = (record.bid_deadline or "").strip()
    if bid_deadline_raw and bid_deadline_raw != "無提供":
        bid_deadline = f'<span class="deadline-red">{escape(bid_deadline_raw)}</span>'
    else:
        bid_deadline = '<span style="color:#9ca3af;">無提供</span>'
    
    # Budget amount - emphasized in green
    if record.budget_amount:
        budget = f'<span class="amount-bold">{escape(record.budget_amount)}</span>'
    elif record.amount_value is not None:
        budget = f'<span class="amount-bold">{format_amount(record)}</span>'
    elif record.amount_raw:
        budget = f'<span class="amount-bold">{escape(record.amount_raw)}</span>'
    else:
        budget = '<span style="color:#9ca3af;">詳見連結</span>'
    
    # Bid bond - show "需繳納" or "免繳"
    bid_bond_raw = (record.bid_bond or "").strip()
    if not bid_bond_raw or bid_bond_raw == "0" or bid_bond_raw.lower() in ["無", "無提供", "none"]:
        bid_bond = '<span class="bid-bond-free">免繳納</span>'
    else:
        bid_bond = f'需繳納'
    
    # Tags - color coding by type
    tag_items = []
    if record.tags:
        for tag in record.tags:
            if "軟體" in tag or "系統開發" in tag:
                tag_class = "tag software"
            elif "AI" in tag.upper() or "人工智慧" in tag:
                tag_class = "tag ai"
            elif "硬體" in tag or "設備" in tag:
                tag_class = "tag hardware"
            else:
                tag_class = "tag"
            tag_items.append(f'<span class="{tag_class}">{escape(tag)}</span>')
    
    # Add bid-bond-free as a tag if applicable
    if not bid_bond_raw or bid_bond_raw == "0" or bid_bond_raw.lower() in ["無", "無提供", "none"]:
        tag_items.append('<span class="tag bid-bond-free-tag">免繳押標金</span>')
    
    tags_html = " ".join(tag_items) if tag_items else '<span style="color:#9ca3af;">無標籤</span>'
    
    # Link button
    link = escape(record.url or "")
    if link:
        link_html = f'<a href="{link}" target="_blank" rel="noreferrer" class="link-button">📄 查看詳情</a>'
    else:
        link_html = '<span style="color:#9ca3af;">無連結</span>'
    
    # Source
    source_text = record.source
    if record.backup_source:
        source_text = f"{record.source}(備份)"
    source_html = escape(source_text)
    
    return f"""
<div class="bid-card">
  <div class="card-title-row">
    <span class="card-index">#{index}</span>
    <span class="card-title">{title}</span>
  </div>
  
  <div class="card-info-row">
    <div class="card-field">
      <span class="field-icon">🏫</span>
      <span class="field-label">機關</span>
      <span class="field-value">{org}</span>
    </div>
    
    <div class="card-field">
      <span class="field-icon">⭐</span>
      <span class="field-label">開標時間</span>
      <span class="field-value">{bid_opening}</span>
    </div>
    
    <div class="card-field">
      <span class="field-icon">⏰</span>
      <span class="field-label">截止投標</span>
      {bid_deadline}
    </div>
    
    <div class="card-field">
      <span class="field-icon">💰</span>
      <span class="field-label">預算金額</span>
      {budget}
    </div>
    
    <div class="card-field">
      <span class="field-icon">💳</span>
      <span class="field-label">押標金</span>
      <span class="field-value">{bid_bond}</span>
    </div>
    
    <div class="card-field">
      <span class="field-icon">🏷️</span>
      <span class="field-label">標籤</span>
      <span class="field-value">{tags_html}</span>
    </div>
    
    <div class="card-field">
      <span class="field-icon">🔗</span>
      <span class="field-label">連結</span>
      <span class="field-value">{link_html}</span>
    </div>
    
    <div class="card-field">
      <span class="field-icon">📌</span>
      <span class="field-label">來源</span>
      <span class="field-value">{source_html}</span>
    </div>
  </div>
</div>
""".strip()


def format_amount(record: BidRecord) -> str:
    if record.amount_value is not None:
        return f"NT$ {int(record.amount_value):,}"
    return record.amount_raw or ""


def _format_enrichment_source(record: BidRecord) -> str:
    source_raw = str(record.metadata.get("enrichment_source", "")).strip()
    if not source_raw:
        return "列表頁資料"

    display_map = {
        "g0v_api": "g0v API",
        "gov_detail": "gov 詳細頁",
        "list_only": "列表頁資料",
    }
    display_parts = [display_map.get(part, part) for part in source_raw.split("+") if part]
    if not display_parts:
        return "列表頁資料"
    return escape(" + ".join(display_parts))
