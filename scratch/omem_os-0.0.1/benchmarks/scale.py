"""
Large-Scale FAISS Benchmark - 100K -> 1M+ memories.

Tests how OMem performs at *real production scale*:
- FAISS IndexFlatIP behavior at 100K, 250K, 500K, 1M memories
- Latency vs dataset size curves
- Memory footprint vs dataset size
- End-to-end latency (embedding + retrieval, separated)
- Index build time scaling

This benchmark is separate from the quick suite because 1M entries
can take 1-3 minutes depending on hardware.
"""

import argparse
import gc
import json
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from omem.core.retrieval.vector import VectorIndex

# -- Result types --


@dataclass
class ScalePoint:
    n: int
    # Index build
    build_time_s: float = 0.0
    build_per_op_ms: float = 0.0
    # Search latency (retrieval only, no embedding)
    search_mean_ms: float = 0.0
    search_p50_ms: float = 0.0
    search_p95_ms: float = 0.0
    search_p99_ms: float = 0.0
    search_p999_ms: float = 0.0
    search_max_ms: float = 0.0
    # End-to-end (embedding + retrieval)
    e2e_mean_ms: float = 0.0
    e2e_p50_ms: float = 0.0
    e2e_p95_ms: float = 0.0
    e2e_p99_ms: float = 0.0
    e2e_embed_ms: float = 0.0  # avg embedding cost
    e2e_retrieval_ms: float = 0.0  # avg retrieval cost
    # Memory
    rss_mb: float = 0.0
    faiss_size_mb: float = 0.0
    # Throughput
    search_ops_per_s: float = 0.0
    e2e_ops_per_s: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__


