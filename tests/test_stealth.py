from __future__ import annotations

import json
import tempfile
import time

from crawler.behavior.throttle import ThrottleConfig, ThrottleController
from crawler.detection.detection_logger import (
    CrawlOutcome,
    DetectionLogger,
    classify_outcome,
    classify_outcome_with_page,
)
from crawler.network.proxy_manager import ProxyConfig, ProxyEntry, ProxyManager
from crawler.session.session_manager import SessionManager
from crawler.stealth.fingerprint_profiles import (
    FingerprintProfile,
    add_viewport_jitter,
    pick_profile,
)


# --- fingerprint_profiles ---

def test_pick_profile_returns_valid_profile():
    p = pick_profile()
    assert isinstance(p, FingerprintProfile)
    assert p.user_agent
    assert p.locale == "zh-TW"
    assert p.timezone_id == "Asia/Taipei"


def test_pick_profile_seeded_is_deterministic():
    a = pick_profile(seed=42)
    b = pick_profile(seed=42)
    assert a.user_agent == b.user_agent
    assert a.platform == b.platform


def test_viewport_jitter_stays_in_range():
    p = pick_profile(seed=1)
    for _ in range(20):
        w, h = add_viewport_jitter(p)
        assert w >= 800
        assert h >= 600
        assert abs(w - p.viewport_width) <= 20
        assert abs(h - p.viewport_height) <= 10


def test_pick_profile_with_locale_timezone_pool():
    p = pick_profile(seed=42, locale_pool=["ja-JP"], timezone_pool=["Asia/Tokyo"])
    assert p.locale == "ja-JP"
    assert p.timezone_id == "Asia/Tokyo"


def test_pick_profile_proxy_alignment_hook():
    p = pick_profile(seed=42, align_with_proxy=True, proxy_server="http://us-proxy-1.example:8080")
    assert p.locale == "en-US"
    assert p.timezone_id == "America/Los_Angeles"


# --- classify_outcome ---

def test_classify_success():
    assert classify_outcome("<html><body>OK</body></html>") == CrawlOutcome.SUCCESS


def test_classify_captcha():
    assert classify_outcome("<html>驗證碼檢核 page</html>") == CrawlOutcome.CAPTCHA
    assert classify_outcome("<html>hCaptcha widget</html>") == CrawlOutcome.CAPTCHA


def test_classify_hard_block_403():
    assert classify_outcome("<html>Forbidden</html>", status_code=403) == CrawlOutcome.HARD_BLOCK


def test_classify_rate_limited_429():
    assert classify_outcome("<html>rate limited</html>", status_code=429) == CrawlOutcome.RATE_LIMITED


def test_classify_timeout():
    assert classify_outcome("", timed_out=True) == CrawlOutcome.TIMEOUT


def test_classify_cloudflare_challenge():
    assert classify_outcome("<html>Just a moment...</html>") == CrawlOutcome.CLOUDFLARE_CHALLENGE
    assert classify_outcome('<html><div class="cf-browser-verification"></div></html>') == CrawlOutcome.CLOUDFLARE_CHALLENGE


def test_classify_empty_content():
    assert classify_outcome("<html></html>", expected_selector_found=False) == CrawlOutcome.EMPTY_CONTENT


def test_classify_access_denied():
    assert classify_outcome("<html>access denied</html>") == CrawlOutcome.ACCESS_DENIED


def test_classify_rate_limited_content():
    assert classify_outcome("<html>請稍後再試</html>") == CrawlOutcome.RATE_LIMITED


def test_classify_soft_block_markers():
    assert classify_outcome("<html>unusual traffic detected</html>") == CrawlOutcome.SOFT_BLOCK
    assert classify_outcome("<html>異常流量</html>") == CrawlOutcome.SOFT_BLOCK


class _FakeLocator:
    def __init__(self, count_value: int) -> None:
        self._count_value = count_value

    def count(self) -> int:
        return self._count_value


