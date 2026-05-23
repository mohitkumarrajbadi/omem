"""OMem Benchmark - measure add() and rag() performance at scale."""

import time
import sys

from omem import OMem


def run_benchmark(n: int = 1000):
    print(f"OMem Benchmark (n={n})")
    print("=" * 50)

    m = OMem()

    # ----- Insertion benchmark -----
    print(f"\nInserting {n} memories...")
    t0 = time.perf_counter()
    for i in range(n):
        m.add(
            f"Memory entry {i}: contextual information about topic {i % 50} in domain {i % 10}"
        )
    add_time = time.perf_counter() - t0

    # ----- Retrieval benchmark -----
    num_queries = min(100, n)
    queries = [f"topic {i}" for i in range(num_queries)]

    print(f"Running {num_queries} RAG queries...")
    t0 = time.perf_counter()
    for q in queries:
        m.recall(q, top_k=5)
    rag_time = time.perf_counter() - t0

    # ----- Results -----
    print(f"\n{'Metric':<30} {'Value':>12}")
    print("-" * 42)
    print(f"{'Memories inserted:':<30} {n:>12,}")
    print(f"{'Insert total:':<30} {add_time:>11.3f}s")
    print(f"{'Insert per memory:':<30} {add_time / n * 1000:>10.3f}ms")
    print(f"{'RAG queries:':<30} {num_queries:>12,}")
    print(f"{'RAG total:':<30} {rag_time:>11.3f}s")
    print(f"{'RAG per query:':<30} {rag_time / num_queries * 1000:>10.3f}ms")
    print(f"{'Total memories:':<30} {m.stats()['total']:>12,}")

    print("\nBenchmark complete!")
    return {"add_time": add_time, "rag_time": rag_time, "n": n}


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    run_benchmark(n)
