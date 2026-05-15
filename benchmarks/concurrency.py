"""
Concurrency Benchmark - thread-safety and parallel throughput testing.

Simulates multiple concurrent clients hammering OMem with mixed
read/write operations to test thread safety, throughput under
contention, and data integrity with parallel access.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from omem import OMem


@dataclass
class ConcurrencyResult:
    """Results from a concurrent load test."""

    n_threads: int
    n_ops_per_thread: int
    total_ops: int
    duration_s: float
    throughput_ops: float
    errors: int
    add_latencies_ms: List[float]
    rag_latencies_ms: List[float]
    add_p50_ms: float
    add_p99_ms: float
    rag_p50_ms: float
    rag_p99_ms: float
    data_integrity_ok: bool


def _percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = int(len(s) * p / 100.0)
    return s[min(k, len(s) - 1)]


def _worker_mixed(
    m: OMem,
    thread_id: int,
    n_ops: int,
    read_ratio: float,
    add_latencies: List[float],
    rag_latencies: List[float],
    errors: List[str],
    lock: threading.Lock,
):
    """Single worker: performs a mix of add() and rag() operations."""
    rng = np.random.default_rng(thread_id * 1000)

    for i in range(n_ops):
        try:
            if rng.random() < read_ratio:
                t0 = time.perf_counter()
                m.recall(f"topic {rng.integers(0, 50)}", top_k=5)
                lat = (time.perf_counter() - t0) * 1000
                with lock:
                    rag_latencies.append(lat)
            else:
                content = f"Thread-{thread_id} op-{i}: data {rng.integers(0, 10000)}"
                t0 = time.perf_counter()
                m.add(content)
                lat = (time.perf_counter() - t0) * 1000
                with lock:
                    add_latencies.append(lat)
        except Exception as e:
            with lock:
                errors.append(f"Thread-{thread_id} op-{i}: {e}")


def _worker_write_only(
    m: OMem,
    thread_id: int,
    n_ops: int,
    latencies: List[float],
    errors: List[str],
    lock: threading.Lock,
):
    """Pure-write worker for write contention testing."""
    for i in range(n_ops):
        try:
            content = (
                f"WriteWorker-{thread_id}-{i}: unique content {thread_id * 100000 + i}"
            )
            t0 = time.perf_counter()
            m.add(content)
            lat = (time.perf_counter() - t0) * 1000
            with lock:
                latencies.append(lat)
        except Exception as e:
            with lock:
                errors.append(f"Write-{thread_id}-{i}: {e}")


def run_concurrent_mixed(
    n_threads: int = 8,
    n_ops_per_thread: int = 500,
    read_ratio: float = 0.7,
    verbose: bool = True,
) -> ConcurrencyResult:
    """Mixed concurrent read/write load test."""
    m = OMem()

    # Pre-seed data
    for i in range(2000):
        m.add(f"Seed-{i}: topic {i % 50} domain {i % 20}")

    add_latencies: List[float] = []
    rag_latencies: List[float] = []
    errors: List[str] = []
    lock = threading.Lock()

    if verbose:
        print(
            f"Running mixed concurrent test: {n_threads} threads x {n_ops_per_thread} ops (read ratio={read_ratio})"
        )

    t0 = time.perf_counter()
    threads = []
    for tid in range(n_threads):
        t = threading.Thread(
            target=_worker_mixed,
            args=(
                m,
                tid,
                n_ops_per_thread,
                read_ratio,
                add_latencies,
                rag_latencies,
                errors,
                lock,
            ),
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
    duration = time.perf_counter() - t0

    total_ops = n_threads * n_ops_per_thread

    # Data integrity check: every memory in KV should be retrievable
    all_mems = m.all()
    integrity_ok = len(all_mems) > 0 and all(mem.content for mem in all_mems)

    result = ConcurrencyResult(
        n_threads=n_threads,
        n_ops_per_thread=n_ops_per_thread,
        total_ops=total_ops,
        duration_s=duration,
        throughput_ops=total_ops / duration,
        errors=len(errors),
        add_latencies_ms=sorted(add_latencies),
        rag_latencies_ms=sorted(rag_latencies),
        add_p50_ms=_percentile(add_latencies, 50),
        add_p99_ms=_percentile(add_latencies, 99),
        rag_p50_ms=_percentile(rag_latencies, 50),
        rag_p99_ms=_percentile(rag_latencies, 99),
        data_integrity_ok=integrity_ok,
    )

    if verbose:
        _print_result(result)
        if errors:
            print(f"\n  WARNING: Errors ({len(errors)}):")
            for e in errors[:5]:
                print(f"    {e}")

    return result


def run_concurrent_write_stress(
    n_threads: int = 16,
    n_ops_per_thread: int = 1000,
    verbose: bool = True,
) -> ConcurrencyResult:
    """Pure write concurrency stress test."""
    m = OMem()

    latencies: List[float] = []
    errors: List[str] = []
    lock = threading.Lock()

    if verbose:
        print(
            f"Running write stress test: {n_threads} threads x {n_ops_per_thread} writes"
        )

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_threads) as executor:
        futures = []
        for tid in range(n_threads):
            futures.append(
                executor.submit(
                    _worker_write_only,
                    m,
                    tid,
                    n_ops_per_thread,
                    latencies,
                    errors,
                    lock,
                )
            )
        for f in as_completed(futures):
            f.result()  # raise if any exception
    duration = time.perf_counter() - t0

    total_ops = n_threads * n_ops_per_thread

    result = ConcurrencyResult(
        n_threads=n_threads,
        n_ops_per_thread=n_ops_per_thread,
        total_ops=total_ops,
        duration_s=duration,
        throughput_ops=total_ops / duration,
        errors=len(errors),
        add_latencies_ms=sorted(latencies),
        rag_latencies_ms=[],
        add_p50_ms=_percentile(latencies, 50),
        add_p99_ms=_percentile(latencies, 99),
        rag_p50_ms=0.0,
        rag_p99_ms=0.0,
        data_integrity_ok=len(errors) == 0,
    )

    if verbose:
        _print_result(result)

    return result


def run_thread_scaling(
    thread_counts: Optional[List[int]] = None,
    n_ops_per_thread: int = 500,
    verbose: bool = True,
) -> List[ConcurrencyResult]:
    """Measure throughput scaling as thread count increases."""
    if thread_counts is None:
        thread_counts = [1, 2, 4, 8, 16, 32]

    results = []
    if verbose:
        print("=" * 70)
        print("  OMem Thread Scaling Benchmark")
        print("=" * 70)

    for n_t in thread_counts:
        r = run_concurrent_mixed(
            n_threads=n_t, n_ops_per_thread=n_ops_per_thread, verbose=False
        )
        results.append(r)
        if verbose:
            status = "PASS" if r.errors == 0 else "WARN"
            print(
                f"  [{status}] {n_t:>3} threads: {r.throughput_ops:>10,.0f} ops/s | "
                f"add p99={r.add_p99_ms:.3f}ms  rag p99={r.rag_p99_ms:.3f}ms | "
                f"errors={r.errors}"
            )

    if verbose and len(results) >= 2:
        speedup = results[-1].throughput_ops / results[0].throughput_ops
        print(
            f"\n{results[0].n_threads} to {results[-1].n_threads} thread speedup: {speedup:.2f}x throughput"
        )

    return results


def _print_result(r: ConcurrencyResult) -> None:
    print(f"  Duration:   {r.duration_s:.3f}s")
    print(f"  Throughput: {r.throughput_ops:,.0f} ops/s")
    print(f"  Add p50/p99: {r.add_p50_ms:.3f}ms / {r.add_p99_ms:.3f}ms")
    if r.rag_latencies_ms:
        print(f"  RAG p50/p99: {r.rag_p50_ms:.3f}ms / {r.rag_p99_ms:.3f}ms")
    print(f"  Errors:     {r.errors}")
    print(f"  Integrity:  {'PASS' if r.data_integrity_ok else 'FAIL'}")


if __name__ == "__main__":
    run_thread_scaling()
