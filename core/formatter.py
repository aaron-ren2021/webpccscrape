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
    """Render email HTML with grid-based card layout."""
    unit_counts = count_by_unit_type(records)
    tag_counter: Counter[str] = Counter()
    
    for record in records:
        tag_counter.update(record.tags)

    high_amount_rows = [
        record
        for record in records
        if record.amount_value is not None and record.amount_value >= high_amount_threshold
    ]
    
    # Find earliest deadline
    earliest_deadline = None
    for record in records:
        if record.bid_deadline:
            try:
                # Try to parse deadline - could be "115/04/27 17:00" or similar
                deadline_str = record.bid_deadline.strip()
                if deadline_str and deadline_str != "無提供":
                    earliest_deadline = deadline_str
                    break
            except Exception:
                pass

    unit_summary = "、".join(f"{escape(k)}: {v}" for k, v in sorted(unit_counts.items())) or "無"
    tag_summary = "、".join(f"{escape(tag)}({count})" for tag, count in tag_counter.most_common()) or "無"

    high_amount_summary = "；".join(
        f"{escape(item.organization)} / {escape(item.title)} / {format_amount(item)}"
        for item in high_amount_rows[:5]
    )
    if not high_amount_summary:
        high_amount_summary = "無"

    # Meta line with earliest deadline
    meta_text = f"查詢日期：{escape(run_date.isoformat())}"
    if earliest_deadline:
        meta_text += f" ｜最緊急截止 {escape(earliest_deadline)}"
    meta_text += " ｜系統自動通知，請勿直接回覆"

    cards = "\n".join(_render_card(idx + 1, record) for idx, record in enumerate(records))

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #f3f4f6; padding: 20px; font-family: 'Noto Sans TC', Arial, sans-serif; }}
    .container {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 24px; max-width: 860px; margin: 0 auto; }}
    .email-header {{ border-bottom: 1.5px solid #d1d5db; padding-bottom: 14px; margin-bottom: 16px; }}
    .email-header h2 {{ font-size: 18px; font-weight: 600; color: #111827; margin-bottom: 4px; }}
    .meta {{ font-size: 12px; color: #9ca3af; }}
    .summary {{ background: #f9fafb; border-left: 3px solid #3b82f6; border-radius: 0 8px 8px 0; padding: 12px 16px; margin-bottom: 20px; display: grid; gap: 5px; }}
    .summary div {{ font-size: 13px; color: #374151; }}
    .summary strong {{ font-weight: 600; }}
    .bid-card {{ border: 1px solid #e5e7eb; border-radius: 10px; margin-bottom: 10px; overflow: hidden; }}
    .card-head {{ display: flex; align-items: baseline; gap: 10px; padding: 10px 16px; background: #f3f4f6; border-bottom: 1px solid #e5e7eb; }}
    .card-num {{ font-size: 11px; font-weight: 600; background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; flex-shrink: 0; }}
    .card-title-text {{ font-size: 14px; font-weight: 600; color: #111827; line-height: 1.4; }}
    .card-body {{ padding: 12px 16px; background: #fff; }}
    .fields-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px 20px; }}
    .field {{ display: flex; flex-direction: column; gap: 3px; }}
    .field-label {{ font-size: 11px; color: #9ca3af; display: flex; align-items: center; gap: 4px; }}
    .field-label span {{ font-size: 13px; }}
    .field-value {{ font-size: 13px; font-weight: 500; color: #1f2937; }}
    .val-deadline {{ color: #a32d2d; font-weight: 600; }}
    .val-amount {{ color: #27500a; font-weight: 600; }}
    .val-bond-free {{ color: #27500a; }}
    .val-bond-req {{ color: #6b7280; }}
    .val-none {{ color: #d1d5db; font-weight: 400; }}
    .tag-pill {{ display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 500; margin-right: 3px; margin-top: 2px; }}
    .tag-soft {{ background: #dcfce7; color: #166534; }}
    .tag-ai {{ background: #fef3c7; color: #78350f; }}
    .tag-hw {{ background: #dbeafe; color: #1e40af; }}
    .tag-free {{ background: #dcfce7; color: #166534; }}
    .tag-default {{ background: #f3f4f6; color: #6b7280; }}
    .link-btn {{ display: inline-flex; align-items: center; gap: 4px; background: #dbeafe; color: #1e40af; padding: 3px 10px; border-radius: 4px; font-size: 11px; text-decoration: none; border: 1px solid #93c5fd; }}
    .src-badge {{ font-size: 12px; color: #6b7280; }}
    .footer {{ margin-top: 20px; padding-top: 12px; border-top: 1px solid #e5e7eb; font-size: 11px; color: #9ca3af; text-align: center; }}
    @media (max-width: 600px) {{
      body {{ padding: 8px; }}
      .container {{ padding: 14px; }}
      .fields-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
<div class="container">

  <div class="email-header">
    <h2>📧 教育資訊標案每日監控</h2>
    <div class="meta">{meta_text}</div>
  </div>

  <div class="summary">
    <div><strong>📊 今日新增：</strong>{len(records)} 筆</div>
    <div><strong>🏫 單位類型：</strong>{unit_summary}</div>
    <div><strong>🏷️ 主題標籤：</strong>{tag_summary}</div>
    <div><strong>💰 高金額案件：</strong>{escape(high_amount_summary)}</div>
  </div>

  {cards}

  <div class="footer">本郵件由標案監控系統自動寄出，請勿直接回覆。</div>

</div>
</body>
</html>""".strip()


def _render_card(index: int, record: BidRecord) -> str:
    """Render a single bid card with grid layout."""
    title = escape(record.title)
    org = escape(record.organization)
    
    # Opening time
    bid_opening = escape(record.bid_opening_time) if record.bid_opening_time else "詳見連結"
    
    # Deadline - emphasized in red
    bid_deadline_raw = (record.bid_deadline or "").strip()
    if bid_deadline_raw and bid_deadline_raw != "無提供":
        bid_deadline = f'<span class="field-value val-deadline">{escape(bid_deadline_raw)}</span>'
    else:
        bid_deadline = '<span class="field-value val-none">無提供</span>'
    
    # Budget amount - emphasized in green
    if record.budget_amount:
        budget = f'<span class="field-value val-amount">{escape(record.budget_amount)}</span>'
    elif record.amount_value is not None:
        budget = f'<span class="field-value val-amount">{format_amount(record)}</span>'
    elif record.amount_raw:
        budget = f'<span class="field-value val-amount">{escape(record.amount_raw)}</span>'
    else:
        budget = '<span class="field-value val-none">詳見連結</span>'
    
    # Bid bond - show "需繳納" or "免繳納"
    bid_bond_raw = (record.bid_bond or "").strip()
    if not bid_bond_raw or bid_bond_raw == "0" or bid_bond_raw.lower() in ["無", "無提供", "none"]:
        bid_bond = '<span class="field-value val-bond-free">免繳納</span>'
    else:
        bid_bond = '<span class="field-value val-bond-req">需繳納</span>'
    
    # Tags - color coding by type
    tag_items = []
    if record.tags:
        for tag in record.tags:
            if "軟體" in tag or "系統" in tag:
                tag_class = "tag-pill tag-soft"
            elif "AI" in tag.upper() or "人工智慧" in tag:
                tag_class = "tag-pill tag-ai"
            elif "硬體" in tag or "設備" in tag:
                tag_class = "tag-pill tag-hw"
            else:
                tag_class = "tag-pill tag-default"
            tag_items.append(f'<span class="{tag_class}">{escape(tag)}</span>')
    
    # Add bid-bond-free as a tag if applicable
    if not bid_bond_raw or bid_bond_raw == "0" or bid_bond_raw.lower() in ["無", "無提供", "none"]:
        tag_items.append('<span class="tag-pill tag-free">免繳押標金</span>')
    
    tags_html = " ".join(tag_items) if tag_items else '<span class="field-value val-none">無標籤</span>'
    
    # Link button
    link = escape(record.url or "")
    if link:
        link_html = f'<a class="link-btn" href="{link}" target="_blank" rel="noreferrer">📄 查看詳情</a>'
    else:
        link_html = '<span class="field-value val-none">無連結</span>'
    
    # Source
    source_text = record.source
    if record.backup_source:
        source_text = f"{record.source}(備份)"
    
    # Map source to display name
    source_display = source_text
    if source_text.lower() == "gov_pcc":
        source_display = "gov_pcc"
    elif "g0v" in source_text.lower():
        source_display = "g0v API"
    elif "taiwanbuying" in source_text.lower():
        source_display = "taiwanbuying"
    
    source_html = f'<span class="src-badge">{escape(source_display)}</span>'
    
    return f"""  <div class="bid-card">
    <div class="card-head">
      <span class="card-num">#{index}</span>
      <span class="card-title-text">{title}</span>
    </div>
    <div class="card-body">
      <div class="fields-grid">
        <div class="field"><span class="field-label"><span>🏫</span> 機關</span><span class="field-value">{org}</span></div>
        <div class="field"><span class="field-label"><span>🕐</span> 開標時間</span><span class="field-value">{bid_opening}</span></div>
        <div class="field"><span class="field-label"><span>⏰</span> 截止投標</span>{bid_deadline}</div>
        <div class="field"><span class="field-label"><span>💰</span> 預算金額</span>{budget}</div>
        <div class="field"><span class="field-label"><span>💳</span> 押標金</span>{bid_bond}</div>
        <div class="field"><span class="field-label"><span>🏷️</span> 標籤</span><span class="field-value">{tags_html}</span></div>
        <div class="field"><span class="field-label"><span>🔗</span> 連結</span>{link_html}</div>
        <div class="field"><span class="field-label"><span>📌</span> 來源</span>{source_html}</div>
      </div>
    </div>
  </div>"""


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
