"""Unit tests for g0v API crawler."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from crawler.g0v import _parse_records


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
