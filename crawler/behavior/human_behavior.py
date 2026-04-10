from __future__ import annotations

import logging
import random
import time
from typing import Any

logger = logging.getLogger(__name__)


def random_sleep(lo: float = 0.3, hi: float = 3.5) -> None:
    """Sleep for a random duration between lo and hi seconds."""
    duration = random.uniform(lo, hi)
    time.sleep(duration)


def human_scroll(page: Any, scroll_count: int = 0) -> None:
    """Simulate human-like scrolling behaviour on a Playwright page.

    If *scroll_count* is 0, a random count (1-6) is chosen.
    """
    if scroll_count <= 0:
        scroll_count = random.randint(1, 6)

    for _ in range(scroll_count):
        # Random scroll distance (150-800 px)
        distance = random.randint(150, 800)
        page.mouse.wheel(0, distance)
        random_sleep(0.2, 1.8)

    # Occasionally scroll back up a little
    if random.random() < 0.4:
        page.mouse.wheel(0, -random.randint(50, 300))
        random_sleep(0.1, 0.9)

    logger.debug("human_scroll", extra={"scroll_count": scroll_count})


def human_mouse_move(page: Any, count: int = 0) -> None:
    """Move the mouse cursor to random positions to simulate human activity."""
    if count <= 0:
        count = random.randint(1, 5)

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
    """Simulate a user reading a page: scroll, pause, maybe move mouse.
    
    🔥 Anti-Pattern Design:
    - Randomize behavior sequence to avoid ML detection
    - Skip actions probabilistically (real users don't always scroll/move mouse)
    - Variable dwell times based on 'reading speed'
    """
    # 🎲 Random behavior profile: fast reader vs slow reader
    is_fast_reader = random.random() < 0.3
    
    # Initial dwell time (varies by reader type)
    if is_fast_reader:
        random_sleep(0.5, 2.0)
    else:
        random_sleep(1.5, 5.0)
    
    # 🎲 Decide actions (not always the same sequence)
    will_scroll = random.random() < 0.85  # 85% chance
    will_mouse_move = random.random() < 0.4  # 40% chance
    scroll_before_mouse = random.random() < 0.6  # Variable order
    
    if scroll_before_mouse:
        if will_scroll:
            human_scroll(page, scroll_count=random.randint(1, 6) if not is_fast_reader else random.randint(1, 3))
        
        if will_mouse_move:
            # Sometimes wait between actions
            if random.random() < 0.5:
                random_sleep(0.3, 1.2)
            human_mouse_move(page, count=random.randint(1, 3))
    else:
        # Reverse order
        if will_mouse_move:
            human_mouse_move(page, count=random.randint(1, 3))
        
        if will_scroll:
            if random.random() < 0.5:
                random_sleep(0.3, 1.2)
            human_scroll(page, scroll_count=random.randint(1, 6) if not is_fast_reader else random.randint(1, 3))
    
    # Final dwell time (sometimes skip this entirely)
    if random.random() < 0.7:  # 70% chance
        if is_fast_reader:
            random_sleep(0.2, 1.0)
        else:
            random_sleep(0.5, 2.5)


def pre_navigation_delay() -> None:
    """Add a small delay before navigating to the next page.
    
    🔥 Anti-Pattern: Variable delay pattern, sometimes very short, sometimes long.
    Mimics real user behavior where they might click immediately or pause to think.
    """
    # 20% chance of immediate navigation (user knows what they want)
    if random.random() < 0.2:
        random_sleep(0.1, 0.5)
    # 60% chance of normal thinking time
    elif random.random() < 0.8:
        random_sleep(1.0, 3.0)
    # 20% chance of long pause (user is distracted/reading something)
    else:
        random_sleep(3.0, 8.0)


def simulate_idle_reading(page: Any) -> None:
    """Simulate user just reading without much interaction.
    
    Some users just read and don't scroll/move mouse much.
    This creates diversity in behavior patterns.
    """
    # Just dwell for reading time
    reading_time = random.uniform(2.0, 10.0)
    
    # Occasionally move mouse a tiny bit (like hand movements while reading)
    if random.random() < 0.3:
        viewport = page.viewport_size or {"width": 1280, "height": 720}
        # Small, natural movements
        for _ in range(random.randint(1, 2)):
            x = random.randint(int(viewport["width"] * 0.3), int(viewport["width"] * 0.7))
            y = random.randint(int(viewport["height"] * 0.3), int(viewport["height"] * 0.6))
            page.mouse.move(x, y, steps=random.randint(3, 8))
            random_sleep(reading_time / 4, reading_time / 2)
    else:
        # Just wait (reading without mouse movement)
        time.sleep(reading_time)
