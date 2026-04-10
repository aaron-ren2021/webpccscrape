"""Identity Manager for cumulative risk mitigation.

An 'identity' is the combination of:
- Browser fingerprint (user-agent, viewport, WebGL, etc.)
- Session state (cookies, localStorage)
- Proxy IP (if enabled)

The website sees these as a single 'user'. To avoid cumulative detection,
we must rotate identities before they accumulate too much suspicion.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from crawler.stealth.fingerprint_profiles import FingerprintProfile, pick_profile

logger = logging.getLogger(__name__)


@dataclass
class Identity:
    """A unique browsing identity with usage tracking."""

    id: str
    fingerprint: FingerprintProfile
    proxy: Optional[str]
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    
    @property
    def is_contaminated(self) -> bool:
        """Check if identity has too many failures and should be rotated."""
        # If more than 50% failures, consider contaminated
        if self.request_count >= 2 and self.failure_count / self.request_count > 0.5:
            return True
        return False


class IdentityManager:
    """Manage identity creation and rotation based on usage limits."""

    def __init__(
        self,
        max_requests_per_identity: int = 4,
        enable_proxy_rotation: bool = False,
        proxy_list: Optional[list[str]] = None,
    ) -> None:
        """
        Args:
            max_requests_per_identity: Maximum requests before forcing rotation
            enable_proxy_rotation: Whether to rotate proxies with identities
            proxy_list: List of proxy servers to rotate through
        """
        self._max_requests = max_requests_per_identity
        self._enable_proxy = enable_proxy_rotation
        self._proxy_list = proxy_list or []
        self._proxy_index = 0
        
        self._current_identity: Optional[Identity] = None
        self._identity_history: list[Identity] = []

    def get_identity(self, force_new: bool = False) -> Identity:
        """Get current identity or create new one if needed.
        
        Args:
            force_new: Force creation of new identity even if current is valid
        
        Returns:
            Identity object with fingerprint and optional proxy
        """
        # Create new identity if:
        # 1. No current identity exists
        # 2. Current identity exceeded max requests
        # 3. Current identity is contaminated (too many failures)
        # 4. Forced rotation requested
        should_rotate = (
            self._current_identity is None
            or self._current_identity.request_count >= self._max_requests
            or self._current_identity.is_contaminated
            or force_new
        )
        
        if should_rotate:
            if self._current_identity:
                logger.info(
                    "identity_rotation",
                    extra={
                        "old_id": self._current_identity.id,
                        "requests": self._current_identity.request_count,
                        "successes": self._current_identity.success_count,
                        "failures": self._current_identity.failure_count,
                        "reason": (
                            "contaminated" if self._current_identity.is_contaminated
                            else "max_requests" if self._current_identity.request_count >= self._max_requests
                            else "forced"
                        ),
                    },
                )
                self._identity_history.append(self._current_identity)
            
            # Create new identity
            new_id = str(uuid.uuid4())[:8]
            new_fingerprint = pick_profile()
            new_proxy = self._get_next_proxy() if self._enable_proxy else None
            
            self._current_identity = Identity(
                id=new_id,
                fingerprint=new_fingerprint,
                proxy=new_proxy,
            )
            
            logger.info(
                "identity_created",
                extra={
                    "identity_id": new_id,
                    "platform": new_fingerprint.platform,
                    "proxy": new_proxy or "none",
                },
            )
        
        return self._current_identity

    def record_request(self, success: bool) -> None:
        """Record a request outcome for the current identity.
        
        Args:
            success: Whether the request succeeded
        """
        if self._current_identity is None:
            return
        
        self._current_identity.request_count += 1
        if success:
            self._current_identity.success_count += 1
        else:
            self._current_identity.failure_count += 1
        
        logger.debug(
            "identity_request_recorded",
            extra={
                "identity_id": self._current_identity.id,
                "total": self._current_identity.request_count,
                "success": success,
            },
        )

    def force_rotation(self) -> None:
        """Force immediate identity rotation on next get_identity() call."""
        if self._current_identity:
            # Mark as contaminated to trigger rotation
            self._current_identity.failure_count = self._current_identity.request_count

    def _get_next_proxy(self) -> Optional[str]:
        """Get next proxy from rotation pool."""
        if not self._proxy_list:
            return None
        
        proxy = self._proxy_list[self._proxy_index % len(self._proxy_list)]
        self._proxy_index += 1
        return proxy

    def get_statistics(self) -> dict:
        """Get overall statistics across all identities."""
        all_identities = self._identity_history + (
            [self._current_identity] if self._current_identity else []
        )
        
        total_requests = sum(i.request_count for i in all_identities)
        total_successes = sum(i.success_count for i in all_identities)
        total_failures = sum(i.failure_count for i in all_identities)
        
        return {
            "total_identities": len(all_identities),
            "total_requests": total_requests,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "success_rate": total_successes / total_requests if total_requests > 0 else 0.0,
            "avg_requests_per_identity": total_requests / len(all_identities) if all_identities else 0.0,
        }
