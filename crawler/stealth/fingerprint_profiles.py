from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


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
]


def pick_profile(seed: Optional[int] = None) -> FingerprintProfile:
    """Pick a random fingerprint profile. Optionally seed for reproducibility."""
    if seed is not None:
        rng = random.Random(seed)
        return rng.choice(_PROFILES)
    return random.choice(_PROFILES)


def add_viewport_jitter(profile: FingerprintProfile) -> tuple[int, int]:
    """Add small random jitter to viewport size to avoid exact-match detection."""
    w = profile.viewport_width + random.randint(-20, 20)
    h = profile.viewport_height + random.randint(-10, 10)
    return max(w, 800), max(h, 600)
