from __future__ import annotations

from collections import Counter
from datetime import date
from html import escape
from typing import Optional

from core.filters import count_by_unit_type
from core.models import BidRecord

# Constants for bid bond free values
_BOND_FREE_VALUES: frozenset[str] = frozenset({"0", "無", "none", "", "免繳"})


def _parse_deadline_to_sort_key(s: str) -> tuple[int, int, int, int, int]:
    """Parse deadline text and normalize ROC year to CE for sorting."""
    try:
        parts = s.strip().split()
        if not parts:
            return (9999, 12, 31, 23, 59)

        date_part = parts[0].replace("-", "/")
        time_part = parts[1] if len(parts) > 1 else "00:00"
        y, m, d = date_part.split("/")
        h, mi = time_part.split(":")

        year = int(y)
        if year < 1911:
            year += 1911

        return (year, int(m), int(d), int(h), int(mi))
    except Exception:
        return (9999, 12, 31, 23, 59)


def _format_deadline_ce(s: str) -> str:
    year, month, day, hour, minute = _parse_deadline_to_sort_key(s)
    if (year, month, day, hour, minute) == (9999, 12, 31, 23, 59):
        return s
    if hour == 0 and minute == 0 and ":" not in s:
        return f"{year:04d}-{month:02d}-{day:02d}"
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def find_earliest_deadline(records: list[BidRecord]) -> Optional[str]:
    deadlines = [
        r.bid_deadline.strip()
        for r in records
        if r.bid_deadline and r.bid_deadline.strip() not in ("", "無提供")
    ]
    if not deadlines:
        return None
    earliest_raw = min(deadlines, key=_parse_deadline_to_sort_key)
    return _format_deadline_ce(earliest_raw)


def render_email_subject(prefix: str, run_date: date, count: int, earliest_deadline: Optional[str] = None) -> str:
    """Render email subject with optional earliest deadline."""
    base = f"{prefix} {run_date.isoformat()} 新增 {count} 筆"
    if earliest_deadline:
        return f"{base}｜最緊急截止 {earliest_deadline}"
    return base


def render_email_html(records: list[BidRecord], run_date: date, high_amount_threshold: float) -> str:
    """Render email HTML — Outlook compatible (table layout, inline styles only)."""
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
    earliest_deadline = find_earliest_deadline(records)

    unit_summary = "、".join(f"{escape(k)}: {v}" for k, v in sorted(unit_counts.items())) or "無"
    tag_summary = "、".join(f"{escape(tag)}({count})" for tag, count in tag_counter.most_common()) or "無"

    high_amount_summary = "；".join(
        f"{escape(item.organization)} / {escape(item.title)} / {format_amount(item)}"
        for item in high_amount_rows[:5]
    )
    if not high_amount_summary:
        high_amount_summary = "無"

    # Meta line
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
</head>
<body style="margin:0;padding:20px;background:#f3f4f6;font-family:'Noto Sans TC',Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td align="center">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;max-width:1100px;">
        <tr>
          <td style="padding:24px;">

            <!-- Header -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="padding-bottom:14px;border-bottom:1px solid #d1d5db;">
                  <div style="font-size:18px;font-weight:600;color:#111827;margin-bottom:4px;">
                    &#128231; 教育資訊標案每日監控
                  </div>
                  <div style="font-size:12px;color:#9ca3af;">{meta_text}</div>
                </td>
              </tr>
            </table>

            <!-- Spacer -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td style="height:16px;"></td></tr>
            </table>

            <!-- Summary -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="background:#f9fafb;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;">
              <tr>
                <td style="padding:12px 16px;">
                  <div style="font-size:13px;color:#374151;padding:4px 0;">
                    <strong>&#128202; 今日新增：</strong>{len(records)} 筆
                  </div>
                  <div style="font-size:13px;color:#374151;padding:4px 0;">
                    <strong>&#127979; 單位類型：</strong>{unit_summary}
                  </div>
                  <div style="font-size:13px;color:#374151;padding:4px 0;">
                    <strong>&#127991; 主題標籤：</strong>{tag_summary}
                  </div>
                  <div style="font-size:13px;color:#374151;padding:4px 0;">
                    <strong>&#128176; 高金額案件：</strong>{escape(high_amount_summary)}
                  </div>
                </td>
              </tr>
            </table>

            <!-- Spacer -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td style="height:20px;"></td></tr>
            </table>

            <!-- Cards -->
            {cards}

            <!-- Footer -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="border-top:1px solid #e5e7eb;margin-top:20px;">
              <tr>
                <td style="padding-top:12px;font-size:11px;color:#9ca3af;text-align:center;">
                  本郵件由標案監控系統自動寄出，請勿直接回覆。
                </td>
              </tr>
            </table>

          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

