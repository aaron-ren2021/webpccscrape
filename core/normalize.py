from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, time
from typing import Optional

from dateutil import parser as dt_parser

PUNCT_OR_SPACE_PATTERN = re.compile(r"[\s\u3000]+")
DIGIT_PATTERN = re.compile(r"([0-9][0-9,\.]*)")
ROC_DATE_PATTERN = re.compile(r"(?P<y>\d{2,3})\s*[年\/-]\s*(?P<m>\d{1,2})\s*[月\/-]\s*(?P<d>\d{1,2})")
DEADLINE_DATE_PATTERN = re.compile(r"(?P<y>\d{2,4})\s*[年\/-]\s*(?P<m>\d{1,2})\s*[月\/-]\s*(?P<d>\d{1,2})")
DEADLINE_TIME_PATTERN = re.compile(r"(?P<h>\d{1,2})\s*[:：]\s*(?P<mi>\d{1,2})")
MISSING_DEADLINE_VALUES = {"", "無", "無提供", "未提供", "詳見連結", "none", "null", "n/a"}


def normalize_text(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("臺", "台")
    normalized = "".join(ch for ch in normalized if not _is_punct(ch))
    normalized = PUNCT_OR_SPACE_PATTERN.sub("", normalized)
    return normalized.lower().strip()


def normalize_org(value: str) -> str:
    return normalize_text(value)


def parse_amount(value: str) -> Optional[float]:
    if not value:
        return None
    text = unicodedata.normalize("NFKC", value)
    
    # Define multipliers
    multiplier = 1.0
    if "億" in text:
        multiplier = 100000000.0
    elif "萬" in text:
        multiplier = 10000.0
    elif "千元" in text:
        multiplier = 1000.0
    
    # Enhanced regex patterns for various formats
    patterns = [
        r"預算金額[\uff1a:]​*新?臺?幣?​*(\d{1,3}(,\d{3})*)​*元?",  # 預算金額：新臺幣 X 元
        r"底價[\uff1a:]​*(\d{1,3}(,\d{3})*)",  # 底價：X
        r"NT\$?​*(\d{1,3}(,\d{3})*)",  # NT$ X or NT X
        r"([0-9][0-9,\.]*)",  # Fallback: any digit sequence
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.replace(",", ""))
        if match:
            try:
                # Extract first group (the number)
                num_str = match.group(1) if "(" in pattern else match.group(0)
                num_str = num_str.replace(",", "").replace(".", "")
                amount = float(num_str)
                return amount * multiplier
            except (ValueError, IndexError):
                continue
    
    return None


def parse_bid_date(value: str) -> Optional[date]:
    if not value:
        return None

    text = unicodedata.normalize("NFKC", value).strip()

    roc_match = ROC_DATE_PATTERN.search(text)
    if roc_match:
        roc_year = int(roc_match.group("y"))
        year = roc_year + 1911 if roc_year < 1911 else roc_year
        month = int(roc_match.group("m"))
        day = int(roc_match.group("d"))
        try:
            return date(year, month, day)
        except ValueError:
            return None

    try:
        parsed = dt_parser.parse(text, dayfirst=False, fuzzy=True)
        return parsed.date()
    except (ValueError, OverflowError):
        return None


def parse_bid_deadline_text(value: str) -> Optional[tuple[date, time | None]]:
    if not value:
        return None

    text = unicodedata.normalize("NFKC", value).strip()
    if text.lower() in MISSING_DEADLINE_VALUES:
        return None

    date_match = DEADLINE_DATE_PATTERN.search(text)
    if not date_match:
        return None

    year_raw = int(date_match.group("y"))
    year = year_raw + 1911 if year_raw < 1911 else year_raw
    month = int(date_match.group("m"))
    day = int(date_match.group("d"))

    try:
        deadline_date = date(year, month, day)
    except ValueError:
        return None

    deadline_time: time | None = None
    time_match = DEADLINE_TIME_PATTERN.search(text[date_match.end():])
    if time_match:
        try:
            deadline_time = time(int(time_match.group("h")), int(time_match.group("mi")))
        except ValueError:
            deadline_time = None

    return deadline_date, deadline_time


def is_bid_deadline_expired(value: str, now_tw: datetime) -> bool:
    parsed = parse_bid_deadline_text(value)
    if not parsed:
        return False

    deadline_date, deadline_time = parsed
    if deadline_time is None:
        return deadline_date < now_tw.date()

    deadline_at = datetime.combine(deadline_date, deadline_time, tzinfo=now_tw.tzinfo)
    return deadline_at < now_tw


def amount_key(value: Optional[float], raw: str = "") -> str:
    if value is None:
        return normalize_text(raw)
    return str(int(round(value)))


def build_bid_uid(title: str, org: str, bid_date: Optional[date], amount: Optional[float], amount_raw: str = "") -> str:
    date_str = bid_date.isoformat() if bid_date else ""
    payload = "|".join(
        [
            normalize_text(title),
            normalize_org(org),
            date_str,
            amount_key(amount, amount_raw),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_punct(ch: str) -> bool:
    return unicodedata.category(ch).startswith(("P", "S"))
