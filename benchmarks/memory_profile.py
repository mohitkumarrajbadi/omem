"""
Memory Profiler - RSS, heap, and per-object memory tracking.

Measures actual memory consumption at different dataset scales
to validate cloud deployment resource planning.
"""

import gc
import sys
from dataclasses import dataclass
from typing import List, Optional

from omem import OMem


@dataclass
class MemoryProfile:
    """Memory usage snapshot at a specific scale."""

    n_memories: int
    rss_mb: float
    rss_per_memory_kb: float
    faiss_index_mb: float
    kv_cache_entries: int
    backend_count: int


def _get_rss_mb() -> float:
    """Get current process RSS in MB."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # macOS returns bytes, Linux returns KB
        if sys.platform == "darwin":
            return usage.ru_maxrss / (1024 * 1024)
        else:
            return usage.ru_maxrss / 1024
    except Exception:
        return 0.0


def _estimate_faiss_mb(n: int, dim: int = 384) -> float:
    """Estimate FAISS IndexFlatIP memory: N x dim x 4 bytes."""
    return (n * dim * 4) / (1024 * 1024)


def profile_memory_usage(
    scales: Optional[List[int]] = None,
    verbose: bool = True,
) -> List[MemoryProfile]:
    """Profile memory consumption at increasing dataset sizes."""
    if scales is None:
        scales = [1_000, 5_000, 10_000, 50_000, 100_000]

    results: List[MemoryProfile] = []

    if verbose:
        print("=" * 70)
        print("  OMem Memory Profiler - Resource Consumption Analysis")
        print("=" * 70)

    for n in scales:
        gc.collect()
        rss_before = _get_rss_mb()

        m = OMem()
        for i in range(n):
            m.add(
                f"Memory-{i}: content for profiling with domain {i % 100} and topic {i % 50}"
            )

        gc.collect()
        rss_after = _get_rss_mb()
        rss_delta = max(rss_after - rss_before, 0.0)

        profile = MemoryProfile(
            n_memories=n,
            rss_mb=rss_delta,
            rss_per_memory_kb=(rss_delta * 1024 / n) if n > 0 else 0.0,
            faiss_index_mb=_estimate_faiss_mb(n),
            kv_cache_entries=m.brain.kv.size,
            backend_count=m._backend.count(),
        )
        results.append(profile)

        if verbose:
            print(f"\n  Batch size {n:>8,} memories:")
            print(f"    RSS delta:          {rss_delta:>8.1f} MB")
            print(f"    Per memory:         {profile.rss_per_memory_kb:>8.2f} KB")
            print(f"    FAISS index (est):  {profile.faiss_index_mb:>8.1f} MB")
            print(f"    KV cache entries:   {profile.kv_cache_entries:>8,}")
            print(f"    Backend records:    {profile.backend_count:>8,}")

        del m
        gc.collect()

    if verbose:
        print("\n" + "-" * 70)
        _print_summary(results)

    return results


def _print_summary(results: List[MemoryProfile]) -> None:
    """Print cloud deployment resource estimation."""
    print("\n  Cloud Resource Estimation:")
    print(
        f"  {'Scale':>10} | {'RSS':>8} | {'Per Mem':>10} | {'FAISS':>10} | {'Recommended Instance':>25}"
    )
    print(f"  {'-' * 10}-+-{'-' * 8}-+-{'-' * 10}-+-{'-' * 10}-+-{'-' * 25}")

    for r in results:
        if r.rss_mb < 512:
            instance = "t3.small (2GB)"
        elif r.rss_mb < 2048:
            instance = "t3.medium (4GB)"
        elif r.rss_mb < 8192:
            instance = "t3.xlarge (16GB)"
        elif r.rss_mb < 32768:
            instance = "r5.2xlarge (64GB)"
        else:
            instance = "r5.4xlarge (128GB)"

        print(
            f"  {r.n_memories:>10,} | {r.rss_mb:>7.1f}MB | {r.rss_per_memory_kb:>9.2f}KB | "
            f"{r.faiss_index_mb:>9.1f}MB | {instance:>25}"
        )

    # Extrapolation
    if len(results) >= 2:
        last = results[-1]
        for target in [1_000_000, 10_000_000]:
            est_mb = last.rss_per_memory_kb * target / 1024
            print(f"\n  Extrapolated {target:>12,} memories: ~{est_mb:,.0f} MB RAM")


if __name__ == "__main__":
    profile_memory_usage()
