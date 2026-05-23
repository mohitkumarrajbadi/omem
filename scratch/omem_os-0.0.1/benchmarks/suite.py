"""
OMem Production Benchmark Suite - Unified Runner

Run all or individual benchmark modules with configurable parameters and
generate JSON/text reports for CI pipelines and cloud deployment validation.

Usage:
    python -m benchmarks.suite --all
    python -m benchmarks.suite --test latency --n 10000
    python -m benchmarks.suite --test scalability --max-n 100000
    python -m benchmarks.suite --test concurrency --threads 16
    python -m benchmarks.suite --test integrity
    python -m benchmarks.suite --test competitor
    python -m benchmarks.suite --test memory
    python -m benchmarks.suite --report json --output results.json
"""

import argparse
import json
import time
from datetime import datetime
from dataclasses import asdict
from typing import Dict, Any, Optional


def _get_system_info() -> Dict[str, str]:
    """Gather system metadata for reproducible reports."""
    import platform

    info = {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "python": platform.python_version(),
        "timestamp": datetime.now().isoformat(),
    }

    try:
        import omem

        info["omem_version"] = omem.__version__
    except Exception:
        pass

    try:
        import faiss

        info["faiss_version"] = (
            faiss.__version__ if hasattr(faiss, "__version__") else "unknown"
        )
    except Exception:
        pass

    try:
        import numpy as np

        info["numpy_version"] = np.__version__
    except Exception:
        pass

    return info


def run_suite(
    tests: Optional[list] = None,
    n: int = 10_000,
    max_n: int = 100_000,
    threads: int = 8,
    n_queries: int = 1_000,
    output: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run the full production benchmark suite."""
    all_tests = {
        "latency",
        "scalability",
        "concurrency",
        "integrity",
        "memory",
        "competitor",
    }
    if tests is None:
        tests = sorted(all_tests)

    report: Dict[str, Any] = {
        "system": _get_system_info(),
        "config": {"n": n, "max_n": max_n, "threads": threads, "n_queries": n_queries},
        "results": {},
        "summary": {},
    }

    wall_start = time.perf_counter()

    if verbose:
        print()
        print("+" + "=" * 68 + "+")
        print("|" + "  OMem Production Benchmark Suite".center(68) + "|")
        print(
            "|" + f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(68) + "|"
        )
        print("+" + "=" * 68 + "+")
        print()

    # -- Latency --
    if "latency" in tests:
        if verbose:
            print("\n" + "#" * 70)
            print("  1/6  LATENCY PROFILER")
            print("#" * 70)
        from benchmarks.latency import run_latency_profile

        lat_results = run_latency_profile(n=n, verbose=verbose)
        report["results"]["latency"] = {k: v.to_dict() for k, v in lat_results.items()}

    # -- Scalability --
    if "scalability" in tests:
        if verbose:
            print("\n" + "#" * 70)
            print("  2/6  SCALABILITY BENCHMARK")
            print("#" * 70)
        from benchmarks.scalability import run_scalability_test

        scales = [s for s in [1_000, 5_000, 10_000, 50_000, 100_000] if s <= max_n]
        scale_results = run_scalability_test(
            scales=scales, n_queries=min(n_queries, 500), verbose=verbose
        )
        report["results"]["scalability"] = [asdict(r) for r in scale_results]

    # -- Concurrency --
    if "concurrency" in tests:
        if verbose:
            print("\n" + "#" * 70)
            print("  3/6  CONCURRENCY BENCHMARK")
            print("#" * 70)
        from benchmarks.concurrency import run_thread_scaling

        thread_counts = [t for t in [1, 2, 4, 8, 16, 32] if t <= threads]
        conc_results = run_thread_scaling(thread_counts=thread_counts, verbose=verbose)
        report["results"]["concurrency"] = [
            {
                "threads": r.n_threads,
                "throughput": r.throughput_ops,
                "add_p99_ms": r.add_p99_ms,
                "rag_p99_ms": r.rag_p99_ms,
                "errors": r.errors,
                "integrity": r.data_integrity_ok,
            }
            for r in conc_results
        ]

    # -- Data Integrity --
    if "integrity" in tests:
        if verbose:
            print("\n" + "#" * 70)
            print("  4/6  DATA INTEGRITY SUITE")
            print("#" * 70)
        from benchmarks.integrity import run_integrity_suite

        int_results = run_integrity_suite(verbose=verbose)
        report["results"]["integrity"] = int_results

    # -- Memory Profile --
    if "memory" in tests:
        if verbose:
            print("\n" + "#" * 70)
            print("  5/6  MEMORY PROFILER")
            print("#" * 70)
        from benchmarks.memory_profile import profile_memory_usage

        scales = [s for s in [1_000, 5_000, 10_000, 50_000, 100_000] if s <= max_n]
        mem_results = profile_memory_usage(scales=scales, verbose=verbose)
        report["results"]["memory"] = [asdict(r) for r in mem_results]

    # -- Competitor Comparison --
    if "competitor" in tests:
        if verbose:
            print("\n" + "#" * 70)
            print("  6/6  COMPETITOR COMPARISON")
            print("#" * 70)
        from benchmarks.competitor import run_comparison

        comp_results = run_comparison(
            n=min(n, 5_000), n_queries=min(n_queries, 500), verbose=verbose
        )
        report["results"]["competitor"] = [
            {
                "name": r.name,
                "available": r.available,
                "setup_ms": r.setup_ms,
                "add_ops_per_s": r.add_ops_per_s,
                "add_p99_ms": r.add_p99_ms,
                "rag_ops_per_s": r.rag_ops_per_s,
                "rag_p95_ms": r.rag_p95_ms,
                "rag_p99_ms": r.rag_p99_ms,
                "memory_mb": r.memory_mb,
                "features": r.features,
                "error": r.error,
            }
            for r in comp_results
        ]

    wall_total = time.perf_counter() - wall_start

    # -- Summary --
    report["summary"]["total_time_s"] = round(wall_total, 2)
    report["summary"]["tests_run"] = tests

    if verbose:
        print("\n" + "=" * 70)
        print(f"  Suite complete in {wall_total:.1f}s")
        print(f"  Tests run: {', '.join(tests)}")
        print("=" * 70)

    # -- Output --
    if output:
        with open(output, "w") as f:
            json.dump(report, f, indent=2, default=str)
        if verbose:
            print(f"\n  Report saved to: {output}")

    return report


def main():
    parser = argparse.ArgumentParser(description="OMem Production Benchmark Suite")
    parser.add_argument("--all", action="store_true", help="Run all benchmark modules")
    parser.add_argument(
        "--test",
        type=str,
        nargs="+",
        help="Specific test(s) to run: latency, scalability, concurrency, integrity, memory, competitor",
    )
    parser.add_argument(
        "--n", type=int, default=10_000, help="Number of memories for latency tests"
    )
    parser.add_argument(
        "--max-n", type=int, default=100_000, help="Max scale for scalability tests"
    )
    parser.add_argument(
        "--threads", type=int, default=16, help="Max thread count for concurrency"
    )
    parser.add_argument(
        "--queries", type=int, default=1_000, help="Number of RAG queries"
    )
    parser.add_argument(
        "--output", type=str, default=None, help="Path to save JSON report"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")

    args = parser.parse_args()

    tests = None
    if args.all:
        tests = None  # run all
    elif args.test:
        tests = args.test

    if tests is None and not args.all:
        tests = None  # default: all

    run_suite(
        tests=tests,
        n=args.n,
        max_n=args.max_n,
        threads=args.threads,
        n_queries=args.queries,
        output=args.output,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
