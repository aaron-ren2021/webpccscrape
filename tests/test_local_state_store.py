from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from core.models import BidRecord
from storage.local_state_store import LocalJsonStateStore


def _record(title: str = "資訊設備採購") -> BidRecord:
    return BidRecord(
        title=title,
        organization="某某大學",
        bid_date=None,
        amount_raw="100萬",
        amount_value=1_000_000,
        source="g0v",
        url="",
        metadata={
            "g0v_unit_id": "UNIT001",
            "g0v_job_number": "JOB001",
        },
    )


def test_local_state_store_alias_key_matches_notified_record(tmp_path) -> None:
    store = LocalJsonStateStore(tmp_path / "notified_state.json", MagicMock())
    store.mark_notified([_record()])

    keys = store.get_notified_keys()

    assert "source:g0v:unit001:job001" in keys


def test_local_state_store_merges_new_aliases_into_existing_entry(tmp_path) -> None:
    path = tmp_path / "notified_state.json"
    store = LocalJsonStateStore(path, MagicMock())
    first = _record()
    store.mark_notified([first])

    second = _record()
    second.url = "https://web.pcc.gov.tw/tps/QueryTender/query/searchTenderDetail?pkPmsMain=AAA"
    store.mark_notified([second])

    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data["entries"]
    assert len(entries) == 1
    alias_keys = next(iter(entries.values()))["alias_keys"]
    assert "source:g0v:unit001:job001" in alias_keys
    assert "source:gov_pcc:pkPmsMain:aaa" in alias_keys


def test_local_state_store_prunes_old_expired_records(tmp_path) -> None:
    path = tmp_path / "notified_state.json"
    old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "entries": {
                    "old": {
                        "primary_key": "old",
                        "alias_keys": ["old"],
                        "notified_at": old,
                        "bid_deadline": "",
                    },
                    "recent": {
                        "primary_key": "recent",
                        "alias_keys": ["recent"],
                        "notified_at": recent,
                        "bid_deadline": "",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    keys = LocalJsonStateStore(path, MagicMock(), retention_days=90).get_notified_keys()

    assert "old" not in keys
    assert "recent" in keys
