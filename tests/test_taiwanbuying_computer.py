from datetime import date

from core.config import Settings
from crawler.taiwanbuying_computer import _parse_records


def test_parse_records_keeps_only_today_updated_rows() -> None:
    html = """
    <table><tbody>
      <tr>
        <td>(2026/5/4 更新)</td>
        <td><a href="/ShowTender.ASP?TBN=TB115001">防火牆採購案</a></td>
        <td>國立臺灣大學</td>
        <td>資訊設備摘要</td>
        <td>1,200,000元</td>
      </tr>
      <tr>
        <td>(2026/5/3 更新)</td>
        <td><a href="/ShowTender.ASP?TBN=TB115002">宿舍網路交換器採購案</a></td>
        <td>某某大學</td>
        <td>摘要</td>
        <td>900,000元</td>
      </tr>
    </tbody></table>
    """

    records = _parse_records(html, Settings(enable_playwright=False), today=date(2026, 5, 4))

    assert len(records) == 1
    record = records[0]
    assert record.title == "防火牆採購案"
    assert record.organization == "國立臺灣大學"
    assert record.bid_date == date(2026, 5, 4)
    assert record.announcement_date == date(2026, 5, 4)
    assert record.source == "taiwanbuying_today_computer"
    assert record.category == "採購-電腦類"
    assert record.metadata["update_date"] == "2026-05-04"
    assert record.metadata["taiwanbuying_id"] == "TB115001"


def test_parse_records_accepts_date_without_update_suffix() -> None:
    html = """
    <table><tbody>
      <tr>
        <td>(2026/5/4)</td>
        <td><a href="/ShowTender.ASP?TBN=TB115003">英文資訊網維護案</a></td>
        <td>臺北市教育局</td>
        <td>摘要</td>
        <td></td>
      </tr>
    </tbody></table>
    """

    records = _parse_records(html, Settings(enable_playwright=False), today=date(2026, 5, 4))

    assert len(records) == 1
    assert records[0].metadata["raw_update_text"] == "(2026/5/4)"
