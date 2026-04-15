from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from core.config import Settings
from core.pipeline import run_monitor


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bid monitor in local mode.")
    parser.add_argument("--no-send", action="store_true", help="Do not actually send emails.")
    parser.add_argument(
        "--preview-html",
        default="",
        help="Write rendered email HTML to a local file path.",
    )
    parser.add_argument(
        "--no-persist-state",
        action="store_true",
        help="Do not write notified state to storage.",
    )
    args = parser.parse_args()

    load_dotenv(override=False)

    class _ExtraFormatter(logging.Formatter):
        """Append extra dict fields (if any) after the log message."""
        def format(self, record: logging.LogRecord) -> str:
            s = super().format(record)
            # Collect extra keys that are not standard LogRecord attributes
            _STANDARD = logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
            extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD and k != "message"}
            if extras:
                s += " " + " ".join(f"{k}={v}" for k, v in extras.items())
            return s

    handler = logging.StreamHandler()
    handler.setFormatter(_ExtraFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # Also log to file for local debugging.
    Path("logs").mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler("logs/cron.log")
    file_handler.setFormatter(_ExtraFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(file_handler)
    logger = logging.getLogger("bid-monitor-local")

    settings = Settings.from_env()
    if args.no_send:
        settings.dry_run = True
    if args.preview_html:
        settings.preview_html_path = args.preview_html

    result = run_monitor(
        settings=settings,
        logger=logger,
        persist_state=not args.no_persist_state,
    )
    result_dict = result.to_dict()
    source_success = sum(1 for s in result.source_status if s.success)
    source_failed = len(result.source_status) - source_success
    logger.info(
        "local_run_finished",
        extra={
            "result": result_dict,
            "crawled_count": result.crawled_count,
            "filtered_count": result.filtered_count,
            "deduped_count": result.deduped_count,
            "new_count": result.new_count,
            "notification_sent": result.notification_sent,
            "notification_backend": result.notification_backend,
            "error_count": len(result.errors),
            "source_success_count": source_success,
            "source_failed_count": source_failed,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
