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
            "url": "/index/case/UNIT001/JOB001/20250407/TIQ-1-71000001",
            "unit_api_url": "/api/listbyunit?unit_id=UNIT001",
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
    assert records[0].url == ""
    assert records[0].bid_date is None
    assert records[0].announcement_date is not None
    assert records[0].announcement_date.isoformat() == "2025-04-07"
    assert records[0].metadata["job_number"] == "JOB001"
    assert records[0].metadata["g0v_human_url_state"] == "unresolved"
    assert records[0].metadata["g0v_link_resolution_state"] == "unresolved"
    assert records[0].metadata["g0v_unit_api_url"] == "https://pcc-api.openfun.app/api/listbyunit?unit_id=UNIT001"


def test_parse_records_filter_non_public_tender() -> None:
    """Test filtering logic: only process '公開招標' types."""
    mock_logger = MagicMock()
    data = [
        {
            "unit_name": "測試單位A",
            "date": 20250401,
            "job_number": "JOB_PUBLIC",
            "url": "/index/case/UNIT_A/JOB_PUBLIC/20250401/TIQ-1-71000002",
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
            "url": "/index/case/UNIT_B/JOB_LIMITED/20250402/TIQ-1-71000003",
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
            "url": "/index/case/UNIT_C/JOB_SELECTIVE/20250403/TIQ-1-71000004",
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
            "url": "/index/case/UNIT_NULL/JOB_NULL_UNIT/20250410/TIQ-1-71000005",
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
            "url": "/index/case/UNIT_M/JOB_MISSING/20250415/TIQ-1-71000006",
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
            "url": "/index/case/UNIT_VALID/JOB_VALID/20250416/TIQ-1-71000007",
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


def test_parse_records_hide_unsafe_human_link_and_keep_api_backup() -> None:
    mock_logger = MagicMock()
    data = [
        {
            "unit_name": "測試單位",
            "date": 20250407,
            "job_number": "JOB_UNSAFE",
            "url": "/api/detail/JOB_UNSAFE",
            "unit_id": "UNIT_UNSAFE",
            "tender_api_url": "/api/tender?unit_id=UNIT_UNSAFE&job_number=JOB_UNSAFE",
            "brief": {
                "type": "公開招標公告",
                "title": "連結測試案件",
                "category": "資訊設備類",
            },
        },
    ]

    records = _parse_records(data, mock_logger)

    assert len(records) == 1
    assert records[0].url.startswith("https://pcc-api.openfun.app/api/tender?")
    assert records[0].metadata["g0v_human_url_state"] == "fallback_api"
    assert "api/tender?" in records[0].metadata["g0v_tender_api_url"]


def test_parse_records_none_fields_do_not_raise() -> None:
    mock_logger = MagicMock()
    data = [
        {
            "unit_name": None,
            "date": 20250407,
            "job_number": "JOB_NONE",
            "url": None,
            "unit_id": "UNIT_NONE",
            "brief": {
                "type": "公開招標公告",
                "title": "None 防呆案件",
                "category": None,
            },
            "tender_api_url": None,
            "unit_api_url": None,
        },
    ]

    records = _parse_records(data, mock_logger)

    assert len(records) == 1
    assert records[0].organization == ""
    assert records[0].category == ""
    assert records[0].url == ""
    assert records[0].metadata["g0v_human_url_state"] == "unresolved"


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


def test_extract_detail_fields_reads_pcc_colon_keys() -> None:
    record = BidRecord(
        title="大王國中網路優化採購案",
        organization="",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="g0v",
        url="https://pcc-api.openfun.app/api/tender?unit_id=3.76.54&job_number=115200720099",
    )
    detail = {
        "機關資料:機關名稱": "臺東縣政府",
        "機關資料:聯絡人": "大王國中，承辦人：葛守仁先生",
        "機關資料:聯絡電話": "(089)781324#240",
        "採購資料:預算金額": "9,500,000元",
        "採購資料:預算金額是否公開": "是",
        "招標資料:決標方式": "最有利標",
        "領投開標:截止投標": "115/05/11 17:00",
        "領投開標:開標時間": "115/05/12 09:30",
        "領投開標:是否須繳納押標金:押標金額度": "450,000",
        "領投開標:是否須繳納押標金": "是，尚未提供廠商線上繳納押標金",
    }

    _extract_detail_fields(detail, record)

    assert record.organization == "臺東縣政府"
    assert record.budget_amount == "9,500,000元"
    assert record.amount_value == 9_500_000
    assert record.bid_bond == "450,000"
    assert record.bid_deadline == "115/05/11 17:00"
    assert record.bid_opening_time == "115/05/12 09:30"
    assert record.metadata["contact_info"] == "大王國中，承辦人：葛守仁先生 (089)781324#240"
    assert record.metadata["award_method"] == "最有利標"


def test_extract_detail_fields_bid_bond_ignores_online_payment_fee() -> None:
    record = BidRecord(
        title="國防醫學大學測試案",
        organization="",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="g0v",
        url="",
    )
    detail = {
        "領投開標:是否須繳納押標金": (
            "是，且提供廠商線上繳納押標金 "
            "押標金額度：標價之一定比率：按廠商報價總金額百分之3繳交。 "
            "廠商線上繳納押標金手續費：10元"
        ),
    }

    _extract_detail_fields(detail, record)

    assert record.bid_bond == "3%"


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
    mock_response.json.return_value = {
        "records": [
            {
                "detail": {
                    "url": "https://web.pcc.gov.tw/tps/QueryTender/query/searchTenderDetail?pkPmsMain=AAA",
                    "budget_amount": "1000000",
                    "bid_bond": "10000",
                }
            }
        ]
    }
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
    assert record.url.startswith("https://web.pcc.gov.tw/tps/")
    assert record.metadata["g0v_link_resolution_state"] == "resolved_official"


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


def test_enrich_record_fallbacks_to_tender_api_when_official_link_missing() -> None:
    record = BidRecord(
        title="測試案",
        organization="某大學",
        bid_date=None,
        amount_raw="",
        amount_value=None,
        source="g0v",
        url="",
        metadata={
            "g0v_tender_api_url": "https://pcc-api.openfun.app/api/tender?unit_id=UNIT001&job_number=JOB001",
        },
    )

    mock_settings = MagicMock()
    mock_settings.request_timeout_seconds = 30
    mock_settings.g0v_human_link_mode = "safe_only"
    mock_logger = MagicMock()

    mock_response = MagicMock()
    mock_response.json.return_value = {"records": [{"detail": {"budget_public": False}}]}
    mock_response.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    enriched = enrich_record(record, mock_settings, mock_logger, session=mock_session)

    assert enriched is True
    assert record.url.startswith("https://pcc-api.openfun.app/api/tender?")
    assert record.metadata["g0v_link_resolution_state"] == "fallback_api"
