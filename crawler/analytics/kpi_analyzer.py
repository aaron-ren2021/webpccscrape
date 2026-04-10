"""KPI analysis tool for anti-detection crawler performance.

Analyzes detection logs to provide insights into:
- Overall success rate
- Failure type distribution
- Proxy effectiveness
- Fingerprint effectiveness
- Strategy performance
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class KPIMetrics:
    """Key performance indicators for crawler runs."""

    total_requests: int = 0
    successful_requests: int = 0
    
    # Failure breakdown
    captcha_count: int = 0
    hard_block_count: int = 0
    access_denied_count: int = 0
    soft_block_count: int = 0
    rate_limited_count: int = 0
    cloudflare_challenge_count: int = 0
    timeout_count: int = 0
    empty_content_count: int = 0
    redirect_challenge_count: int = 0
    unknown_failure_count: int = 0
    
    # Performance by proxy
    proxy_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    
    # Performance by fingerprint platform
    platform_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    
    # Performance by strategy (if logged)
    strategy_stats: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Overall success rate as a percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def terminal_failure_rate(self) -> float:
        """Rate of terminal failures (CAPTCHA, HARD_BLOCK, ACCESS_DENIED)."""
        if self.total_requests == 0:
            return 0.0
        terminal = self.captcha_count + self.hard_block_count + self.access_denied_count
        return (terminal / self.total_requests) * 100

    @property
    def recoverable_failure_rate(self) -> float:
        """Rate of recoverable failures (RATE_LIMITED, CLOUDFLARE, SOFT_BLOCK)."""
        if self.total_requests == 0:
            return 0.0
        recoverable = (
            self.rate_limited_count
            + self.cloudflare_challenge_count
            + self.soft_block_count
        )
        return (recoverable / self.total_requests) * 100

    def get_proxy_success_rate(self, proxy: str) -> float:
        """Get success rate for a specific proxy."""
        if proxy not in self.proxy_stats:
            return 0.0
        stats = self.proxy_stats[proxy]
        total = stats.get("total", 0)
        success = stats.get("success", 0)
        if total == 0:
            return 0.0
        return (success / total) * 100

    def get_platform_success_rate(self, platform: str) -> float:
        """Get success rate for a specific fingerprint platform."""
        if platform not in self.platform_stats:
            return 0.0
        stats = self.platform_stats[platform]
        total = stats.get("total", 0)
        success = stats.get("success", 0)
        if total == 0:
            return 0.0
        return (success / total) * 100

    def get_strategy_success_rate(self, strategy: str) -> float:
        """Get success rate for a specific crawl strategy."""
        if strategy not in self.strategy_stats:
            return 0.0
        stats = self.strategy_stats[strategy]
        total = stats.get("total", 0)
        success = stats.get("success", 0)
        if total == 0:
            return 0.0
        return (success / total) * 100


class KPIAnalyzer:
    """Analyze detection logger events to generate KPI metrics."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def load_events_from_logger(self, detection_logger: Any) -> None:
        """Load events from a DetectionLogger instance."""
        self._events = detection_logger.events

    def load_events_from_json(self, file_path: str | Path) -> None:
        """Load events from a JSON file containing log events."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {file_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                self._events = data
            elif isinstance(data, dict) and "events" in data:
                self._events = data["events"]
            else:
                raise ValueError("Invalid JSON format. Expected list of events or dict with 'events' key.")

    def analyze(self) -> KPIMetrics:
        """Analyze loaded events and return KPI metrics."""
        metrics = KPIMetrics()
        
        for event in self._events:
            outcome = event.get("outcome", "unknown_failure")
            proxy = event.get("proxy", "").strip() or "no_proxy"
            user_agent = event.get("user_agent", "")
            
            # Extract platform from user_agent or other fields
            platform = self._extract_platform(user_agent, event)
            
            # Extract strategy if available
            strategy = event.get("strategy", "unknown")
            
            metrics.total_requests += 1
            
            # Count by outcome
            if outcome == "success":
                metrics.successful_requests += 1
            elif outcome == "captcha":
                metrics.captcha_count += 1
            elif outcome == "hard_block":
                metrics.hard_block_count += 1
            elif outcome == "access_denied":
                metrics.access_denied_count += 1
            elif outcome == "soft_block":
                metrics.soft_block_count += 1
            elif outcome == "rate_limited":
                metrics.rate_limited_count += 1
            elif outcome == "cloudflare_challenge":
                metrics.cloudflare_challenge_count += 1
            elif outcome == "timeout":
                metrics.timeout_count += 1
            elif outcome == "empty_content":
                metrics.empty_content_count += 1
            elif outcome == "redirect_challenge":
                metrics.redirect_challenge_count += 1
            else:
                metrics.unknown_failure_count += 1
            
            # Track proxy stats
            if proxy not in metrics.proxy_stats:
                metrics.proxy_stats[proxy] = {"total": 0, "success": 0}
            metrics.proxy_stats[proxy]["total"] += 1
            if outcome == "success":
                metrics.proxy_stats[proxy]["success"] += 1
            
            # Track platform stats
            if platform not in metrics.platform_stats:
                metrics.platform_stats[platform] = {"total": 0, "success": 0}
            metrics.platform_stats[platform]["total"] += 1
            if outcome == "success":
                metrics.platform_stats[platform]["success"] += 1
            
            # Track strategy stats
            if strategy not in metrics.strategy_stats:
                metrics.strategy_stats[strategy] = {"total": 0, "success": 0}
            metrics.strategy_stats[strategy]["total"] += 1
            if outcome == "success":
                metrics.strategy_stats[strategy]["success"] += 1
        
        return metrics

    def _extract_platform(self, user_agent: str, event: dict[str, Any]) -> str:
        """Extract platform identifier from user agent or event metadata."""
        # Try to extract from user agent
        ua_lower = user_agent.lower()
        
        if "windows" in ua_lower or "win32" in ua_lower:
            return "Windows"
        elif "macintosh" in ua_lower or "macintel" in ua_lower:
            return "Mac"
        elif "linux" in ua_lower or "x11" in ua_lower:
            return "Linux"
        
        # Fallback to "unknown"
        return "unknown"

    def generate_report(self, metrics: KPIMetrics) -> str:
        """Generate a human-readable text report from metrics."""
        lines = [
            "=" * 70,
            "KPI Analysis Report",
            "=" * 70,
            "",
            f"Total Requests: {metrics.total_requests}",
            f"Successful: {metrics.successful_requests} ({metrics.success_rate:.1f}%)",
            "",
            "Failure Breakdown:",
            f"  Terminal Failures ({metrics.terminal_failure_rate:.1f}%):",
            f"    - CAPTCHA: {metrics.captcha_count}",
            f"    - Hard Block: {metrics.hard_block_count}",
            f"    - Access Denied: {metrics.access_denied_count}",
            "",
            f"  Recoverable Failures ({metrics.recoverable_failure_rate:.1f}%):",
            f"    - Rate Limited: {metrics.rate_limited_count}",
            f"    - Cloudflare Challenge: {metrics.cloudflare_challenge_count}",
            f"    - Soft Block: {metrics.soft_block_count}",
            "",
            f"  Other Failures:",
            f"    - Timeout: {metrics.timeout_count}",
            f"    - Empty Content: {metrics.empty_content_count}",
            f"    - Redirect Challenge: {metrics.redirect_challenge_count}",
            f"    - Unknown: {metrics.unknown_failure_count}",
            "",
        ]
        
        # Proxy performance
        if metrics.proxy_stats:
            lines.append("Proxy Performance:")
            for proxy, stats in sorted(
                metrics.proxy_stats.items(),
                key=lambda x: x[1]["success"] / max(x[1]["total"], 1),
                reverse=True,
            ):
                rate = metrics.get_proxy_success_rate(proxy)
                total = stats["total"]
                success = stats["success"]
                lines.append(f"  {proxy}: {success}/{total} ({rate:.1f}%)")
            lines.append("")
        
        # Platform performance
        if metrics.platform_stats:
            lines.append("Platform Performance:")
            for platform, stats in sorted(
                metrics.platform_stats.items(),
                key=lambda x: x[1]["success"] / max(x[1]["total"], 1),
                reverse=True,
            ):
                rate = metrics.get_platform_success_rate(platform)
                total = stats["total"]
                success = stats["success"]
                lines.append(f"  {platform}: {success}/{total} ({rate:.1f}%)")
            lines.append("")
        
        # Strategy performance
        if metrics.strategy_stats:
            lines.append("Strategy Performance:")
            for strategy, stats in sorted(
                metrics.strategy_stats.items(),
                key=lambda x: x[1]["success"] / max(x[1]["total"], 1),
                reverse=True,
            ):
                rate = metrics.get_strategy_success_rate(strategy)
                total = stats["total"]
                success = stats["success"]
                lines.append(f"  {strategy}: {success}/{total} ({rate:.1f}%)")
            lines.append("")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)

    def export_metrics_json(self, metrics: KPIMetrics, output_path: str | Path) -> None:
        """Export metrics to a JSON file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "total_requests": metrics.total_requests,
            "successful_requests": metrics.successful_requests,
            "success_rate": metrics.success_rate,
            "terminal_failure_rate": metrics.terminal_failure_rate,
            "recoverable_failure_rate": metrics.recoverable_failure_rate,
            "failure_breakdown": {
                "captcha": metrics.captcha_count,
                "hard_block": metrics.hard_block_count,
                "access_denied": metrics.access_denied_count,
                "soft_block": metrics.soft_block_count,
                "rate_limited": metrics.rate_limited_count,
                "cloudflare_challenge": metrics.cloudflare_challenge_count,
                "timeout": metrics.timeout_count,
                "empty_content": metrics.empty_content_count,
                "redirect_challenge": metrics.redirect_challenge_count,
                "unknown": metrics.unknown_failure_count,
            },
            "proxy_stats": metrics.proxy_stats,
            "platform_stats": metrics.platform_stats,
            "strategy_stats": metrics.strategy_stats,
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info("metrics_exported", extra={"path": str(path)})


def quick_analyze(detection_logger: Any) -> str:
    """Quick analysis helper - analyze a DetectionLogger and return a report."""
    analyzer = KPIAnalyzer()
    analyzer.load_events_from_logger(detection_logger)
    metrics = analyzer.analyze()
    return analyzer.generate_report(metrics)
