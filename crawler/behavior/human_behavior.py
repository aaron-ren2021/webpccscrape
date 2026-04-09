from __future__ import annotations

import logging
import random
import time
from typing import Any

logger = logging.getLogger(__name__)


def random_sleep(lo: float = 0.5, hi: float = 2.5) -> None:
    """Sleep for a random duration between lo and hi seconds."""
    duration = random.uniform(lo, hi)
    time.sleep(duration)


def human_scroll(page: Any, scroll_count: int = 0) -> None:
    """Simulate human-like scrolling behaviour on a Playwright page.

    If *scroll_count* is 0, a random count (1-4) is chosen.
    """
    if scroll_count <= 0:
        scroll_count = random.randint(1, 4)

    for _ in range(scroll_count):
        # Random scroll distance (200-600 px)
        distance = random.randint(200, 600)
        page.mouse.wheel(0, distance)
        random_sleep(0.3, 1.2)

    # Occasionally scroll back up a little
    if random.random() < 0.3:
        page.mouse.wheel(0, -random.randint(80, 200))
        random_sleep(0.2, 0.6)

    logger.debug("human_scroll", extra={"scroll_count": scroll_count})


def human_mouse_move(page: Any, count: int = 0) -> None:
    """Move the mouse cursor to random positions to simulate human activity."""
    if count <= 0:
        count = random.randint(1, 3)

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    w, h = viewport["width"], viewport["height"]

    for _ in range(count):
        x = random.randint(int(w * 0.1), int(w * 0.9))
        y = random.randint(int(h * 0.1), int(h * 0.7))
        # step count for natural movement curve
        steps = random.randint(5, 15)
        page.mouse.move(x, y, steps=steps)
        random_sleep(0.1, 0.5)

    logger.debug("human_mouse_move", extra={"count": count})


def human_hover_and_click(page: Any, selector: str, timeout: int = 5000) -> None:
    """Hover over an element briefly, then click it — mimicking a real user."""
    element = page.wait_for_selector(selector, timeout=timeout)
    if element is None:
        return

    # Move to element with slight offset
    box = element.bounding_box()
    if box:
        offset_x = random.randint(-3, 3)
        offset_y = random.randint(-3, 3)
        page.mouse.move(
            box["x"] + box["width"] / 2 + offset_x,
            box["y"] + box["height"] / 2 + offset_y,
            steps=random.randint(5, 12),
        )
    random_sleep(0.2, 0.8)
    element.click()
    random_sleep(0.3, 1.0)


def simulate_page_read(page: Any) -> None:
    """Simulate a user reading a page: scroll, pause, maybe move mouse."""
    # Initial dwell time — as if reading the top of the page
    random_sleep(1.0, 3.0)

    human_scroll(page)

    if random.random() < 0.4:
        human_mouse_move(page)

    # Final dwell time
    random_sleep(0.5, 1.5)


def pre_navigation_delay() -> None:
    """Add a small delay before navigating to the next page."""
    random_sleep(0.5, 2.0)
