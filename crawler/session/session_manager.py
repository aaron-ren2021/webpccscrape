from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default directory for session state files
_DEFAULT_SESSION_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".sessions")


class SessionManager:
    """Persist and reload Playwright browser storage state across runs.

    Storage state includes cookies and localStorage, making repeat visits
    look like a returning user rather than a fresh bot.
    """

    def __init__(self, session_dir: str = "") -> None:
        self._session_dir = Path(session_dir or _DEFAULT_SESSION_DIR)
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, domain: str) -> Path:
        safe_name = domain.replace(".", "_").replace("/", "_").replace(":", "_")
        return self._session_dir / f"{safe_name}.json"

    def load_state(self, domain: str) -> Optional[str]:
        """Return path to stored state file if it exists and is valid, else None."""
        path = self._state_path(domain)
        if not path.exists():
            logger.debug("session_not_found", extra={"domain": domain})
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("session_corrupted", extra={"domain": domain})
            path.unlink(missing_ok=True)
            return None

        # Check expiry marker (optional field)
        expires = data.get("_session_expires", 0)
        if expires and time.time() > expires:
            logger.info("session_expired", extra={"domain": domain})
            path.unlink(missing_ok=True)
            return None

        logger.info("session_loaded", extra={"domain": domain, "path": str(path)})
        return str(path)

    def save_state(self, context: Any, domain: str, ttl_hours: float = 24.0) -> str:
        """Save context storage state to disk. Returns the file path."""
        path = self._state_path(domain)
        state = context.storage_state()

        # Inject an expiry marker so we can auto-expire stale sessions
        if isinstance(state, dict):
            state["_session_expires"] = time.time() + ttl_hours * 3600
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        elif isinstance(state, str):
            # In case storage_state returns JSON string directly
            parsed = json.loads(state)
            parsed["_session_expires"] = time.time() + ttl_hours * 3600
            path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            # Fallback: save via Playwright's path-based API
            context.storage_state(path=str(path))

        logger.info("session_saved", extra={"domain": domain, "path": str(path)})
        return str(path)

    def clear(self, domain: str) -> None:
        """Remove stored session for a given domain."""
        path = self._state_path(domain)
        if path.exists():
            path.unlink()
            logger.info("session_cleared", extra={"domain": domain})

    def clear_all(self) -> None:
        """Remove all stored sessions."""
        for path in self._session_dir.glob("*.json"):
            path.unlink()
        logger.info("all_sessions_cleared")
