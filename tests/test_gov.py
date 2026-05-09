from __future__ import annotations

from unittest.mock import MagicMock

from crawler.gov import _extract_detail_fields, _is_captcha_page, _parse_bid_bond_value
from crawler.g0v import _extract_detail_fields as _extract_g0v_detail_fields
from crawler.gov import enrich_detail, fetch_bids
from crawler.common import parse_html
from core.config import Settings
from core.models import BidRecord


def _make_record(**kwargs: object) -> BidRecord:
    defaults = dict(
        title="test",
        organization="org",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="gov_pcc",
        url="https://example.com",
    )
    defaults.update(kwargs)
    return BidRecord(**defaults)  # type: ignore[arg-type]


DETAIL_HTML = """
<html><body>
<table>
  <tr><td>預算金額</td><td><div>222,380元</div></td></tr>
  <tr><td>預算金額是否公開</td><td>是</td></tr>
  <tr><td>截止投標</td><td>115/04/08 17:00</td></tr>
  <tr><td>開標時間</td><td>115/04/09 14:00</td></tr>
  <tr><td>是否須繳納押標金</td><td>否</td></tr>
</table>
</body></html>
"""

DETAIL_HTML_WITH_BOND = """
<html><body>
<table>
  <tr><td>預算金額</td><td>19,173,000元</td></tr>
  <tr><td>截止投標</td><td>115/05/05 10:00</td></tr>
  <tr><td>開標時間</td><td>115/05/05 14:00</td></tr>
  <tr><td>是否須繳納押標金</td><td>是 押標金額度：576,000</td></tr>
</table>
</body></html>
"""

CAPTCHA_HTML = """
<html><body>
<div>驗證碼檢核</div>
<div>為預防惡意程式針對本系統進行大量查詢致影響系統服務品質</div>
</body></html>
"""


def test_extract_detail_fields_basic():
    record = _make_record()
    soup = parse_html(DETAIL_HTML)
    _extract_detail_fields(soup, record)

    assert record.budget_amount == "NT$ 222,380 元"
    assert record.amount_raw == "NT$ 222,380 元"
    assert record.amount_value == 222_380.0
    assert record.bid_bond == "免繳"
    assert record.bid_deadline == "115/04/08 17:00"
    assert record.bid_opening_time == "115/04/09 14:00"


def test_extract_detail_fields_with_bond_amount():
    record = _make_record()
    soup = parse_html(DETAIL_HTML_WITH_BOND)
    _extract_detail_fields(soup, record)

    assert record.budget_amount == "NT$ 19,173,000 元"
    assert record.amount_raw == "NT$ 19,173,000 元"
    assert record.amount_value == 19_173_000.0
    assert record.bid_bond == "NT$ 576,000 元"
    assert record.bid_deadline == "115/05/05 10:00"
    assert record.bid_opening_time == "115/05/05 14:00"


def test_extract_detail_fields_budget_decimal_keeps_precision():
    html = """
    <html><body><table>
      <tr><td>預算金額</td><td>1,234,567.89元</td></tr>
    </table></body></html>
    """
    record = _make_record()
    soup = parse_html(html)
    _extract_detail_fields(soup, record)

    assert record.budget_amount == "NT$ 1,234,567.89 元"
    assert record.amount_raw == "NT$ 1,234,567.89 元"
    assert record.amount_value == 1_234_567.89


def test_extract_detail_fields_budget_not_public():
    html = '<html><body><table><tr><td>預算金額是否公開</td><td>否</td></tr></table></body></html>'
    record = _make_record()
    soup = parse_html(html)
    _extract_detail_fields(soup, record)

    assert record.budget_amount == "未公開"
    assert record.amount_raw == ""
    assert record.amount_value is None


def test_extract_detail_fields_budget_not_public_does_not_overwrite_amount():
    html = """
    <html><body><table>
      <tr><td>預算金額</td><td>9,500,000元</td></tr>
      <tr><td>預算金額是否公開</td><td>否</td></tr>
    </table></body></html>
    """
    record = _make_record()
    soup = parse_html(html)
    _extract_detail_fields(soup, record)

    assert record.budget_amount == "NT$ 9,500,000 元"
    assert record.amount_raw == "NT$ 9,500,000 元"
    assert record.amount_value == 9_500_000.0


def test_extract_detail_fields_budget_public_yes_preserves_existing_list_amount():
    html = '<html><body><table><tr><td>預算金額是否公開</td><td>是</td></tr></table></body></html>'
    record = _make_record(amount_raw="NT$ 1,200,000 元", amount_value=1_200_000.0)
    soup = parse_html(html)
    _extract_detail_fields(soup, record)

    assert record.budget_amount == ""
    assert record.amount_raw == "NT$ 1,200,000 元"
    assert record.amount_value == 1_200_000.0


def test_is_captcha_page_detects_captcha():
    assert _is_captcha_page(CAPTCHA_HTML) is True


def test_is_captcha_page_normal():
    assert _is_captcha_page(DETAIL_HTML) is False


def test_fetch_bids_marks_degraded_mode_after_rate_limited_circuit_breaker(monkeypatch):
    logger = MagicMock()

    def _raise_rate_limited(*args, **kwargs):
        raise RuntimeError(
            "Stealth fetch failed after 2 attempts for https://web.pcc.gov.tw. "
            "Summary: {'rate_limited': 2}"
        )

    list_html = """
    <html><body>
      <table><tbody>
        <tr>
          <td>115/05/24</td>
          <td><a href="/tps/QueryTender/query/searchTenderDetail?pkPmsMain=AAA">測試標案</a></td>
          <td>測試機關</td>
        </tr>
      </tbody></table>
    </body></html>
    """

    monkeypatch.setattr("crawler.gov.optional_playwright_fetch_html", _raise_rate_limited)
    monkeypatch.setattr("crawler.gov.build_session", lambda settings: object())
    monkeypatch.setattr("crawler.gov.request_html", lambda **kwargs: list_html)

    settings = Settings(
        enable_playwright=True,
        stealth_enabled=True,
        gov_block_circuit_breaker_threshold=2,
        gov_url="https://web.pcc.gov.tw/pis/",
    )

    records = fetch_bids(settings, logger)

    assert len(records) == 1
    assert records[0].metadata.get("detail_fetch_mode") == "degraded_blocked"


