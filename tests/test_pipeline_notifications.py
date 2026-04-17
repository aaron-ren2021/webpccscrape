from __future__ import annotations

from core.config import Settings


def test_g0v_notify_today_only_default_true() -> None:
    settings = Settings()
    assert settings.g0v_notify_today_only is True


def test_g0v_notify_today_only_can_be_disabled() -> None:
    settings = Settings(g0v_notify_today_only=False)
    assert settings.g0v_notify_today_only is False
