"""Unit tests for g0v API crawler."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from crawler.g0v import _extract_detail_fields, _parse_records, enrich_record
from core.models import BidRecord


def test_parse_records_valid_data() -> None:
    """Test parsing valid g0v JSON data."""
    mock_logger = MagicMock()
    data = [
        {
            "unit_name": "國立臺灣大學",
            "date": 20250407,
            "job_number": "JOB001",
            "url": "/api/detail/JOB001",
            "unit_id": "UNIT001",
            "brief": {
                "type": "公開招標公告",
                "title": "資訊設備採購案",
                "category": "資訊設備類",
            },
        },
    ]
    
    records = _parse_records(data, mock_logger)
    
    assert len(records) == 1
    assert records[0].title == "資訊設備採購案"
    assert records[0].organization == "國立臺灣大學"
    assert records[0].source == "g0v"
    assert records[0].category == "資訊設備類"
    assert records[0].url == "https://pcc-api.openfun.app/api/detail/JOB001"
    assert records[0].metadata["job_number"] == "JOB001"


def test_parse_records_filter_non_public_tender() -> None:
    """Test filtering logic: only process '公開招標' types."""
    mock_logger = MagicMock()
    data = [
        {
            "unit_name": "測試單位A",
            "date": 20250401,
            "job_number": "JOB_PUBLIC",
            "url": "/api/detail/JOB_PUBLIC",
            "unit_id": "UNIT_A",
            "brief": {
                "type": "公開招標公告",
                "title": "公開招標案件",
                "category": "資訊設備類",
            },
        },
        {
            "unit_name": "測試單位B",
            "date": 20250402,
            "job_number": "JOB_LIMITED",
            "url": "/api/detail/JOB_LIMITED",
            "unit_id": "UNIT_B",
            "brief": {
                "type": "限制性招標",  # Should be filtered out
                "title": "限制性招標案件",
                "category": "其他",
            },
        },
        {
            "unit_name": "測試單位C",
            "date": 20250403,
            "job_number": "JOB_SELECTIVE",
            "url": "/api/detail/JOB_SELECTIVE",
            "unit_id": "UNIT_C",
            "brief": {
                "type": "選擇性招標",  # Should be filtered out
                "title": "選擇性招標案件",
                "category": "其他",
            },
        },
    ]
    
    records = _parse_records(data, mock_logger)
    
    assert len(records) == 1
    assert records[0].title == "公開招標案件"
    assert records[0].metadata["job_number"] == "JOB_PUBLIC"


def test_parse_records_null_unit_name() -> None:
    """Test handling of null unit_name field."""
    mock_logger = MagicMock()
    data = [
        {
            "unit_name": None,  # Null unit_name
            "date": 20250410,
            "job_number": "JOB_NULL_UNIT",
            "url": "/api/detail/JOB_NULL_UNIT",
            "unit_id": "UNIT_NULL",
            "brief": {
                "type": "公開招標公告",
                "title": "無單位名稱案件",
                "category": "測試類別",
            },
        },
    ]
    
    records = _parse_records(data, mock_logger)
    
    assert len(records) == 1
    assert records[0].organization == ""  # Should default to empty string
    assert records[0].title == "無單位名稱案件"


def test_parse_records_missing_fields() -> None:
    """Test handling of missing or empty fields."""
    mock_logger = MagicMock()
    data = [
        {
            "unit_name": "測試單位",
            "date": 20250415,
            "job_number": "JOB_MISSING",
            "url": "/api/detail/JOB_MISSING",
            "unit_id": "",
            "brief": {
                "type": "公開招標公告",
                "title": "",  # Empty title - should be skipped
                "category": "測試類別",
            },
        },
        {
            "unit_name": "正常單位",
            "date": 20250416,
            "job_number": "JOB_VALID",
            "url": "/api/detail/JOB_VALID",
            "unit_id": "UNIT_VALID",
            "brief": {
                "type": "公開招標公告",
                "title": "正常案件",
                "category": "測試類別",
            },
        },
    ]
    
    records = _parse_records(data, mock_logger)
    
    # Only the valid record should be parsed
    assert len(records) == 1
    assert records[0].title == "正常案件"
    assert records[0].metadata["job_number"] == "JOB_VALID"


def test_parse_records_empty_list() -> None:
    """Test with empty data list."""
    mock_logger = MagicMock()
    data: list[dict[str, Any]] = []
    
    records = _parse_records(data, mock_logger)
    
    assert len(records) == 0


def test_extract_detail_fields_defaults_and_metadata() -> None:
    record = BidRecord(
        title="測試案",
        organization="某大學",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="g0v",
        url="https://pcc-api.openfun.app/api/detail/JOB001",
    )
    detail = {
        "budget_public": False,
        "contact": "王小姐 02-1234-5678",
        "award_method": "最低標",
    }

    _extract_detail_fields(detail, record)

    assert record.budget_amount == "未公開"
    assert record.bid_bond == "無提供"
    assert record.bid_deadline == "無提供"
    assert record.bid_opening_time == "無提供"
    assert record.metadata["contact_info"] == "王小姐 02-1234-5678"
    assert record.metadata["award_method"] == "最低標"


def test_enrich_record_uses_unit_job_lookup_and_marks_source() -> None:
    record = BidRecord(
        title="測試案",
        organization="某大學",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="gov_pcc",
        url="https://web.pcc.gov.tw/tps/SomeDetail",
        metadata={
            "g0v_unit_id": "3.79.56.3",
            "g0v_job_number": "11514",
        },
    )

    mock_settings = MagicMock()
    mock_settings.request_timeout_seconds = 30
    mock_logger = MagicMock()

    mock_response = MagicMock()
    mock_response.json.return_value = {"budget_amount": "1000000", "bid_bond": "10000"}
    mock_response.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    enriched = enrich_record(record, mock_settings, mock_logger, session=mock_session)

    assert enriched is True
    assert record.budget_amount == "1000000"
    assert record.bid_bond == "10000"
    assert record.metadata["enrichment_source"] == "g0v_api"
    assert record.metadata["enrichment_note"] == "g0v_tender_lookup:unit_id_job_number"
    assert "api/tender?" in record.metadata["g0v_tender_api_url"]


def test_enrich_record_skip_when_lookup_key_missing() -> None:
    record = BidRecord(
        title="測試案",
        organization="某大學",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="gov_pcc",
        url="https://web.pcc.gov.tw/tps/SomeDetail",
        metadata={},
    )

    mock_settings = MagicMock()
    mock_settings.request_timeout_seconds = 30
    mock_logger = MagicMock()
    mock_session = MagicMock()

    enriched = enrich_record(record, mock_settings, mock_logger, session=mock_session)

    assert enriched is False
    mock_session.get.assert_not_called()
