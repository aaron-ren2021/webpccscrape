from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.normalize import (
    build_bid_uid,
    is_bid_deadline_expired,
    normalize_text,
    parse_amount,
    parse_bid_date,
    parse_bid_deadline_text,
)


def test_normalize_text_handles_fullwidth_space_and_punct() -> None:
    assert normalize_text(" 國立臺灣大學－資訊設備 採購 ") == "國立台灣大學資訊設備採購"


def test_parse_amount_with_wan_unit() -> None:
    assert parse_amount("1,250萬") == 12_500_000.0


def test_parse_bid_date_roc_format() -> None:
    assert parse_bid_date("114/03/24") == date(2025, 3, 24)


def test_parse_bid_deadline_text_supports_roc_and_ce_with_optional_time() -> None:
    roc_date, roc_time = parse_bid_deadline_text("115/04/29 17:00") or (None, None)
    ce_date, ce_time = parse_bid_deadline_text("2026-04-30") or (None, None)

    assert roc_date == date(2026, 4, 29)
    assert roc_time is not None
    assert roc_time.hour == 17
    assert roc_time.minute == 0
    assert ce_date == date(2026, 4, 30)
    assert ce_time is None


def test_is_bid_deadline_expired_compares_time_when_present() -> None:
    now_tw = datetime(2026, 4, 29, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))

    assert is_bid_deadline_expired("115/04/29 11:59", now_tw) is True
    assert is_bid_deadline_expired("115/04/29 12:01", now_tw) is False


def test_is_bid_deadline_expired_keeps_today_date_without_time() -> None:
    now_tw = datetime(2026, 4, 29, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))

    assert is_bid_deadline_expired("115/04/29", now_tw) is False
    assert is_bid_deadline_expired("115/04/28", now_tw) is True


def test_is_bid_deadline_expired_keeps_missing_or_unparseable_values() -> None:
    now_tw = datetime(2026, 4, 29, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))

    assert is_bid_deadline_expired("", now_tw) is False
    assert is_bid_deadline_expired("無提供", now_tw) is False
    assert is_bid_deadline_expired("詳見連結", now_tw) is False


def test_build_bid_uid_stable() -> None:
    uid1 = build_bid_uid("資訊設備採購", "某某大學", date(2026, 3, 24), 1000000, "100萬")
    uid2 = build_bid_uid("資訊設備採購", "某某大學", date(2026, 3, 24), 1000000, "100萬元")
    assert uid1 == uid2
