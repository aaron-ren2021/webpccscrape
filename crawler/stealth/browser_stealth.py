from __future__ import annotations

import logging
from typing import Any, Optional

from crawler.stealth.fingerprint_profiles import (
    FingerprintProfile,
    add_viewport_jitter,
    pick_profile,
)

logger = logging.getLogger(__name__)

# JavaScript to patch common automation-detectable properties.
# Applied via page.add_init_script before any page navigation.
_STEALTH_JS = """
() => {
    // --- Hide webdriver property ---
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // --- Chrome runtime stub ---
    if (!window.chrome) {
        window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
    }

    // --- Permissions query patch ---
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );

    // --- Plugin array ---
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ],
    });

    // --- Languages ---
    Object.defineProperty(navigator, 'languages', {
        get: () => %%LANGUAGES%%,
    });

    // --- Platform ---
    Object.defineProperty(navigator, 'platform', {
        get: () => '%%PLATFORM%%',
    });

    // --- Vendor ---
    Object.defineProperty(navigator, 'vendor', {
        get: () => '%%VENDOR%%',
    });

    // --- Hardware concurrency ---
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => %%HARDWARE_CONCURRENCY%%,
    });

    // --- Device memory ---
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => %%DEVICE_MEMORY%%,
    });

    // --- Max touch points ---
    Object.defineProperty(navigator, 'maxTouchPoints', {
        get: () => %%MAX_TOUCH_POINTS%%,
    });

    // --- WebGL vendor/renderer override ---
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return '%%WEBGL_VENDOR%%';
        if (param === 37446) return '%%WEBGL_RENDERER%%';
        return getParameter.call(this, param);
    };
    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return '%%WEBGL_VENDOR%%';
        if (param === 37446) return '%%WEBGL_RENDERER%%';
        return getParameter2.call(this, param);
    };

    // --- iframe contentWindow patch ---
    const origDescriptor = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
    if (origDescriptor) {
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function() {
                const win = origDescriptor.get.call(this);
                if (win) {
                    try {
                        Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined });
                    } catch(e) {}
                }
                return win;
            }
        });
    }

    // --- Prevent toString detection of patched functions ---
    const nativeToString = Function.prototype.toString;
    const myToString = function() {
        if (this === window.navigator.permissions.query) {
            return 'function query() { [native code] }';
        }
        return nativeToString.call(this);
    };
    Function.prototype.toString = myToString;
}
"""


def _build_stealth_script(profile: FingerprintProfile) -> str:
    """Replace placeholders in the stealth JS with profile-specific values."""
    js = _STEALTH_JS
    js = js.replace("%%LANGUAGES%%", str(profile.languages))
    js = js.replace("%%PLATFORM%%", profile.platform)
    js = js.replace("%%VENDOR%%", profile.vendor)
    js = js.replace("%%HARDWARE_CONCURRENCY%%", str(profile.hardware_concurrency))
    js = js.replace("%%DEVICE_MEMORY%%", str(profile.device_memory))
    js = js.replace("%%MAX_TOUCH_POINTS%%", str(profile.max_touch_points))
    js = js.replace("%%WEBGL_VENDOR%%", profile.webgl_vendor or profile.vendor)
    js = js.replace("%%WEBGL_RENDERER%%", profile.webgl_renderer or profile.renderer)
    return js


def create_stealth_context(
    browser: Any,
    profile: Optional[FingerprintProfile] = None,
    proxy: Optional[dict[str, str]] = None,
    storage_state: Optional[str] = None,
) -> tuple[Any, FingerprintProfile]:
    """Create a Playwright BrowserContext with stealth patches applied.

    Returns (context, profile) so callers can log the profile used.
    """
    if profile is None:
        profile = pick_profile()

    vw, vh = add_viewport_jitter(profile)

    context_kwargs: dict[str, Any] = {
        "user_agent": profile.user_agent,
        "viewport": {"width": vw, "height": vh},
        "locale": profile.locale,
        "timezone_id": profile.timezone_id,
        "color_scheme": profile.color_scheme,
        "extra_http_headers": {
            "Accept-Language": ",".join(
                f"{lang};q={round(1.0 - i * 0.1, 1)}"
                for i, lang in enumerate(profile.languages)
            ),
        },
    }

    if proxy:
        context_kwargs["proxy"] = proxy

    if storage_state:
        context_kwargs["storage_state"] = storage_state

    context = browser.new_context(**context_kwargs)

    # Inject stealth init script
    stealth_js = _build_stealth_script(profile)
    context.add_init_script(stealth_js)

    logger.debug(
        "stealth_context_created",
        extra={
            "ua": profile.user_agent[:60],
            "viewport": f"{vw}x{vh}",
            "platform": profile.platform,
        },
    )
    return context, profile
