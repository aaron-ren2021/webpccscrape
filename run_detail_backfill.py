from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from core.config import Settings
from core.detail_backfill import run_detail_backfill


def main() -> int:
    parser = argparse.ArgumentParser(description="Run background bid detail backfill.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum queued records to process.")
    parser.add_argument(
        "--source",
        default="gov_pcc,g0v",
        help="Comma-separated sources to process, e.g. gov_pcc or g0v.",
    )
    parser.add_argument("--dry-run", action="store_true", help="List queued work without fetching details.")
    args = parser.parse_args()

    load_dotenv(override=False)

    class _ExtraFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            text = super().format(record)
            standard = logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
            extras = {k: v for k, v in record.__dict__.items() if k not in standard and k != "message"}
            if extras:
                text += " " + " ".join(f"{k}={v}" for k, v in extras.items())
            return text

    handler = logging.StreamHandler()
    handler.setFormatter(_ExtraFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    Path("logs").mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler("logs/cron.log")
    file_handler.setFormatter(_ExtraFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(file_handler)

    logger = logging.getLogger("bid-detail-backfill")
    settings = Settings.from_env()
    sources = {item.strip() for item in args.source.split(",") if item.strip()}

    result = run_detail_backfill(
        settings=settings,
        logger=logger,
        limit=args.limit,
        sources=sources or None,
        dry_run=args.dry_run,
    )
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
