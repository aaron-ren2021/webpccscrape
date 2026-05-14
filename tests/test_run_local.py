from __future__ import annotations

import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import run_local


@dataclass
class _SourceStatus:
    success: bool


class _Result:
    crawled_count = 1
    filtered_count = 1
    deduped_count = 1
    new_count = 1
    notification_sent = True
    notification_backend = "smtp"
    errors: list[str] = []
    source_status = [_SourceStatus(success=True)]

    def to_dict(self) -> dict[str, int]:
        return {"new_count": self.new_count}


def _prepare_main(monkeypatch: pytest.MonkeyPatch, tmp_path, argv: list[str]) -> SimpleNamespace:
    calls = SimpleNamespace(settings_from_env=0, run_monitor=0, settings=None)

    def fake_from_env() -> SimpleNamespace:
        calls.settings_from_env += 1
        calls.settings = SimpleNamespace(dry_run=False, preview_html_path="")
        return calls.settings

    def fake_run_monitor(*, settings, logger, persist_state: bool) -> _Result:
        calls.run_monitor += 1
        calls.settings = settings
        calls.persist_state = persist_state
        return _Result()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_local.py", *argv])
    monkeypatch.setattr(run_local.Settings, "from_env", fake_from_env)
    monkeypatch.setattr(run_local, "run_monitor", fake_run_monitor)
    return calls


def test_formal_send_on_master_proceeds_to_run_monitor(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls = _prepare_main(monkeypatch, tmp_path, [])
    monkeypatch.setattr(run_local, "_detect_current_git_branch", lambda: "master")

    exit_code = run_local.main()

    assert exit_code == 0
    assert calls.settings_from_env == 1
    assert calls.run_monitor == 1


def test_formal_send_on_non_master_logs_and_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = _prepare_main(monkeypatch, tmp_path, [])
    monkeypatch.setattr(run_local, "_detect_current_git_branch", lambda: "feature/test")

    exit_code = run_local.main()

    assert exit_code == 1
    assert calls.settings_from_env == 0
    assert calls.run_monitor == 0
    assert any(
        record.message == "production_branch_guard_blocked"
        and record.current_branch == "feature/test"
        and record.expected_branch == "master"
        for record in caplog.records
    )


def test_no_send_on_non_master_proceeds(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls = _prepare_main(monkeypatch, tmp_path, ["--no-send"])
    monkeypatch.setattr(run_local, "_detect_current_git_branch", lambda: "feature/test")

    exit_code = run_local.main()

    assert exit_code == 0
    assert calls.settings_from_env == 1
    assert calls.run_monitor == 1
    assert calls.settings.dry_run is True


def test_git_detection_failure_in_formal_send_logs_and_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = _prepare_main(monkeypatch, tmp_path, [])

    def fail_detection() -> str:
        raise RuntimeError("git unavailable")

    monkeypatch.setattr(run_local, "_detect_current_git_branch", fail_detection)

    exit_code = run_local.main()

    assert exit_code == 1
    assert calls.settings_from_env == 0
    assert calls.run_monitor == 0
    assert any(
        record.message == "production_branch_guard_blocked"
        and record.current_branch == ""
        and record.expected_branch == "master"
        and "git unavailable" in record.detection_error
        for record in caplog.records
    )
