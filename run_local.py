from __future__ import annotations

import argparse
import logging

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

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
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
    logger.info("local_run_finished", extra={"result": result.to_dict()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
