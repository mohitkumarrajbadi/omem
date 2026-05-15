"""Circuit breaker: CLOSED/OPEN/HALF_OPEN state machine."""

import time
import threading
import logging
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    def __init__(self, name):
        super().__init__(f"Circuit '{name}' is OPEN — call rejected")
        self.circuit_name = name


class CircuitBreaker:
    def __init__(
        self,
        name,
        failure_threshold=5,
        recovery_timeout=30.0,
        success_threshold=1,
        window_seconds=60.0,
    ):
        self.name = name
        self._ft = failure_threshold
        self._rt = recovery_timeout
        self._st = success_threshold
        self._ws = window_seconds
        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()
        self._failure_ts: list = []
        self._opened_at = 0.0
        self._half_open_successes = 0

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        with self._lock:
            state = self._get_state()
        if state == CircuitState.OPEN:
            raise CircuitOpenError(self.name)
        try:
            result = fn(*args, **kwargs)
            with self._lock:
                self._on_success()
            return result
        except Exception:
            with self._lock:
                self._on_failure()
            raise

    def _get_state(self):
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self._rt:
                self._state = CircuitState.HALF_OPEN
                self._half_open_successes = 0
                logger.info("Circuit '%s' → HALF_OPEN", self.name)
        return self._state

    def _on_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self._st:
                self._state = CircuitState.CLOSED
                self._failure_ts.clear()
                logger.info("Circuit '%s' → CLOSED (recovered)", self.name)

    def _on_failure(self):
        now = time.monotonic()
        self._failure_ts = [t for t in self._failure_ts if t > now - self._ws]
        self._failure_ts.append(now)
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = now
            logger.warning("Circuit '%s' → OPEN (failed in HALF_OPEN)", self.name)
        elif self._state == CircuitState.CLOSED:
            if len(self._failure_ts) >= self._ft:
                self._state = CircuitState.OPEN
                self._opened_at = now
                logger.error(
                    "Circuit '%s' → OPEN (%d failures in %.0fs)",
                    self.name,
                    len(self._failure_ts),
                    self._ws,
                )

    @property
    def state(self):
        return self._state

    @property
    def failure_count(self):
        return len(self._failure_ts)
