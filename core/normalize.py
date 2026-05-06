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
MIN_REASONABLE_BID_YEAR = 2000
MAX_REASONABLE_BID_YEAR = 2100


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
    text = text.replace("\u3000", " ").strip()

    if _looks_like_non_amount(text):
        return None

    total = _parse_amount_with_units(text)
    if total is not None:
        return total

    plain = _parse_plain_amount(text)
    if plain is not None:
        return plain

    return None


def _looks_like_non_amount(text: str) -> bool:
    lowered = text.lower()
    if "%" in text or "％" in text:
        return True
    if not re.search(r"\d", text):
        return True
    has_explicit_money_context = bool(
        re.search(r"(預算金額|採購金額|決標金額|底價|新[臺台]幣|[臺台]幣|NT\$?|NTD|\d+\s*元)", text, re.IGNORECASE)
    )
    non_amount_markers = [
        "手續費",
        "電子領標",
        "領標費",
        "下載費",
        "系統使用費",
        "廠商家數",
        "件數",
        "電話",
        "傳真",
        "統一編號",
        "郵遞區號",
        "日期",
        "時間",
        "截止",
        "開標",
        "履約期限",
        "民國",
        "年",
        "月",
        "日",
    ]
    # Some sources return mixed field text in a single cell (for example:
    # "預算金額：9,500,000元 截止投標：115/05/05 17:00"). In that case we should
    # still parse the amount and not discard it just because deadline/date words exist.
    if has_explicit_money_context:
        non_amount_markers = [marker for marker in non_amount_markers if marker not in {"日期", "時間", "截止", "開標", "民國", "年", "月", "日"}]
    if any(marker in text for marker in non_amount_markers):
        return True
    return lowered in {"none", "null", "n/a"}


def _parse_amount_with_units(text: str) -> Optional[float]:
    compact = re.sub(r"\s+", "", text)
    normalized = (
        compact.replace("新臺幣", "")
        .replace("新台幣", "")
        .replace("臺幣", "")
        .replace("台幣", "")
        .replace("NT$", "")
        .replace("NTD", "")
        .replace("元整", "元")
    )
    unit_pattern = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(億|萬|千元)")
    matches = list(unit_pattern.finditer(normalized))
    if not matches:
        return None

    total = 0.0
    for match in matches:
        number = _parse_number_token(match.group(1))
        if number is None:
            return None
        unit = match.group(2)
        if unit == "億":
            total += number * 100_000_000
        elif unit == "萬":
            total += number * 10_000
        elif unit == "千元":
            total += number * 1_000
    return total if total else None


def _parse_plain_amount(text: str) -> Optional[float]:
    money_context = bool(
        re.search(r"(預算金額|採購金額|決標金額|底價|金額|新[臺台]幣|[臺台]幣|NT\$?|NTD|元)", text, re.IGNORECASE)
    )
    tokens = re.findall(r"\d+(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", text)
    if not tokens:
        return None
    if not money_context and len(tokens) > 1:
        return None

    values: list[float] = []
    for token in tokens:
        number = _parse_number_token(token)
        if number is not None:
            values.append(number)
    if not values:
        return None
    if not money_context and values[0] < 10_000:
        return None
    return max(values)


def _parse_number_token(token: str) -> Optional[float]:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def parse_bid_date(value: str) -> Optional[date]:
    if not value:
        return None

    text = unicodedata.normalize("NFKC", value).strip()
    compact_digits = re.sub(r"\D", "", text)
    compact = _parse_compact_bid_date(compact_digits)
    if compact:
        return compact

    roc_match = ROC_DATE_PATTERN.search(text)
    if roc_match:
        roc_year = int(roc_match.group("y"))
        year = roc_year + 1911 if roc_year < 1911 else roc_year
        month = int(roc_match.group("m"))
        day = int(roc_match.group("d"))
        return _safe_bid_date(year, month, day)

    try:
        parsed = dt_parser.parse(text, dayfirst=False, fuzzy=True)
        parsed_date = parsed.date()
        if not _is_reasonable_bid_year(parsed_date.year):
            return None
        return parsed_date
    except (ValueError, OverflowError):
        return None


def _parse_compact_bid_date(value: str) -> Optional[date]:
    if len(value) == 8 and value.startswith(("19", "20")):
        return _safe_bid_date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    if len(value) == 7:
        return _safe_bid_date(int(value[:3]) + 1911, int(value[3:5]), int(value[5:7]))
    if len(value) == 6 and not value.startswith(("19", "20")):
        return _safe_bid_date(int(value[:2]) + 1911, int(value[2:4]), int(value[4:6]))
    return None


def _safe_bid_date(year: int, month: int, day: int) -> Optional[date]:
    if not _is_reasonable_bid_year(year):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _is_reasonable_bid_year(year: int) -> bool:
    return MIN_REASONABLE_BID_YEAR <= year <= MAX_REASONABLE_BID_YEAR


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