class _FakePage:
    def __init__(self, selector_counts: dict[str, int] | None = None, button_count: int = 0, raise_locator: bool = False) -> None:
        self._selector_counts = selector_counts or {}
        self._button_count = button_count
        self._raise_locator = raise_locator

    def locator(self, selector: str) -> _FakeLocator:
        if self._raise_locator:
            raise RuntimeError("locator unavailable")
        return _FakeLocator(self._selector_counts.get(selector, 0))

    def get_by_role(self, role: str, name=None) -> _FakeLocator:
        return _FakeLocator(self._button_count)


def test_classify_outcome_with_page_locator_hit():
    page = _FakePage(selector_counts={"form[action*='captcha'], #captcha, .g-recaptcha, .h-captcha, [class*='cf-turnstile']": 1})
    outcome = classify_outcome_with_page(
        page=page,
        html="<html><body>normal</body></html>",
    )
    assert outcome == CrawlOutcome.CAPTCHA


def test_classify_outcome_with_page_regex_fallback_on_locator_error():
    page = _FakePage(raise_locator=True)
    outcome = classify_outcome_with_page(
        page=page,
        html="<html>Just a moment...</html>",
    )
    assert outcome == CrawlOutcome.CLOUDFLARE_CHALLENGE


def test_classify_outcome_with_page_timeout_priority():
    page = _FakePage(selector_counts={"#captcha": 1})
    outcome = classify_outcome_with_page(
        page=page,
        html="<html>驗證碼檢核</html>",
        timed_out=True,
    )
    assert outcome == CrawlOutcome.TIMEOUT


def test_classify_outcome_with_page_expected_selector_missing():
    page = _FakePage()
    outcome = classify_outcome_with_page(
        page=page,
        html="<html></html>",
        expected_selector_found=False,
    )
    assert outcome == CrawlOutcome.EMPTY_CONTENT


def test_crawl_outcome_is_str():
    """CrawlOutcome is a StrEnum and compares equal to plain strings."""
    assert CrawlOutcome.SUCCESS == "success"
    assert isinstance(CrawlOutcome.CAPTCHA, str)


def test_detection_rules_sorted_by_priority():
    from crawler.detection.detection_logger import DETECTION_RULES
    priorities = [r.priority for r in DETECTION_RULES]
    assert priorities == sorted(priorities, reverse=True)


# --- DetectionLogger ---

def test_detection_logger_records_events():
    with tempfile.TemporaryDirectory() as td:
        dl = DetectionLogger(artifact_dir=td)
        dl.log_event("https://example.com", CrawlOutcome.SUCCESS)
        dl.log_event("https://example.com/2", CrawlOutcome.CAPTCHA)

        assert len(dl.events) == 2
        assert dl.summary() == {"success": 1, "captcha": 1}
        assert dl.success_rate() == 0.5


def test_detection_logger_html_capture():
    with tempfile.TemporaryDirectory() as td:
        dl = DetectionLogger(artifact_dir=td)
        path = dl.capture_html("<html>test</html>", "https://x.com", label="test")
        assert path.endswith(".html")
        with open(path) as f:
            assert "<html>test</html>" in f.read()


