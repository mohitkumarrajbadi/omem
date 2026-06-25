"""Benchmark specifically isolating the Rust SIMD ranking loop."""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import omem_rust

from omem.core.engine.rag import _HAS_RUST


def run_benchmark():
    if not _HAS_RUST:
        print("ERROR: omem_rust extension not found. Compile it first!")
        sys.exit(1)

    print("==================================================")
    print("OMem v0.0.1 Sub-Millisecond Speed Benchmark")
    print("==================================================")

    # 1. Setup mock data for 10,000 candidate memories
    N_CANDIDATES = 10_000
    DIM = 384
    TOP_K = 10

    print(f"Setting up {N_CANDIDATES:,} mock memory vectors (dim={DIM})...")

    query = np.random.rand(DIM).astype(np.float32)
    vectors = np.random.rand(N_CANDIDATES, DIM).astype(np.float32)
    base_scores = np.random.rand(N_CANDIDATES).astype(np.float32)
    recencies = np.random.rand(N_CANDIDATES).astype(np.float32)
    mem_types = np.zeros(N_CANDIDATES, dtype=np.uint8)

    weights = [0.6, 0.2, 0.15, 0.05]  # vector, importance, recency, keyword
    type_boosts = np.ones(10, dtype=np.float32)

    print("Warming up Rust SIMD engine...")
    _ = omem_rust.rag_score_batch(
        query,
        vectors[:100],
        base_scores[:100],
        recencies[:100],
        mem_types[:100],
        weights,
        type_boosts,
        TOP_K,
    )

    print(
        f"\nRunning 1,000 iterations of Rust SIMD scoring over {N_CANDIDATES:,} memories..."
    )

    ITERATIONS = 1000

    t0 = time.time()
    for _ in range(ITERATIONS):
        omem_rust.rag_score_batch(
            query,
            vectors,
            base_scores,
            recencies,
            mem_types,
            weights,
            type_boosts,
            TOP_K,
        )
    t1 = time.time()

    elapsed_ms = (t1 - t0) * 1000
    avg_ms = elapsed_ms / ITERATIONS

    print("\n[ RESULTS ]")
    print(f"Total time for {ITERATIONS:,} queries : {elapsed_ms:.2f} ms")
    print(f"Average time per query        : {avg_ms:.4f} ms")

    if avg_ms < 1.0:
        print(f"\nSUB-1MS GOAL ACHIEVED: {avg_ms:.4f} ms per query over 10K memories!")
        print("   (This proves the Rust + SIMD integration is active and ultra-fast)")
    else:
        print(f"\nFAILED TO HIT <1ms. Actual: {avg_ms:.4f} ms")


if __name__ == "__main__":
    run_benchmark()
