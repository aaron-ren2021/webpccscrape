from __future__ import annotations

from unittest.mock import MagicMock

from crawler.gov import _extract_detail_fields, _is_captcha_page
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
    assert record.bid_bond == "免繳"
    assert record.bid_deadline == "115/04/08 17:00"
    assert record.bid_opening_time == "115/04/09 14:00"


def test_extract_detail_fields_with_bond_amount():
    record = _make_record()
    soup = parse_html(DETAIL_HTML_WITH_BOND)
    _extract_detail_fields(soup, record)

    assert record.budget_amount == "NT$ 19,173,000 元"
    assert record.bid_bond == "NT$ 576,000 元"
    assert record.bid_deadline == "115/05/05 10:00"
    assert record.bid_opening_time == "115/05/05 14:00"


def test_extract_detail_fields_budget_not_public():
    html = '<html><body><table><tr><td>預算金額是否公開</td><td>否</td></tr></table></body></html>'
    record = _make_record()
    soup = parse_html(html)
    _extract_detail_fields(soup, record)

    assert record.budget_amount == "未公開"


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
          <td>115/04/24</td>
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
