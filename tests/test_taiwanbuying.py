from core.config import Settings
from crawler.taiwanbuying import _parse_records


def test_taiwanbuying_computer_category_edu_records_are_candidate_only() -> None:
    html = """
    <table>
      <tbody>
        <tr>
          <td>115/04/29</td>
          <td><a href="/bid/A001">資訊設備採購案</a></td>
          <td>某某大學</td>
          <td>摘要</td>
          <td>100萬</td>
          <td>電腦類</td>
        </tr>
      </tbody>
    </table>
    """

    records = _parse_records(html, Settings())

    assert len(records) == 1
    assert records[0].source == "taiwanbuying"
    assert records[0].category == "電腦類"
    assert records[0].metadata["candidate_only"] is True
    assert records[0].metadata["category_hint"] == "computer_edu"
    assert records[0].metadata["category_hint_source"] == "taiwanbuying"


def test_taiwanbuying_non_edu_computer_category_is_not_hint_candidate() -> None:
    html = """
    <table>
      <tbody>
        <tr>
          <td>115/04/29</td>
          <td><a href="/bid/A001">資訊設備採購案</a></td>
          <td>某某公司</td>
          <td>摘要</td>
          <td>100萬</td>
          <td>電腦類</td>
        </tr>
      </tbody>
    </table>
    """

    records = _parse_records(html, Settings())

    assert len(records) == 1
    assert "candidate_only" not in records[0].metadata
    assert "category_hint" not in records[0].metadata