def test_enrich_detail_skips_when_degraded_blocked(monkeypatch):
    logger = MagicMock()
    called = {"stealth": 0}

    def _should_not_run(*args, **kwargs):
        called["stealth"] += 1

    monkeypatch.setattr("crawler.gov.enrich_detail_stealth", _should_not_run)

    settings = Settings(enable_playwright=True, stealth_enabled=True)
    records = [
        _make_record(
            metadata={"detail_fetch_mode": "degraded_blocked"},
            url="https://web.pcc.gov.tw/tps/QueryTender/query/searchTenderDetail?pkPmsMain=AAA",
        )
    ]

    enrich_detail(records, settings, logger)

    assert called["stealth"] == 0


def test_extract_detail_fields_bond_variations():
    """Test various formats of bid bond extraction."""
    with open("tests/data/test_gov_detail_bond.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = parse_html(html_content)

    # Case 1: Fixed Amount
    case1_soup = soup.find("table", id="case1")
    record1 = _make_record()
    _extract_detail_fields(case1_soup, record1)
    assert record1.bid_bond == "NT$ 50,000 元"

    # Case 2: Percentage
    case2_soup = soup.find("table", id="case2")
    record2 = _make_record()
    _extract_detail_fields(case2_soup, record2)
    assert record2.bid_bond == "5%"

    # Case 3: No bond
    case3_soup = soup.find("table", id="case3")
    record3 = _make_record()
    _extract_detail_fields(case3_soup, record3)
    assert record3.bid_bond == "免繳"

    # Case 4: See price list (should be "需繳納")
    case4_soup = soup.find("table", id="case4")
    record4 = _make_record()
    _extract_detail_fields(case4_soup, record4)
    assert record4.bid_bond == "需繳納"

    # Case 5: Online payment fee should not be mistaken for bid bond amount
    case5_soup = soup.find("table", id="case5")
    record5 = _make_record()
    _extract_detail_fields(case5_soup, record5)
    assert record5.bid_bond == "3%"


def test_parse_bid_bond_value_with_wan_unit():
    assert _parse_bid_bond_value("押標金額度：新臺幣3萬元整") == "NT$ 30,000 元"


def test_extract_detail_fields_preserves_list_amount_when_budget_unparseable():
    html = """
    <html><body><table>
      <tr><th>預算金額</th><td>詳見招標文件</td></tr>
      <tr><th>截止投標</th><td>115/05/11 17:00</td></tr>
    </table></body></html>
    """
    logger = MagicMock()
    record = _make_record(amount_raw="NT$ 1,200,000 元", amount_value=1_200_000.0)

    _extract_detail_fields(parse_html(html), record, logger)

    assert record.amount_raw == "NT$ 1,200,000 元"
    assert record.amount_value == 1_200_000.0
    assert record.budget_amount == ""
    assert record.bid_deadline == "115/05/11 17:00"
    logger.warning.assert_any_call(
        "gov_detail_field_missing",
        extra={
            "field": "預算金額",
            "reason": "parse_amount_failed",
            "title": "test",
            "url": "https://example.com",
            "snippet": "詳見招標文件",
        },
    )
    budget_miss_reasons = [
        call.kwargs["extra"]["reason"]
        for call in logger.warning.call_args_list
        if call.args
        and call.args[0] == "gov_detail_field_missing"
        and call.kwargs.get("extra", {}).get("field") == "預算金額"
    ]
    assert budget_miss_reasons == ["parse_amount_failed"]


def test_extract_detail_fields_production_wrong_page_preserves_list_values():
    with open("tests/data/production_gov_search_wrong_page_20260424.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    logger = MagicMock()
    record = _make_record(
        organization="國立臺灣藝術大學",
        bid_deadline="115/05/14",
        amount_raw="NT$ 3,600,000 元",
        amount_value=3_600_000.0,
    )

    _extract_detail_fields(parse_html(html_content), record, logger)

    assert record.organization == "國立臺灣藝術大學"
    assert record.bid_deadline == "115/05/14"
    assert record.amount_raw == "NT$ 3,600,000 元"
    assert record.amount_value == 3_600_000.0
    assert record.budget_amount == ""
    logged_fields = [
        call.kwargs["extra"]["field"]
        for call in logger.warning.call_args_list
        if call.args and call.args[0] == "gov_detail_field_missing"
    ]
    assert "預算金額" in logged_fields
    assert "押標金" in logged_fields
    assert "開標時間" in logged_fields


def test_g0v_detail_preserves_amount_value_when_budget_parse_fails():
    logger = MagicMock()
    record = _make_record(
        source="g0v",
        amount_raw="NT$ 2,500,000 元",
        amount_value=2_500_000.0,
    )

    _extract_g0v_detail_fields({"採購資料:預算金額": "詳見連結"}, record, logger)

    assert record.budget_amount == "詳見連結"
    assert record.amount_raw == "NT$ 2,500,000 元"
    assert record.amount_value == 2_500_000.0
    logger.warning.assert_any_call(
        "g0v_detail_budget_parse_failed",
        extra={
            "title": "test",
            "url": "https://example.com",
            "budget": "詳見連結",
            "existing_amount_value": 2_500_000.0,
        },
    )
