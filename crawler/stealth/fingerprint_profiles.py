from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Any, Optional


@dataclass(slots=True)
class FingerprintProfile:
    """A consistent browser fingerprint to avoid mismatched property combinations."""

    user_agent: str
    viewport_width: int
    viewport_height: int
    locale: str
    timezone_id: str
    color_scheme: str
    platform: str
    vendor: str
    renderer: str
    languages: list[str] = field(default_factory=list)
    device_memory: int = 8
    hardware_concurrency: int = 8
    max_touch_points: int = 0
    webgl_vendor: str = ""
    webgl_renderer: str = ""


# Realistic desktop Chrome profiles (Windows / Mac / Linux)
_PROFILES: list[FingerprintProfile] = [
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport_width=1920,
        viewport_height=1080,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="Win32",
        vendor="Google Inc.",
        renderer="ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB Direct3D11 vs_5_0 ps_5_0, D3D11)",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=8,
        hardware_concurrency=8,
        max_touch_points=0,
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        viewport_width=1366,
        viewport_height=768,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="Win32",
        vendor="Google Inc.",
        renderer="ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=16,
        hardware_concurrency=12,
        max_touch_points=0,
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport_width=1440,
        viewport_height=900,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="MacIntel",
        vendor="Google Inc.",
        renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=8,
        hardware_concurrency=8,
        max_touch_points=0,
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        viewport_width=1680,
        viewport_height=1050,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="MacIntel",
        vendor="Apple Computer, Inc.",
        renderer="Apple GPU",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=16,
        hardware_concurrency=10,
        max_touch_points=0,
        webgl_vendor="Apple Inc.",
        webgl_renderer="Apple GPU",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport_width=1920,
        viewport_height=1080,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="Linux x86_64",
        vendor="Google Inc.",
        renderer="ANGLE (Mesa, llvmpipe (LLVM 15.0.7, 256 bits), OpenGL 4.5)",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=8,
        hardware_concurrency=4,
        max_touch_points=0,
        webgl_vendor="Google Inc. (Mesa)",
        webgl_renderer="ANGLE (Mesa, llvmpipe (LLVM 15.0.7, 256 bits), OpenGL 4.5)",
    ),
    # --- New diverse profiles for enhanced anti-detection ---
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport_width=2560,
        viewport_height=1440,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="Win32",
        vendor="Google Inc.",
        renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=16,
        hardware_concurrency=12,
        max_touch_points=0,
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        viewport_width=1600,
        viewport_height=900,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="Win32",
        vendor="Google Inc.",
        renderer="ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
        languages=["zh-TW", "zh", "en"],
        device_memory=16,
        hardware_concurrency=16,
        max_touch_points=0,
        webgl_vendor="Google Inc. (AMD)",
        webgl_renderer="ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        viewport_width=1512,
        viewport_height=982,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="dark",
        platform="MacIntel",
        vendor="Google Inc.",
        renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=16,
        hardware_concurrency=8,
        max_touch_points=0,
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        viewport_width=1920,
        viewport_height=1080,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="Win32",
        vendor="Google Inc.",
        renderer="ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=8,
        hardware_concurrency=8,
        max_touch_points=0,
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport_width=1280,
        viewport_height=720,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="Win32",
        vendor="Google Inc.",
        renderer="ANGLE (Intel, Intel(R) HD Graphics 530 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        languages=["zh-TW", "en"],
        device_memory=4,
        hardware_concurrency=4,
        max_touch_points=0,
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) HD Graphics 530 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport_width=1728,
        viewport_height=1117,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="dark",
        platform="MacIntel",
        vendor="Google Inc.",
        renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2 Pro, Unspecified Version)",
        languages=["zh-TW", "zh", "en"],
        device_memory=32,
        hardware_concurrency=12,
        max_touch_points=0,
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2 Pro, Unspecified Version)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        viewport_width=1920,
        viewport_height=1200,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="Linux x86_64",
        vendor="Google Inc.",
        renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 2060 OpenGL 4.6.0)",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=16,
        hardware_concurrency=6,
        max_touch_points=0,
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 2060 OpenGL 4.6.0)",
    ),
    FingerprintProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport_width=1536,
        viewport_height=864,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        color_scheme="light",
        platform="Win32",
        vendor="Google Inc.",
        renderer="ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        languages=["zh-TW", "zh", "en-US", "en"],
        device_memory=8,
        hardware_concurrency=6,
        max_touch_points=0,
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
]


def _normalize_languages(locale: str) -> list[str]:
    base_lang = locale.split("-")[0] if "-" in locale else locale
    languages = [locale]
    if base_lang and base_lang != locale:
        languages.append(base_lang)
    if "en-US" not in languages:
        languages.append("en-US")
    if "en" not in languages:
        languages.append("en")
    return languages


def _detect_proxy_locale_timezone(proxy_server: str) -> tuple[str, str] | None:
    """Best-effort mapping hook for proxy geography -> locale/timezone consistency."""
    normalized = proxy_server.lower()
    mappings = [
        (("taiwan", "taipei", ".tw"), ("zh-TW", "Asia/Taipei")),
        (("japan", "tokyo", ".jp"), ("ja-JP", "Asia/Tokyo")),
        (("singapore", ".sg"), ("en-SG", "Asia/Singapore")),
        (("us", "usa", "america", ".us"), ("en-US", "America/Los_Angeles")),
    ]
    for keywords, locale_timezone in mappings:
        if any(keyword in normalized for keyword in keywords):
            return locale_timezone
    return None


def apply_profile_overrides(
    profile: FingerprintProfile,
    *,
    locale_pool: Optional[list[str]] = None,
    timezone_pool: Optional[list[str]] = None,
    align_with_proxy: bool = False,
    proxy_server: str = "",
    rng: Any = random,
) -> FingerprintProfile:
    """Apply configurable locale/timezone overrides while keeping defaults unchanged."""
    locale = profile.locale
    timezone_id = profile.timezone_id

    if locale_pool:
        locale = rng.choice(locale_pool)
    if timezone_pool:
        timezone_id = rng.choice(timezone_pool)

    if align_with_proxy and proxy_server:
        mapped = _detect_proxy_locale_timezone(proxy_server)
        if mapped:
            locale, timezone_id = mapped

    if locale == profile.locale and timezone_id == profile.timezone_id:
        return profile

    return replace(
        profile,
        locale=locale,
        timezone_id=timezone_id,
        languages=_normalize_languages(locale),
    )


def pick_profile(
    seed: Optional[int] = None,
    *,
    locale_pool: Optional[list[str]] = None,
    timezone_pool: Optional[list[str]] = None,
    align_with_proxy: bool = False,
    proxy_server: str = "",
) -> FingerprintProfile:
    """Pick a profile with optional locale/timezone pool overrides."""
    rng = random.Random(seed) if seed is not None else random
    base_profile = rng.choice(_PROFILES)
    return apply_profile_overrides(
        base_profile,
        locale_pool=locale_pool,
        timezone_pool=timezone_pool,
        align_with_proxy=align_with_proxy,
        proxy_server=proxy_server,
        rng=rng,
    )


def add_viewport_jitter(profile: FingerprintProfile) -> tuple[int, int]:
    """Add small random jitter to viewport size to avoid exact-match detection."""
    w = profile.viewport_width + random.randint(-20, 20)
    h = profile.viewport_height + random.randint(-10, 10)
    return max(w, 800), max(h, 600)