def test_detection_logger_log_failure_records_event_and_artifacts_once(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        dl = DetectionLogger(artifact_dir=td)
        calls: list[tuple[str, str]] = []

        def fake_screenshot(page, url, label=""):
            calls.append(("screenshot", str(label)))
            return "/tmp/fake.png"

        def fake_html(html, url, label=""):
            calls.append(("html", str(label)))
            return "/tmp/fake.html"

        monkeypatch.setattr(dl, "capture_screenshot", fake_screenshot)
        monkeypatch.setattr(dl, "capture_html", fake_html)

        event = dl.log_failure(
            page=object(),
            html="<html>blocked</html>",
            url="https://example.com/fail",
            outcome=CrawlOutcome.SOFT_BLOCK,
        )

        assert event["outcome"] == CrawlOutcome.SOFT_BLOCK
        assert calls == [("screenshot", "soft_block"), ("html", "soft_block")]


# --- ThrottleController ---

def test_throttle_normal_delay():
    cfg = ThrottleConfig(delay_min=0, delay_max=0.001, cooldown_after_n=100)
    tc = ThrottleController(cfg)
    wait = tc.wait_before_request()
    assert wait >= 0


def test_throttle_backoff():
    cfg = ThrottleConfig(backoff_base=0.001, backoff_max=0.01, backoff_multiplier=2.0, jitter_factor=0)
    tc = ThrottleController(cfg)
    w1 = tc.backoff_after_detection()
    w2 = tc.backoff_after_detection()
    # Second backoff should be >= first (exponential)
    assert w2 >= w1


def test_throttle_reset():
    cfg = ThrottleConfig(delay_min=0, delay_max=0.001)
    tc = ThrottleController(cfg)
    tc.wait_before_request()
    tc.backoff_after_detection()
    tc.reset()
    assert tc._request_count == 0
    assert tc._consecutive_failures == 0


# --- SessionManager ---

def test_session_manager_load_nonexistent():
    with tempfile.TemporaryDirectory() as td:
        sm = SessionManager(session_dir=td)
        assert sm.load_state("nonexistent.com") is None


def test_session_manager_save_and_load(tmp_path):
    sm = SessionManager(session_dir=str(tmp_path))

    # Simulate a context with storage_state method
    class FakeContext:
        def storage_state(self, path=None):
            return {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}

    ctx = FakeContext()
    path = sm.save_state(ctx, "test.com", ttl_hours=1.0)
    assert path

    loaded = sm.load_state("test.com")
    assert loaded == path


def test_session_manager_expired(tmp_path):
    sm = SessionManager(session_dir=str(tmp_path))
    # Write a session that's already expired
    state = {"cookies": [], "origins": [], "_session_expires": time.time() - 100}
    p = tmp_path / "test_com.json"
    p.write_text(json.dumps(state))

    assert sm.load_state("test.com") is None


def test_session_manager_clear(tmp_path):
    sm = SessionManager(session_dir=str(tmp_path))
    p = tmp_path / "test_com.json"
    p.write_text("{}")
    sm.clear("test.com")
    assert not p.exists()


# --- ProxyManager ---

def test_proxy_manager_disabled():
    pm = ProxyManager(ProxyConfig(enabled=False))
    assert pm.get_proxy("example.com") is None


def test_proxy_manager_round_robin():
    entries = [ProxyEntry(server=f"http://proxy{i}:8080") for i in range(3)]
    pm = ProxyManager(ProxyConfig(enabled=True, proxies=entries, strategy="round_robin"))
    results = [pm.get_proxy("a.com")["server"] for _ in range(6)]
    assert results == [
        "http://proxy0:8080", "http://proxy1:8080", "http://proxy2:8080",
        "http://proxy0:8080", "http://proxy1:8080", "http://proxy2:8080",
    ]


def test_proxy_manager_sticky():
    entries = [ProxyEntry(server=f"http://proxy{i}:8080") for i in range(3)]
    pm = ProxyManager(ProxyConfig(enabled=True, proxies=entries, strategy="sticky"))
    first = pm.get_proxy("a.com")["server"]
    # Same domain should get exactly the same proxy
    for _ in range(5):
        assert pm.get_proxy("a.com")["server"] == first


def test_proxy_manager_report_failure_clears_sticky():
    entries = [ProxyEntry(server="http://proxy0:8080"), ProxyEntry(server="http://proxy1:8080")]
    pm = ProxyManager(ProxyConfig(enabled=True, proxies=entries, strategy="sticky"))
    first = pm.get_proxy("a.com")["server"]
    pm.report_failure(first, "a.com")
    # After failure report, sticky is cleared; next call may pick a different proxy
    assert pm.get_proxy("a.com") is not None


def test_proxy_entry_to_playwright_proxy():
    e = ProxyEntry(server="http://host:1234", username="u", password="p")
    d = e.to_playwright_proxy()
    assert d == {"server": "http://host:1234", "username": "u", "password": "p"}