</body>
</html>""".strip()


def _render_card(index: int, record: BidRecord) -> str:
    """Render a single bid card — Outlook compatible table layout with inline styles."""
    title = escape(record.title)
    org = escape(record.organization)

    # Opening time
    bid_opening = escape(record.bid_opening_time) if record.bid_opening_time else "詳見連結"

    # Deadline
    bid_deadline_raw = (record.bid_deadline or "").strip()
    if bid_deadline_raw and bid_deadline_raw != "無提供":
        bid_deadline = (
            f'<div style="font-size:13px;font-weight:600;color:#a32d2d;">'
            f'{escape(bid_deadline_raw)}</div>'
        )
    else:
        bid_deadline = '<div style="font-size:13px;color:#d1d5db;">無提供</div>'

    # Budget
    if record.budget_amount:
        budget = (
            f'<div style="font-size:13px;font-weight:600;color:#27500a;">'
            f'{escape(record.budget_amount)}</div>'
        )
    elif record.amount_value is not None:
        budget = (
            f'<div style="font-size:13px;font-weight:600;color:#27500a;">'
            f'{format_amount(record)}</div>'
        )
    elif record.amount_raw:
        budget = (
            f'<div style="font-size:13px;font-weight:600;color:#27500a;">'
            f'{escape(record.amount_raw)}</div>'
        )
    else:
        budget = '<div style="font-size:13px;color:#d1d5db;">詳見連結</div>'

    # Bid bond
    bid_bond_raw = (record.bid_bond or "").strip()
    if bid_bond_raw.lower() in _BOND_FREE_VALUES:
        bid_bond = '<div style="font-size:13px;color:#27500a;">免繳納</div>'
        is_free = True
    elif bid_bond_raw and bid_bond_raw != "需繳納":
        bid_bond = (
            f'<div style="font-size:13px;font-weight:600;color:#6b7280;">'
            f'{escape(bid_bond_raw)}</div>'
        )
        is_free = False
    else:
        bid_bond = '<div style="font-size:13px;color:#6b7280;">需繳納</div>'
        is_free = False

    # Tags
    tag_items = []
    if record.tags:
        for tag in record.tags:
            if "軟體" in tag or "系統" in tag:
                bg, fg = "#dcfce7", "#166534"
            elif "AI" in tag.upper() or "人工智慧" in tag:
                bg, fg = "#fef3c7", "#78350f"
            elif "硬體" in tag or "設備" in tag:
                bg, fg = "#dbeafe", "#1e40af"
            else:
                bg, fg = "#f3f4f6", "#6b7280"
            tag_items.append(
                f'<span style="display:inline-block;padding:2px 7px;border-radius:4px;'
                f'font-size:11px;font-weight:500;margin-right:3px;'
                f'background:{bg};color:{fg};">{escape(tag)}</span>'
            )
    if is_free:
        tag_items.append(
            '<span style="display:inline-block;padding:2px 7px;border-radius:4px;'
            'font-size:11px;font-weight:500;margin-right:3px;'
            'background:#dcfce7;color:#166534;">免繳押標金</span>'
        )
    tags_html = (
        "".join(tag_items)
        if tag_items
        else '<span style="font-size:13px;color:#d1d5db;">無標籤</span>'
    )

    metadata = record.metadata or {}
    source_text = record.source
    if record.backup_source:
        source_text = f"{record.source}(備份)"

    is_g0v = "g0v" in source_text.lower()
    g0v_link_state = str(
        metadata.get("g0v_link_resolution_state", metadata.get("g0v_human_url_state", ""))
    ).strip().lower()

    # Link
    raw_link = (record.url or "").strip()
    is_http_link = raw_link.startswith("http://") or raw_link.startswith("https://")
    if is_http_link:
        safe_link = escape(raw_link)
        link_label = "&#128196; 查看詳情"
        if is_g0v and g0v_link_state == "resolved_official":
            link_label = "&#128196; 查看詳情（官方頁）"
        elif is_g0v and g0v_link_state == "fallback_api":
            link_label = "&#128279; 來源 API（備援）"
        link_html = (
            f'<a href="{safe_link}" target="_blank" rel="noreferrer"'
            f' style="display:inline-block;padding:3px 10px;border-radius:4px;'
            f'font-size:11px;text-decoration:none;'
            f'background:#dbeafe;color:#1e40af;border:1px solid #93c5fd;">'
            f'{link_label}</a>'
        )
    else:
        backup_links: list[str] = []
        if is_g0v:
            tender_api_url = str(metadata.get("g0v_tender_api_url", "")).strip()
            unit_api_url = str(metadata.get("g0v_unit_api_url", "")).strip()
            if tender_api_url.startswith("http"):
                backup_links.append(
                    '<a href="{}" target="_blank" rel="noreferrer" style="display:inline-block;padding:2px 8px;'
                    'border-radius:4px;font-size:11px;text-decoration:none;background:#eff6ff;color:#1d4ed8;'
                    'border:1px solid #bfdbfe;margin-right:4px;">來源 API</a>'.format(escape(tender_api_url))
                )
            if unit_api_url.startswith("http"):
                backup_links.append(
                    '<a href="{}" target="_blank" rel="noreferrer" style="display:inline-block;padding:2px 8px;'
                    'border-radius:4px;font-size:11px;text-decoration:none;background:#f5f3ff;color:#5b21b6;'
                    'border:1px solid #ddd6fe;">機關 API</a>'.format(escape(unit_api_url))
                )
        if backup_links:
            link_html = (
                '<div style="font-size:11px;color:#6b7280;margin-bottom:4px;">主連結不可用，請改用：</div>'
                + "".join(backup_links)
            )
        else:
            link_html = '<span style="font-size:13px;color:#d1d5db;">無連結</span>'

    # Source
    if source_text.lower() == "gov_pcc":
        source_display = "gov_pcc"
    elif "g0v" in source_text.lower():
        source_display = "g0v API"
    elif "taiwanbuying" in source_text.lower():
        source_display = "taiwanbuying"
    else:
        source_display = source_text
    source_note = ""
    if is_g0v and g0v_link_state == "unresolved":
        source_note = '<div style="font-size:11px;color:#b45309;margin-top:4px;">資料連結暫不可用</div>'

    # Shared cell styles
    td_style = 'style="width:25%;padding:6px 20px 14px 0;vertical-align:top;"'
    td_last = 'style="width:25%;padding:6px 0 14px 0;vertical-align:top;"'
    label_style = 'style="font-size:11px;color:#9ca3af;margin-bottom:3px;"'
    value_style = 'style="font-size:13px;font-weight:500;color:#1f2937;"'

    return f"""
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="border:1px solid #e5e7eb;border-radius:10px;margin-bottom:10px;">
    <tr>
      <td colspan="4"
          style="padding:10px 16px;background:#f3f4f6;
                 border-bottom:1px solid #e5e7eb;
                 border-radius:10px 10px 0 0;">
        <span style="display:inline-block;font-size:11px;font-weight:600;
                     background:#dbeafe;color:#1e40af;
                     padding:2px 8px;border-radius:4px;margin-right:12px;">
          #{index}
        </span>
        <span style="font-size:14px;font-weight:600;color:#111827;">{title}</span>
      </td>
    </tr>
    <tr style="background:#ffffff;">
      <td {td_style}>
        <div {label_style}>&#127979; 機關</div>
        <div {value_style}>{org}</div>
      </td>
      <td {td_style}>
        <div {label_style}>&#128336; 開標時間</div>
        <div {value_style}>{bid_opening}</div>
      </td>
      <td {td_style}>
        <div {label_style}>&#9200; 截止投標</div>
        {bid_deadline}
      </td>
      <td {td_last}>
        <div {label_style}>&#128176; 預算金額</div>
        {budget}
      </td>
    </tr>
    <tr style="background:#ffffff;">
      <td {td_style}>
        <div {label_style}>&#128179; 押標金</div>
        {bid_bond}
      </td>
      <td {td_style}>
        <div {label_style}>&#127991; 標籤</div>
        <div style="font-size:13px;">{tags_html}</div>
      </td>
      <td {td_style}>
        <div {label_style}>&#128279; 連結</div>
        {link_html}
      </td>
      <td {td_last}>
        <div {label_style}>&#128204; 來源</div>
        <div style="font-size:12px;color:#6b7280;">{escape(source_display)}</div>
        {source_note}
      </td>
    </tr>
  </table>"""


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
