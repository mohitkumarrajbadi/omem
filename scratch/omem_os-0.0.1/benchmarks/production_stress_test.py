"""
OMem V2 - Production-Level Stress Test.

Tests the upgraded engine under conditions that simulate real-world AI agent
deployments:

  1. Bulk Ingestion Throughput   - How fast can we add 5,000 memories?
  2. Single Query Latency        - p50/p95/p99 retrieval latency.
  3. Cache Hit Speedup           - Measures LRU Working Memory speedup.
  4. Concurrent Read Throughput  - Multi-threaded RAG queries (RWLock test).
  5. Numba JIT Warm-up           - First-call vs steady-state scoring latency.
  6. End-to-End Agent Simulation - 10k interactions with contradiction handling.

Usage:
    python benchmarks/production_stress_test.py
"""

import os
import random
import statistics
import sys
import threading
import time
from typing import List

# Ensure omem is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from omem import OMem

# --------------------------- Helpers ---------------------------


def _banner(title: str):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def _result(label: str, value: str):
    print(f"  {label:<45} | {value}")


def _sep():
    print(f"{'-' * 70}")


# --------------------- 1. Bulk Ingestion ----------------------


def bench_ingestion(m: OMem, n: int = 5000) -> float:
    """Add N memories, return total time in seconds."""
    _banner(f"1. Bulk Ingestion - {n:,} memories")

    corpus = [
        f"Memory item {i}: The quick brown fox talks about topic-{i % 50} on day {i // 100}."
        for i in range(n)
    ]

    start = time.perf_counter()
    for text in corpus:
        m.add(text, importance=random.uniform(0.1, 1.0))
    elapsed = time.perf_counter() - start

    rate = n / elapsed
    _result("Total time", f"{elapsed:.2f}s")
    _result("Throughput", f"{rate:,.0f} memories/sec")
    _result("Avg per memory", f"{(elapsed / n) * 1000:.2f}ms")

    return elapsed


# --------------------- 2. Single Query Latency ----------------


def bench_latency(m: OMem, queries: List[str], n_rounds: int = 3) -> dict:
    """Run each query n_rounds times, report p50/p95/p99."""
    _banner("2. Single Query Latency (cold -> warm)")

    # Warm up Numba JIT on first call
    m.recall("warmup query", top_k=1)

    latencies_ms = []
    for _ in range(n_rounds):
        for q in queries:
            t0 = time.perf_counter()
            m.recall(q, top_k=5)
            dt = (time.perf_counter() - t0) * 1000
            latencies_ms.append(dt)

    latencies_ms.sort()
    p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)]
    avg = statistics.mean(latencies_ms)

    _result("Queries executed", f"{len(latencies_ms)}")
    _result("Avg latency", f"{avg:.2f}ms")
    _result("p50 latency", f"{p50:.2f}ms")
    _result("p95 latency", f"{p95:.2f}ms")
    _result("p99 latency", f"{p99:.2f}ms")

    return {"avg": avg, "p50": p50, "p95": p95, "p99": p99}


# --------------------- 3. Cache Hit Speedup -------------------


def bench_cache(m: OMem) -> float:
    """Measure speedup from the LRU Working Memory Buffer."""
    _banner("3. LRU Cache Hit Speedup")

    query = "What programming language do I prefer?"

    # Cold call (cache miss)
    t0 = time.perf_counter()
    m.recall(query, top_k=5)
    cold_ms = (time.perf_counter() - t0) * 1000

    # Hot call (cache hit)
    t0 = time.perf_counter()
    m.recall(query, top_k=5)
    hot_ms = (time.perf_counter() - t0) * 1000

    speedup = cold_ms / max(hot_ms, 0.001)

    _result("Cold (cache miss)", f"{cold_ms:.3f}ms")
    _result("Hot  (cache hit)", f"{hot_ms:.3f}ms")
    _result("Speedup", f"{speedup:.1f}x faster")

    return speedup


# --------------------- 4. Concurrent Reads --------------------


def bench_concurrency(m: OMem, n_threads: int = 8, queries_per_thread: int = 20):
    """Fire N threads doing RAG queries simultaneously (tests RWLock)."""
    _banner(
        f"4. Concurrent Read Throughput - {n_threads} threads x {queries_per_thread} queries"
    )

    sample_queries = [
        "What editor do I use?",
        "Tell me about Python",
        "What is OMem?",
        "Where do I live?",
        "programming language preference",
        "AI memory system",
        "favorite food",
        "debugging tips",
    ]

    results = []
    errors = []
    barrier = threading.Barrier(n_threads)

    def worker():
        barrier.wait()  # all threads start at the same time
        t0 = time.perf_counter()
        for _ in range(queries_per_thread):
            q = random.choice(sample_queries)
            try:
                m.recall(q, top_k=3)
            except Exception as e:
                errors.append(str(e))
        dt = time.perf_counter() - t0
        results.append(dt)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    wall_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_time = time.perf_counter() - wall_start

    total_queries = n_threads * queries_per_thread
    qps = total_queries / wall_time

    _result("Total queries", f"{total_queries}")
    _result("Wall-clock time", f"{wall_time:.2f}s")
    _result("Throughput", f"{qps:,.0f} queries/sec")
    _result("Thread errors", f"{len(errors)}")

    if errors:
        print(f"  WARNING: Errors: {errors[:3]}")