def _pct(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = min(int(len(s) * p / 100.0), len(s) - 1)
    return s[k]


def _rss_mb() -> float:
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return ru / (1024 * 1024) if sys.platform == "darwin" else ru / 1024
    except Exception:
        return 0.0


def _generate_vectors(n: int, dim: int = 384) -> np.ndarray:
    """Generate n random L2-normalised vectors."""
    vecs = np.random.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def _generate_content_batch(n: int) -> List[str]:
    """Generate n unique strings for embedding."""
    return [
        f"Memory entry {i}: topic {i % 200} category {i % 50} domain {i % 20}"
        for i in range(n)
    ]


# -- Benchmark functions --


def bench_faiss_raw(
    n: int, dim: int = 384, n_queries: int = 1000, top_k: int = 5
) -> ScalePoint:
    """Benchmark raw FAISS performance (no embedding overhead)."""
    gc.collect()
    rss_before = _rss_mb()

    idx = VectorIndex(dim=dim)
    vectors = _generate_vectors(n, dim)

    # Build index
    t0 = time.perf_counter()
    idx.add(vectors)
    build_time = time.perf_counter() - t0

    gc.collect()
    rss_after = _rss_mb()

    # Search (retrieval only)
    query_vecs = _generate_vectors(n_queries, dim)
    search_latencies = []
    for i in range(n_queries):
        t0 = time.perf_counter()
        idx.search(query_vecs[i], top_k=top_k)
        search_latencies.append((time.perf_counter() - t0) * 1000)

    faiss_size = (n * dim * 4) / (1024 * 1024)  # float32

    return ScalePoint(
        n=n,
        build_time_s=build_time,
        build_per_op_ms=(build_time / n) * 1000,
        search_mean_ms=sum(search_latencies) / len(search_latencies),
        search_p50_ms=_pct(search_latencies, 50),
        search_p95_ms=_pct(search_latencies, 95),
        search_p99_ms=_pct(search_latencies, 99),
        search_p999_ms=_pct(search_latencies, 99.9),
        search_max_ms=max(search_latencies),
        search_ops_per_s=n_queries / (sum(search_latencies) / 1000),
        rss_mb=max(rss_after - rss_before, 0),
        faiss_size_mb=faiss_size,
    )


def bench_e2e(n: int, n_queries: int = 500, top_k: int = 5) -> ScalePoint:
    """Benchmark end-to-end: embedding + retrieval, costs separated."""
    from omem import OMem

    gc.collect()
    rss_before = _rss_mb()

    m = OMem()
    content = _generate_content_batch(n)

    # Build
    t0 = time.perf_counter()
    for c in content:
        m.add(c)
    build_time = time.perf_counter() - t0

    gc.collect()
    rss_after = _rss_mb()

    # Queries
    queries = [f"topic {i % 200} domain {i % 20}" for i in range(n_queries)]

    embed_latencies = []
    retrieval_latencies = []
    e2e_latencies = []

    embedder = m.brain.embedder

    for q in queries:
        # End-to-end (what users experience)
        t_start = time.perf_counter()

        # Phase 1: Embedding
        t_embed = time.perf_counter()
        qvec = embedder.encode(q)
        embed_time = (time.perf_counter() - t_embed) * 1000

        # Phase 2: Retrieval
        t_ret = time.perf_counter()
        m.brain.vector_index.search(qvec, top_k=top_k)
        ret_time = (time.perf_counter() - t_ret) * 1000

        total = (time.perf_counter() - t_start) * 1000

        embed_latencies.append(embed_time)
        retrieval_latencies.append(ret_time)
        e2e_latencies.append(total)

    faiss_size = (n * embedder.dim * 4) / (1024 * 1024)

    return ScalePoint(
        n=n,
        build_time_s=build_time,
        build_per_op_ms=(build_time / n) * 1000,
        # Retrieval-only
        search_mean_ms=sum(retrieval_latencies) / len(retrieval_latencies),
        search_p50_ms=_pct(retrieval_latencies, 50),
        search_p95_ms=_pct(retrieval_latencies, 95),
        search_p99_ms=_pct(retrieval_latencies, 99),
        search_p999_ms=_pct(retrieval_latencies, 99.9),
        search_max_ms=max(retrieval_latencies),
        search_ops_per_s=n_queries / (sum(retrieval_latencies) / 1000),
        # End-to-end
        e2e_mean_ms=sum(e2e_latencies) / len(e2e_latencies),
        e2e_p50_ms=_pct(e2e_latencies, 50),
        e2e_p95_ms=_pct(e2e_latencies, 95),
        e2e_p99_ms=_pct(e2e_latencies, 99),
        e2e_embed_ms=sum(embed_latencies) / len(embed_latencies),
        e2e_retrieval_ms=sum(retrieval_latencies) / len(retrieval_latencies),
        e2e_ops_per_s=n_queries / (sum(e2e_latencies) / 1000),
        # Memory
        rss_mb=max(rss_after - rss_before, 0),
        faiss_size_mb=faiss_size,
    )


# -- Runners --


def run_faiss_scale_benchmark(
    scales: Optional[List[int]] = None,
    n_queries: int = 1000,
    verbose: bool = True,
) -> List[ScalePoint]:
    """Run FAISS-only benchmark at increasing scales."""
    if scales is None:
        scales = [10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]

    if verbose:
        print("=" * 90)
        print("  OMem FAISS Scale Benchmark - Raw Vector Search Performance")
        print(f"  Queries per scale: {n_queries} | top_k=5 | dim=384")
        print("=" * 90)

    results = []
    for n in scales:
        if verbose:
            print(f"\n> Scale: {n:>10,} vectors", end="", flush=True)

        point = bench_faiss_raw(n, n_queries=n_queries)
        results.append(point)

        if verbose:
            print(
                f"  | build={point.build_time_s:.2f}s"
                f"  | search p50={point.search_p50_ms:.3f}ms"
                f"  p99={point.search_p99_ms:.3f}ms"
                f"  p99.9={point.search_p999_ms:.3f}ms"
                f"  | {point.search_ops_per_s:,.0f} ops/s"
                f"  | FAISS={point.faiss_size_mb:.0f}MB"
            )

    if verbose:
        _print_scale_table(results, "FAISS RAW")
        _print_scaling_analysis(results)

    return results


def run_e2e_scale_benchmark(
    scales: Optional[List[int]] = None,
    n_queries: int = 500,
    verbose: bool = True,
) -> List[ScalePoint]:
    """Run end-to-end benchmark separating embedding vs retrieval cost."""
    if scales is None:
        scales = [1_000, 5_000, 10_000, 50_000, 100_000]

    if verbose:
        print("\n" + "=" * 90)
        print("  OMem End-to-End Latency Benchmark - Embedding vs Retrieval Cost")
        print(f"  Queries per scale: {n_queries} | top_k=5")
        print("=" * 90)

    results = []
    for n in scales:
        if verbose:
            print(f"\n> Scale: {n:>10,} memories", end="", flush=True)

        point = bench_e2e(n, n_queries=n_queries)
        results.append(point)

        if verbose:
            print(
                f"  | embed={point.e2e_embed_ms:.3f}ms"
                f"  retrieval={point.e2e_retrieval_ms:.3f}ms"
                f"  | e2e p50={point.e2e_p50_ms:.3f}ms"
                f"  p99={point.e2e_p99_ms:.3f}ms"
                f"  | {point.e2e_ops_per_s:,.0f} e2e ops/s"
            )

    if verbose:
        _print_e2e_table(results)

    return results


def _print_scale_table(results: List[ScalePoint], label: str = "") -> None:
    print(f"\n{'-' * 90}")
    print(f"  {label} - Latency vs Dataset Size")
    print(f"{'-' * 90}")
    print(
        f"  {'N':>12} | {'Build':>8} | {'p50':>9} {'p95':>9} {'p99':>9} {'p99.9':>9} | {'ops/s':>10} | {'FAISS MB':>9} {'RSS MB':>8}"
    )
    print(f"{'-' * 90}")
    for r in results:
        print(
            f"  {r.n:>12,} | {r.build_time_s:>7.2f}s |"
            f" {r.search_p50_ms:>8.3f}ms {r.search_p95_ms:>8.3f}ms"
            f" {r.search_p99_ms:>8.3f}ms {r.search_p999_ms:>8.3f}ms |"
            f" {r.search_ops_per_s:>10,.0f} |"
            f" {r.faiss_size_mb:>8.1f}MB {r.rss_mb:>7.1f}MB"
        )
    print(f"{'-' * 90}")


def _print_e2e_table(results: List[ScalePoint]) -> None:
    print(f"\n{'-' * 100}")
    print("  End-to-End Latency Breakdown - Where Time Goes")
    print(f"{'-' * 100}")
    print(
        f"  {'N':>12} | {'Embed':>9} {'Retrieval':>10} {'Total':>9} |"
        f" {'e2e p50':>9} {'e2e p95':>9} {'e2e p99':>9} |"
        f" {'e2e ops/s':>10} | {'Embed %':>7}"
    )
    print(f"{'-' * 100}")
    for r in results:
        embed_pct = (r.e2e_embed_ms / max(r.e2e_mean_ms, 0.001)) * 100
        print(
            f"  {r.n:>12,} |"
            f" {r.e2e_embed_ms:>8.3f}ms {r.e2e_retrieval_ms:>9.3f}ms {r.e2e_mean_ms:>8.3f}ms |"
            f" {r.e2e_p50_ms:>8.3f}ms {r.e2e_p95_ms:>8.3f}ms {r.e2e_p99_ms:>8.3f}ms |"
            f" {r.e2e_ops_per_s:>10,.0f} |"
            f" {embed_pct:>6.1f}%"
        )
    print(f"{'-' * 100}")

    # Summary insight
    if len(results) >= 2:
        first, last = results[0], results[-1]
        ret_growth = last.e2e_retrieval_ms / max(first.e2e_retrieval_ms, 0.001)
        scale_factor = last.n / first.n
        print(
            f"\n  Embedding cost: ~{last.e2e_embed_ms:.1f}ms (constant across all scales)"
        )
        print(
            f"  Retrieval cost: {first.e2e_retrieval_ms:.3f}ms -> {last.e2e_retrieval_ms:.3f}ms ({ret_growth:.1f}x for {scale_factor:.0f}x data)"
        )
        embed_pct = (last.e2e_embed_ms / max(last.e2e_mean_ms, 0.001)) * 100
        print(
            f"  At {last.n:,} memories, embedding is {embed_pct:.0f}% of end-to-end latency"
        )


def _print_scaling_analysis(results: List[ScalePoint]) -> None:
    if len(results) < 2:
        return

    print("\n  Scaling Analysis:")
    first = results[0]
    for r in results[1:]:
        data_factor = r.n / first.n
        lat_factor = r.search_p50_ms / max(first.search_p50_ms, 0.001)
        complexity = (
            f"O(n^{lat_factor / data_factor:.2f})"
            if lat_factor > 0 and data_factor > 0
            else "N/A"
        )
        print(
            f"    {first.n:>10,} -> {r.n:>10,}: "
            f"{data_factor:>5.0f}x data -> {lat_factor:>6.1f}x latency  "
            f"({complexity})"
        )

    # Cloud recommendations at scale
    last = results[-1]
    print(f"\n  Cloud costs at {last.n:,} vectors:")
    print(f"    FAISS index: {last.faiss_size_mb:.0f} MB")
    print(f"    Search p99: {last.search_p99_ms:.3f} ms")
    if last.n >= 1_000_000:
        print("    Recommended: r6g.xlarge (32GB) or GPU instance for sub-ms latency")
    elif last.n >= 500_000:
        print("    Recommended: t3.xlarge (16GB) or r6g.large (16GB)")
    elif last.n >= 100_000:
        print("    Recommended: t3.large (8GB)")
    else:
        print("    Recommended: t3.small (2GB)")


# -- Main --


def main():
    parser = argparse.ArgumentParser(description="OMem Large-Scale Benchmark")
    parser.add_argument(
        "--mode",
        choices=["faiss", "e2e", "both"],
        default="both",
        help="Benchmark mode: faiss-only, end-to-end, or both",
    )
    parser.add_argument(
        "--max-n",
        type=int,
        default=1_000_000,
        help="Maximum dataset size (default: 1M)",
    )
    parser.add_argument(
        "--queries", type=int, default=1000, help="Number of queries per scale point"
    )
    parser.add_argument(
        "--output", type=str, default=None, help="Save results to JSON file"
    )
    args = parser.parse_args()

    all_results = {}

    faiss_scales = [
        s
        for s in [10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]
        if s <= args.max_n
    ]
    e2e_scales = [s for s in [1_000, 5_000, 10_000, 50_000, 100_000] if s <= args.max_n]

    if args.mode in ("faiss", "both"):
        faiss_results = run_faiss_scale_benchmark(faiss_scales, args.queries)
        all_results["faiss_raw"] = [r.to_dict() for r in faiss_results]

    if args.mode in ("e2e", "both"):
        e2e_results = run_e2e_scale_benchmark(e2e_scales, min(args.queries, 500))
        all_results["e2e"] = [r.to_dict() for r in e2e_results]

    if args.output:
        import platform

        report = {
            "system": {
                "platform": platform.platform(),
                "processor": platform.processor() or platform.machine(),
                "python": platform.python_version(),
            },
            "results": all_results,
        }
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n  Report saved to: {args.output}")


if __name__ == "__main__":
    main()
