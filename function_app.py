from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import azure.functions as func
from dotenv import load_dotenv

from core.config import Settings
from core.pipeline import run_monitor

load_dotenv(override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("bid-monitor")

app = func.FunctionApp()


@app.function_name(name="daily_bid_monitor")
@app.timer_trigger(
    arg_name="timer",
    schedule="0 30 0 * * *",  # UTC 00:30 = Asia/Taipei 08:30
    run_on_startup=False,
    use_monitor=True,
)
def daily_bid_monitor(timer: func.TimerRequest) -> None:
    settings = Settings.from_env()
    now_tw = datetime.now(ZoneInfo(settings.timezone))
    logger.info(
        "timer_trigger_started",
        extra={
            "is_past_due": bool(timer.past_due),
            "run_at_tw": now_tw.isoformat(),
        },
    )
    result = run_monitor(settings=settings, logger=logger, persist_state=True)
    logger.info("timer_trigger_finished", extra={"result": result.to_dict()})
