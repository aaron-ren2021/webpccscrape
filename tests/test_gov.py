from __future__ import annotations

from crawler.gov import _extract_detail_fields, _is_captcha_page
from crawler.common import parse_html
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
