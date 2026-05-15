"""
Latency Profiler - p50 / p95 / p99 / max percentile analysis.

Measures add() and rag() latencies at operation level, computes
percentile distributions, and detects tail-latency spikes.
"""

import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

import numpy as np

from omem import OMem


@dataclass
class LatencyResult:
    """Percentile breakdown for a single operation type."""

    operation: str
    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    p999_ms: float
    max_ms: float
    min_ms: float
    mean_ms: float
    stddev_ms: float
    throughput_ops: float  # operations per second
    raw_ms: List[float] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw_ms", None)
        return d


def _percentile(data: List[float], p: float) -> float:
    """Compute the p-th percentile of a sorted list."""
    if not data:
        return 0.0
    k = (len(data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(data):
        return data[-1]
    return data[f] + (k - f) * (data[c] - data[f])


def _build_result(
    operation: str, latencies_ms: List[float], total_time: float
) -> LatencyResult:
    s = sorted(latencies_ms)
    return LatencyResult(
        operation=operation,
        count=len(s),
        p50_ms=_percentile(s, 50),
        p95_ms=_percentile(s, 95),
        p99_ms=_percentile(s, 99),
        p999_ms=_percentile(s, 99.9),
        max_ms=s[-1] if s else 0.0,
        min_ms=s[0] if s else 0.0,
        mean_ms=statistics.mean(s) if s else 0.0,
        stddev_ms=statistics.stdev(s) if len(s) > 1 else 0.0,
        throughput_ops=len(s) / total_time if total_time > 0 else 0.0,
        raw_ms=s,
    )


def profile_add_latency(
    n: int = 10_000, db_path: Optional[str] = None
) -> LatencyResult:
    """Profile individual add() call latencies."""
    m = OMem(db_path=db_path)
    latencies: List[float] = []

    wall_start = time.perf_counter()
    for i in range(n):
        content = f"Production memory entry #{i}: contextual data about domain {i % 100} topic {i % 50} user-segment {i % 20}"
        t0 = time.perf_counter()
        m.add(content)
        latencies.append((time.perf_counter() - t0) * 1000)
    wall_total = time.perf_counter() - wall_start

    return _build_result("add", latencies, wall_total)


def profile_rag_latency(
    n_memories: int = 10_000,
    n_queries: int = 1_000,
    top_k: int = 5,
    db_path: Optional[str] = None,
) -> LatencyResult:
    """Profile individual rag() call latencies."""
    m = OMem(db_path=db_path)

    # Seed memories
    for i in range(n_memories):
        m.add(
            f"Memory #{i}: domain {i % 100} topic {i % 50} segment {i % 20} context {i % 200}"
        )

    # Diverse query set
    queries = [f"domain {i % 100} topic {i % 50}" for i in range(n_queries)]

    latencies: List[float] = []
    wall_start = time.perf_counter()
    for q in queries:
        t0 = time.perf_counter()
        m.recall(q, top_k=top_k)
        latencies.append((time.perf_counter() - t0) * 1000)
    wall_total = time.perf_counter() - wall_start

    return _build_result("rag", latencies, wall_total)


def profile_mixed_workload(
    n: int = 10_000,
    read_write_ratio: float = 0.7,
    db_path: Optional[str] = None,
) -> Dict[str, LatencyResult]:
    """Simulate a mixed read/write workload (default 70% reads, 30% writes)."""
    m = OMem(db_path=db_path)

    # Pre-seed some data
    for i in range(1000):
        m.add(f"Seed memory {i}: topic {i % 30}")

    rng = np.random.default_rng(42)
    add_latencies: List[float] = []
    rag_latencies: List[float] = []

    wall_start = time.perf_counter()
    for i in range(n):
        if rng.random() < read_write_ratio:
            t0 = time.perf_counter()
            m.recall(f"topic {rng.integers(0, 30)}", top_k=5)
            rag_latencies.append((time.perf_counter() - t0) * 1000)
        else:
            t0 = time.perf_counter()
            m.add(f"Mixed workload memory {i}: data {rng.integers(0, 1000)}")
            add_latencies.append((time.perf_counter() - t0) * 1000)
    wall_total = time.perf_counter() - wall_start

    return {
        "mixed_add": _build_result("mixed_add", add_latencies, wall_total),
        "mixed_rag": _build_result("mixed_rag", rag_latencies, wall_total),
    }


def run_latency_profile(
    n: int = 10_000, verbose: bool = True
) -> Dict[str, LatencyResult]:
    """Run the full latency profiling suite."""
    results: Dict[str, LatencyResult] = {}

    if verbose:
        print("=" * 70)
        print("  OMem Latency Profiler - Production Percentile Analysis")
        print("=" * 70)

    # 1. Add latency
    if verbose:
        print(f"\n> Profiling add() with {n:,} operations...")
    results["add"] = profile_add_latency(n)

    # 2. RAG latency
    n_queries = min(n, 2000)
    if verbose:
        print(f"> Profiling rag() with {n:,} memories, {n_queries:,} queries...")
    results["rag"] = profile_rag_latency(n, n_queries)

    # 3. Mixed workload
    if verbose:
        print(f"> Profiling mixed workload (70/30 read/write, {n:,} ops)...")
    mixed = profile_mixed_workload(n)
    results.update(mixed)

    if verbose:
        print("\n" + "-" * 70)
        _print_table(results)

    return results


def _print_table(results: Dict[str, LatencyResult]) -> None:
    header = f"{'Operation':<14} {'Count':>7} {'p50':>8} {'p95':>8} {'p99':>8} {'p99.9':>8} {'max':>8} {'mean':>8} {'s':>8} {'ops/s':>10}"
    print(header)
    print("-" * len(header))
    for r in results.values():
        print(
            f"{r.operation:<14} {r.count:>7,} {r.p50_ms:>7.3f}ms {r.p95_ms:>7.3f}ms "
            f"{r.p99_ms:>7.3f}ms {r.p999_ms:>7.3f}ms {r.max_ms:>7.3f}ms "
            f"{r.mean_ms:>7.3f}ms {r.stddev_ms:>7.3f}ms {r.throughput_ops:>9,.0f}"
        )


if __name__ == "__main__":
    run_latency_profile(n=10_000)
