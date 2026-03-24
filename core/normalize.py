from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from typing import Optional

from dateutil import parser as dt_parser

PUNCT_OR_SPACE_PATTERN = re.compile(r"[\s\u3000]+")
DIGIT_PATTERN = re.compile(r"([0-9][0-9,\.]*)")
ROC_DATE_PATTERN = re.compile(r"(?P<y>\d{2,3})\s*[年\/-]\s*(?P<m>\d{1,2})\s*[月\/-]\s*(?P<d>\d{1,2})")


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
    multiplier = 1.0
    if "億" in text:
        multiplier = 100000000.0
    elif "萬" in text:
        multiplier = 10000.0

    match = DIGIT_PATTERN.search(text.replace(",", ""))
    if not match:
        return None
    try:
        amount = float(match.group(1))
    except ValueError:
        return None
    return amount * multiplier


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
