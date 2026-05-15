"""
Scalability Benchmark - measure how OMem performance degrades at scale.

Tests add() and rag() at increasing dataset sizes (1K -> 10K -> 50K -> 100K -> 500K)
to produce scaling curves showing throughput and latency trends.
"""

import time
from dataclasses import dataclass
from typing import List, Optional

from omem import OMem


@dataclass
class ScalePoint:
    """Performance at a specific dataset size."""

    n_memories: int
    add_total_s: float
    add_per_ms: float
    rag_total_s: float
    rag_per_ms: float
    rag_p95_ms: float
    rag_p99_ms: float
    memory_mb: float  # approximate RSS delta


def _measure_rag_latencies(
    m: OMem, n_queries: int = 500, top_k: int = 5
) -> List[float]:
    """Return list of per-query latencies in ms."""
    latencies = []
    for i in range(n_queries):
        q = f"domain {i % 100} topic {i % 50}"
        t0 = time.perf_counter()
        m.recall(q, top_k=top_k)
        latencies.append((time.perf_counter() - t0) * 1000)
    return latencies


def _get_rss_mb() -> float:
    """Get current process RSS in MB (best-effort)."""
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
            1024 * 1024
        )  # macOS: bytes
    except Exception:
        try:
            import psutil

            return psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0


def run_scalability_test(
    scales: Optional[List[int]] = None,
    n_queries: int = 500,
    verbose: bool = True,
) -> List[ScalePoint]:
    """Run scaling curve benchmark at multiple dataset sizes."""
    if scales is None:
        scales = [1_000, 5_000, 10_000, 50_000, 100_000]

    results: List[ScalePoint] = []

    if verbose:
        print("=" * 80)
        print("  OMem Scalability Benchmark - Scaling Curve Analysis")
        print("=" * 80)

    for n in scales:
        if verbose:
            print(f"\n> Scale: {n:>8,} memories")

        m = OMem()
        rss_before = _get_rss_mb()

        # ---- Insert ----
        t0 = time.perf_counter()
        for i in range(n):
            m.add(
                f"Scalability entry {i}: domain {i % 100} topic {i % 50} context {i % 200} extra {i % 500}"
            )
        add_total = time.perf_counter() - t0

        rss_after = _get_rss_mb()

        # ---- RAG ----
        latencies = _measure_rag_latencies(m, n_queries)
        rag_total = sum(latencies) / 1000.0
        sorted_lat = sorted(latencies)
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0.0
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if sorted_lat else 0.0

        point = ScalePoint(
            n_memories=n,
            add_total_s=add_total,
            add_per_ms=(add_total / n) * 1000,
            rag_total_s=rag_total,
            rag_per_ms=(rag_total / n_queries) * 1000,
            rag_p95_ms=p95,
            rag_p99_ms=p99,
            memory_mb=max(rss_after - rss_before, 0.0),
        )
        results.append(point)

        if verbose:
            print(f"  Add: {add_total:.3f}s total, {point.add_per_ms:.3f}ms/op")
            print(
                f"  RAG: {point.rag_per_ms:.3f}ms/query, p95={p95:.3f}ms, p99={p99:.3f}ms"
            )
            print(f"  Memory delta: ~{point.memory_mb:.1f} MB")

        # Cleanup
        del m

    if verbose:
        print("\n" + "-" * 80)
        _print_scaling_table(results)

    return results


def _print_scaling_table(results: List[ScalePoint]) -> None:
    header = (
        f"{'N':>10} | {'Add/op':>9} {'Add tot':>9} | "
        f"{'RAG/q':>9} {'p95':>9} {'p99':>9} | {'Mem MB':>8}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.n_memories:>10,} | {r.add_per_ms:>8.3f}ms {r.add_total_s:>8.2f}s | "
            f"{r.rag_per_ms:>8.3f}ms {r.rag_p95_ms:>8.3f}ms {r.rag_p99_ms:>8.3f}ms | "
            f"{r.memory_mb:>7.1f}MB"
        )

    # Scaling factor analysis
    if len(results) >= 2:
        first, last = results[0], results[-1]
        scale_factor = last.n_memories / first.n_memories
        rag_degradation = (
            last.rag_per_ms / first.rag_per_ms if first.rag_per_ms > 0 else 0
        )
        print(
            f"\nScale factor: {scale_factor:.0f}x data -> {rag_degradation:.1f}x RAG latency"
        )
        if rag_degradation < scale_factor * 0.5:
            print("   [OK] Sub-linear scaling - production ready!")
        elif rag_degradation < scale_factor:
            print("   [!] Near-linear scaling - acceptable for most workloads")
        else:
            print("   [!] Super-linear scaling - optimization needed")


if __name__ == "__main__":
    run_scalability_test()
