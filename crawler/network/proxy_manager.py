from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProxyEntry:
    """A single proxy endpoint."""

    server: str  # e.g. "http://host:port" or "socks5://host:port"
    username: str = ""
    password: str = ""
    label: str = ""  # optional tag for logging (e.g. "residential-us")

    def to_playwright_proxy(self) -> dict[str, str]:
        proxy: dict[str, str] = {"server": self.server}
        if self.username:
            proxy["username"] = self.username
        if self.password:
            proxy["password"] = self.password
        return proxy


@dataclass(slots=True)
class ProxyConfig:
    """Configuration for proxy rotation."""

    enabled: bool = False
    proxies: list[ProxyEntry] = field(default_factory=list)
    strategy: str = "round_robin"  # "round_robin" | "random" | "sticky"
    sticky_per_domain: bool = True


class ProxyManager:
    """Manage proxy selection and rotation for Playwright sessions.

    Strategies:
      - round_robin: cycle through proxies in order
      - random: pick a random proxy each time
      - sticky: assign one proxy per domain and reuse it
    """

    def __init__(self, config: ProxyConfig | None = None) -> None:
        self._config = config or ProxyConfig()
        self._index: int = 0
        self._domain_map: dict[str, ProxyEntry] = {}

    @property
    def enabled(self) -> bool:
        return self._config.enabled and len(self._config.proxies) > 0

    def get_proxy(self, domain: str = "") -> Optional[dict[str, str]]:
        """Return a Playwright-compatible proxy dict, or None if no proxy is configured."""
        if not self.enabled:
            return None

        entry = self._select(domain)
        if entry is None:
            return None

        # Log proxy used without exposing credentials
        logger.debug(
            "proxy_selected",
            extra={"server": entry.server, "label": entry.label, "domain": domain},
        )
        return entry.to_playwright_proxy()

    def _select(self, domain: str) -> Optional[ProxyEntry]:
        proxies = self._config.proxies
        if not proxies:
            return None

        strategy = self._config.strategy

        if strategy == "sticky" and domain:
            if domain in self._domain_map:
                return self._domain_map[domain]
            entry = random.choice(proxies)
            self._domain_map[domain] = entry
            return entry

        if strategy == "random":
            return random.choice(proxies)

        # round_robin (default)
        entry = proxies[self._index % len(proxies)]
        self._index += 1
        return entry

    def report_failure(self, proxy_server: str, domain: str = "") -> None:
        """Report a proxy failure. Future: could temporarily disable bad proxies."""
        logger.warning(
            "proxy_failure",
            extra={"server": proxy_server, "domain": domain},
        )
        # Remove sticky assignment so next call gets a different proxy
        if domain in self._domain_map:
            del self._domain_map[domain]

    def reset(self) -> None:
        self._index = 0
        self._domain_map.clear()
