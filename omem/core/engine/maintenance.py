"""Background Maintenance Engine - handles throttled memory cleanup."""

import time
import threading
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class MaintenanceEngine:
    """Orchestrates periodic cleanup tasks in a background thread.

    Prevents maintenance spikes from impacting real-time RAG performance.
    """

    def __init__(self, engine, interval: float = 3600.0, speed: str = "normal"):
        self.engine = engine
        self.interval = interval
        self.speed = speed
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_run = time.time()

        # Speed profiles
        self.profiles = {
            "fast": {"batch_sleep": 0.01, "cycle_sleep": 10.0},
            "normal": {"batch_sleep": 0.1, "cycle_sleep": 60.0},
            "thorough": {"batch_sleep": 0.5, "cycle_sleep": 300.0},
        }

    def start(self):
        """Start the background maintenance loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="omem-maintenance"
        )
        self._thread.start()
        logger.info("Maintenance engine started (interval=%.0fs)", self.interval)

    def stop(self):
        """Stop the background maintenance loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def trigger_sleep(
        self, speed: Optional[str] = None, llm_fn: Optional[Callable] = None
    ):
        """Manually trigger a full maintenance cycle."""
        speed = speed or self.speed
        self.profiles.get(speed, self.profiles["normal"])

        logger.info("Triggering maintenance sleep (speed=%s)...", speed)
        result = self.engine.sleep(speed=speed, llm_fn=llm_fn)
        self._last_run = time.time()
        return result

    def _worker(self):
        """Background loop that periodically triggers maintenance with exponential backoff."""
        _consecutive_failures = 0
        while self._running:
            now = time.time()
            if now - self._last_run >= self.interval:
                try:
                    self.engine.sleep(speed="normal", include_dream=True)
                    self._last_run = time.time()
                    _consecutive_failures = 0
                except Exception as e:
                    _consecutive_failures += 1
                    backoff = min(60 * (2 ** _consecutive_failures), 3600)
                    logger.error(
                        "Background maintenance failed (failures=%d, retry_in=%ds): %s",
                        _consecutive_failures,
                        backoff,
                        e,
                        exc_info=True,
                    )
                    slept = 0
                    while slept < backoff and self._running:
                        time.sleep(1.0)
                        slept += 1
                    continue

            # Check every minute
            time.sleep(60.0)