# --------------------- 5. Numba JIT Warm-up -------------------


def bench_numba_warmup(m: OMem):
    """Measure the one-time Numba compilation cost vs steady-state."""
    _banner("5. Numba JIT Warm-up Cost")

    # Create a fresh OMem to force first-ever JIT compilation
    fresh = OMem()
    for i in range(50):
        fresh.add(f"Test memory {i} about topic-{i % 10}", importance=0.5)

    query = "topic-5 information"

    # First call triggers Numba compilation
    t0 = time.perf_counter()
    fresh.recall(query, top_k=5)
    first_ms = (time.perf_counter() - t0) * 1000

    # Subsequent calls use the cached compiled code
    times = []
    for _ in range(10):
        t0 = time.perf_counter()
        fresh.recall(query + f" {random.randint(0, 9999)}", top_k=5)
        times.append((time.perf_counter() - t0) * 1000)

    avg_steady = statistics.mean(times)

    _result("First call (JIT compile)", f"{first_ms:.2f}ms")
    _result("Steady-state avg", f"{avg_steady:.2f}ms")
    _result("JIT overhead", f"{first_ms / max(avg_steady, 0.001):.1f}x (one-time cost)")


# ---------------- 6. End-to-End Agent Simulation --------------


def bench_agent_e2e():
    """Full agent lifecycle: 10k interactions with facts and contradictions."""
    _banner("6. End-to-End Agent Simulation - 10,000 interactions")

    m = OMem()
    n_noise = 9000

    print("  Generating noise interactions...")
    topics = [
        "weather",
        "code bug",
        "meeting",
        "lunch",
        "compile error",
        "git rebase",
        "deploy",
    ]
    noise = [
        f"Interaction {i}: Had a {random.choice(topics)} today." for i in range(n_noise)
    ]

    facts = [
        (1000, "My favorite editor is VSCode"),
        (1050, "I use Python mostly for backend development"),
        (1100, "I live in an apartment in Mumbai"),
        (5000, "I'm starting to heavily use Rust for performance critical services"),
        (5100, "I'm working on an AI memory system called OMem"),
        (8000, "Actually switched to Cursor AI editor from VSCode"),
        (8100, "I moved to a new house in Whitefield, Bangalore"),
    ]

    timeline = [(i, "noise", noise[i]) for i in range(n_noise)]
    for t, fact in facts:
        timeline.append((t, "fact", fact))
    timeline.sort(key=lambda x: x[0])

    print("  Ingesting timeline...")
    t0 = time.perf_counter()
    for _, kind, content in timeline:
        if kind == "fact":
            if "switched to Cursor" in content:
                results = m.recall("VSCode editor", top_k=1)
                if results:
                    m.update(results[0].id, content)
                else:
                    m.add(content)
            elif "moved to a new house" in content:
                results = m.recall("live in Mumbai", top_k=1)
                if results:
                    m.update(results[0].id, content)
                else:
                    m.add(content)
            else:
                m.add(content, importance=0.9)
        else:
            m.add(content)
    ingest_time = time.perf_counter() - t0

    _result("Ingestion time", f"{ingest_time:.1f}s")
    _result("Total memories", f"{m.stats()['total']}")

    _sep()
    print(f"  {'Query':<35} | {'Top Result':<30} | Correct?")
    _sep()

    queries = [
        ("What editor do I use?", ["Cursor"]),
        ("Where do I live?", ["Whitefield", "Bangalore"]),
        ("What languages do I use?", ["Python", "Rust"]),
        ("What am I building?", ["OMem", "memory"]),
    ]

    score = 0
    for q, expected in queries:
        t0 = time.perf_counter()
        results = m.recall(q, top_k=1)
        lat = (time.perf_counter() - t0) * 1000
        ans = results[0].content if results else "None"
        correct = any(e.lower() in ans.lower() for e in expected)
        icon = "OK" if correct else "FAIL"
        if correct:
            score += 1
        _result(f"{q} ({lat:.0f}ms)", f"{icon} {ans[:28]}...")

    _sep()
    _result("Accuracy", f"{score}/{len(queries)} ({score / len(queries) * 100:.0f}%)")


# --------------------------- Main -----------------------------


def main():
    print("\n" + "#" * 70)
    print("#  OMem V2 - Production-Level Stress Test")
    print("#  Testing: HNSW + Numba JIT + RWLock + LRU Cache")
    print("#" * 70)

    random.seed(42)

    m = OMem()

    # Run benchmarks in order
    bench_ingestion(m, n=5000)

    queries = [
        "What programming language do I prefer?",
        "Tell me about AI memory systems",
        "What editor should I use?",
        "latest news about technology",
        "topic-25 detailed information",
    ]
    bench_latency(m, queries, n_rounds=5)

    bench_cache(m)

    bench_concurrency(m, n_threads=8, queries_per_thread=20)

    bench_numba_warmup(m)

    bench_agent_e2e()

    print("\n" + "#" * 70)
    print("#  All production tests complete!")
    print("#" * 70 + "\n")


if __name__ == "__main__":
    main()
