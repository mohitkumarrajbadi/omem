"""Production metrics collector — lightweight observability.

Tracks: p50/p99 latency, operation counts, cache hit rates,
memory growth, and throughput. No external dependencies.

v0.5.0 Production hardening (H).
"""

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List
from collections import defaultdict

logger = logging.getLogger(__name__)

# Keep last N samples per operation
_MAX_SAMPLES = 1000


@dataclass
class OperationMetrics:
    """Metrics for a single operation type."""

    count: int = 0
    total_time_ms: float = 0.0
    samples: List[float] = field(default_factory=list)
    errors: int = 0

    def record(self, elapsed_ms: float) -> None:
        self.count += 1
        self.total_time_ms += elapsed_ms
        self.samples.append(elapsed_ms)
        if len(self.samples) > _MAX_SAMPLES:
            self.samples = self.samples[-_MAX_SAMPLES:]

    def percentile(self, p: float) -> float:
        if not self.samples:
            return 0.0
        sorted_s = sorted(self.samples)
        idx = int(len(sorted_s) * p / 100)
        return sorted_s[min(idx, len(sorted_s) - 1)]

    @property
    def p50(self) -> float:
        return self.percentile(50)

    @property
    def p99(self) -> float:
        return self.percentile(99)

    @property
    def avg(self) -> float:
        return self.total_time_ms / max(self.count, 1)


class MetricsCollector:
    """Global metrics collector for OMem operations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ops: Dict[str, OperationMetrics] = defaultdict(OperationMetrics)
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._start_time = time.time()

    def timer(self, operation: str) -> "Timer":
        """Context manager for timing operations.

        Usage::

            with metrics.timer("rag") as t:
                results = engine.rag(query)
        """
        return Timer(self, operation)

    def record_latency(self, operation: str, elapsed_ms: float) -> None:
        """Manually record a latency sample."""
        with self._lock:
            self._ops[operation].record(elapsed_ms)

    def record_error(self, operation: str) -> None:
        """Record an error for an operation."""
        with self._lock:
            self._ops[operation].errors += 1

    def increment(self, counter: str, amount: int = 1) -> None:
        """Increment a counter (memory_added, cache_hits, etc.)."""
        with self._lock:
            self._counters[counter] += amount

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value (memory_count, index_size, etc.)."""
        with self._lock:
            self._gauges[name] = value

    def get_stats(self) -> Dict:
        """Return all metrics as a dict."""
        with self._lock:
            uptime = time.time() - self._start_time
            ops = {}
            for name, m in self._ops.items():
                ops[name] = {
                    "count": m.count,
                    "p50_ms": round(m.p50, 3),
                    "p99_ms": round(m.p99, 3),
                    "avg_ms": round(m.avg, 3),
                    "errors": m.errors,
                }

            return {
                "uptime_s": round(uptime, 1),
                "operations": ops,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._ops.clear()
            self._counters.clear()
            self._gauges.clear()
            self._start_time = time.time()


class Timer:
    """Context manager for timing operations."""

    def __init__(self, collector: MetricsCollector, operation: str):
        self._collector = collector
        self._operation = operation
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.time()
        return self

    def __exit__(self, *args) -> None:
        self.elapsed_ms = (time.time() - self._start) * 1000
        self._collector.record_latency(self._operation, self.elapsed_ms)


# Global metrics instance
metrics = MetricsCollector()
