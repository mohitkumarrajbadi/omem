"""End-to-end recall latency SLO gate.

Charter target: P95 retrieval latency < 10ms (in-process, k<=10, N<=5k).

Usage::

    python -m benchmarks.slo_recall_latency
    # or pytest tests/test_memory_os_phases.py -k slo
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

from omem import OMem


@dataclass
class SLOReport:
    n_memories: int
    n_queries: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    passed: bool
    threshold_p95_ms: float = 10.0

    def as_dict(self) -> dict:
        return {
            "n_memories": self.n_memories,
            "n_queries": self.n_queries,
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
            "threshold_p95_ms": self.threshold_p95_ms,
            "passed": self.passed,
        }


def _pct(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (k - f) * (s[c] - s[f])


def run_recall_slo(
    *,
    n_memories: int = 500,
    n_queries: int = 100,
    k: int = 5,
    threshold_p95_ms: float = 10.0,
    warmup: int = 5,
) -> SLOReport:
    """Build a corpus, warm the cache, time recall(), return SLO report."""
    brain = OMem()
    for i in range(n_memories):
        brain.add(
            f"Memory {i}: decision about PostgreSQL SCRAM upgrade and pool limits "
            f"incident response for service AuthAPI project omem-{i % 7}",
            force=True,
        )

    queries = [
        "PostgreSQL SCRAM upgrade",
        "pool limits incident",
        "AuthAPI service",
        "decision database",
        "omem project workflow",
    ]
    # Warmup
    for i in range(warmup):
        brain.recall(queries[i % len(queries)], k=k)

    latencies: List[float] = []
    for i in range(n_queries):
        q = queries[i % len(queries)]
        t0 = time.perf_counter()
        brain.recall(q, k=k)
        latencies.append((time.perf_counter() - t0) * 1000.0)

    p95 = _pct(latencies, 95)
    return SLOReport(
        n_memories=n_memories,
        n_queries=n_queries,
        p50_ms=_pct(latencies, 50),
        p95_ms=p95,
        p99_ms=_pct(latencies, 99),
        passed=p95 < threshold_p95_ms,
        threshold_p95_ms=threshold_p95_ms,
    )


def main() -> None:
    report = run_recall_slo()
    print(report.as_dict())
    if not report.passed:
        raise SystemExit(
            f"SLO FAIL: p95={report.p95_ms:.2f}ms >= {report.threshold_p95_ms}ms"
        )
    print("SLO PASS")


if __name__ == "__main__":
    main()
