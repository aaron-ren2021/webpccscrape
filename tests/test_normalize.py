from datetime import date

from core.normalize import build_bid_uid, normalize_text, parse_amount, parse_bid_date


def test_normalize_text_handles_fullwidth_space_and_punct() -> None:
    assert normalize_text(" 國立臺灣大學－資訊設備 採購 ") == "國立台灣大學資訊設備採購"


def test_parse_amount_with_wan_unit() -> None:
    assert parse_amount("1,250萬") == 12_500_000.0


def test_parse_bid_date_roc_format() -> None:
    assert parse_bid_date("114/03/24") == date(2025, 3, 24)


def test_build_bid_uid_stable() -> None:
    uid1 = build_bid_uid("資訊設備採購", "某某大學", date(2026, 3, 24), 1000000, "100萬")
    uid2 = build_bid_uid("資訊設備採購", "某某大學", date(2026, 3, 24), 1000000, "100萬元")
    assert uid1 == uid2
