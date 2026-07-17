#!/usr/bin/env python3
"""OMem vs Mem0 — Reproducible Performance Benchmark.

Measures and compares:
  • Cold-start latency  (first add / recall)
  • Warm add() throughput  (ops/sec, N=1000)
  • RAG p50/p95/p99 recall latency  (N=500 queries, M=5000 memories)
  • Estimated third-party API fees per 1M recalls
  • Memory overhead  (RSS delta, MB)

Methodology:
  OMem  — measured local SQLite path, Rust scoring when available, and
           all-MiniLM-L6-v2 embeddings via sentence-transformers. No required
           third-party API calls.
  Mem0  — by default, a modeled baseline for an LLM-based extraction/scoring
           configuration, using prior competitor.py observations and documented
           network/API characteristics (~15,000ms cold start, ~18 RAG ops/s).

           This is not an apples-to-apples microbenchmark of equivalent
           primitive operations. Use --live-mem0 with Mem0 installed and an
           OPENAI_API_KEY to measure that configured system in your environment.

Usage:
    # Python-only (reproducible, no API keys needed)
    python distribution/benchmark_vs_mem0.py

    # Live Mem0 comparison (requires: pip install mem0ai; export OPENAI_API_KEY=...)
    python distribution/benchmark_vs_mem0.py --live-mem0

    # JSON output for CI
    python distribution/benchmark_vs_mem0.py --json

    # Custom scale
    python distribution/benchmark_vs_mem0.py --memories 5000 --queries 500

Results are written to distribution/benchmark_results.json.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# ── Repository root on path ───────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ─────────────────────────────────────────────────────────────────────────────
# Synthetic dataset
# ─────────────────────────────────────────────────────────────────────────────

_MEMORY_TEMPLATES = [
    "Architectural decision: {topic} should use {tech} because {reason}.",
    "Bug fix in {module}: {symptom} caused by {root_cause}. Fixed by {fix}.",
    "PR #{n}: {feature} — merged after {reviews} reviews. Key change: {change}.",
    "Performance insight: {component} bottleneck is {bottleneck}, improved by {improvement}.",
    "User {user} preference: {pref}. Priority: {priority}.",
    "API contract: {endpoint} accepts {input} and returns {output}.",
    "Security note: {asset} requires {protection} to prevent {threat}.",
    "Deployment: {service} runs on {infra} with {config} configuration.",
    "Test coverage: {module} has {coverage}% coverage. Missing: {missing}.",
    "Dependency: {lib} v{version} chosen over {alt} for {reason}.",
]

_TECH_WORDS = [
    "PostgreSQL", "Redis", "FastAPI", "Pydantic", "Docker", "Kubernetes",
    "Rust", "PyO3", "FAISS", "pgvector", "SQLite", "nginx", "Prometheus",
    "GraphQL", "gRPC", "OAuth2", "JWT", "S3", "Kafka", "Celery",
]

_QUERIES = [
    "database choice for production",
    "authentication middleware implementation",
    "payment retry logic bug fix",
    "performance bottleneck in the API layer",
    "user preferences and settings",
    "how do we handle rate limiting",
    "deployment configuration for staging",
    "test coverage gaps in the auth module",
    "Rust scoring engine architecture",
    "vector index maintenance strategy",
    "multi-tenant namespace isolation",
    "connection pooling configuration",
    "PR history for the memory layer",
    "error handling in background workers",
    "caching strategy for embeddings",
]


def _make_memory(i: int) -> str:
    template = _MEMORY_TEMPLATES[i % len(_MEMORY_TEMPLATES)]
    tech = random.choice(_TECH_WORDS)
    return template.format(
        topic=f"topic_{i % 50}",
        tech=tech,
        reason=f"reason_{i % 20}",
        module=f"module_{i % 30}",
        symptom=f"symptom_{i % 15}",
        root_cause=f"root_cause_{i % 10}",
        fix=f"fix_{i % 10}",
        n=1000 + i,
        feature=f"feature_{i % 40}",
        reviews=random.randint(1, 5),
        change=f"change_{i % 25}",
        component=f"component_{i % 20}",
        bottleneck=f"bottleneck_{i % 8}",
        improvement=f"improvement_{i % 8}",
        user=f"user_{i % 100}",
        pref=f"preference_{i % 30}",
        priority=random.choice(["high", "medium", "low"]),
        endpoint=f"/api/v1/endpoint_{i % 20}",
        input=f"input_schema_{i % 10}",
        output=f"output_schema_{i % 10}",
        asset=f"asset_{i % 15}",
        protection=f"protection_{i % 8}",
        threat=f"threat_{i % 8}",
        service=f"service_{i % 10}",
        infra=tech,
        config=f"config_{i % 5}",
        module_=f"module_{i % 20}",
        coverage=random.randint(40, 95),
        missing=f"missing_{i % 10}",
        lib=tech,
        version=f"{random.randint(1,4)}.{random.randint(0,9)}.{random.randint(0,9)}",
        alt=random.choice(_TECH_WORDS),
    )


# ─────────────────────────────────────────────────────────────────────────────
# OMem benchmark
# ─────────────────────────────────────────────────────────────────────────────

def _get_rss_mb() -> float:
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return 0.0


def benchmark_omem(
    n_memories: int = 5000,
    n_queries: int = 500,
    db_path: str = "/tmp/omem_bench.db",
    verbose: bool = True,
) -> Dict[str, Any]:
    from omem import OMem

    if verbose:
        print("\n── OMem Benchmark ─────────────────────────────────────────────")
        print(f"   memories={n_memories}  queries={n_queries}  db={db_path}")

    rss_before = _get_rss_mb()

    # ── Cold start ────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    brain = OMem(db_path=db_path)
    cold_add = time.perf_counter() - t0
    cold_add_ms = cold_add * 1000

    t0 = time.perf_counter()
    brain.add("cold start test memory", importance=0.5)
    cold_recall = (time.perf_counter() - t0) * 1000

    if verbose:
        print(f"   cold_add={cold_add_ms:.1f}ms  cold_recall={cold_recall:.1f}ms")

    # ── Add throughput ────────────────────────────────────────────────────────
    memories = [_make_memory(i) for i in range(n_memories)]
    t0 = time.perf_counter()
    for i, content in enumerate(memories):
        brain.add(content, importance=round(0.3 + (i % 7) * 0.1, 1), namespace="bench")
    add_elapsed = time.perf_counter() - t0
    add_ops_per_sec = n_memories / add_elapsed

    if verbose:
        print(f"   add: {n_memories} ops in {add_elapsed:.2f}s → {add_ops_per_sec:.0f} ops/s")

    # ── RAG latency ───────────────────────────────────────────────────────────
    queries = [_QUERIES[i % len(_QUERIES)] for i in range(n_queries)]
    rag_times: List[float] = []
    hits = 0

    for q in queries:
        t0 = time.perf_counter()
        results = brain.recall(q, k=5, namespace="bench", mode="coding")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        rag_times.append(elapsed_ms)
        if results:
            hits += 1

    p50 = statistics.median(rag_times)
    p95 = sorted(rag_times)[int(len(rag_times) * 0.95)]
    p99 = sorted(rag_times)[int(len(rag_times) * 0.99)]
    mean = statistics.mean(rag_times)

    rss_after = _get_rss_mb()
    rss_delta = rss_after - rss_before

    if verbose:
        print(f"   rag: p50={p50:.1f}ms  p95={p95:.1f}ms  p99={p99:.1f}ms  mean={mean:.1f}ms")
        print(f"   recall_rate={hits/n_queries*100:.1f}%  rss_delta={rss_delta:.0f}MB")

    # Cleanup
    try:
        os.remove(db_path)
    except FileNotFoundError:
        pass

    return {
        "system": "OMem",
        "n_memories": n_memories,
        "n_queries": n_queries,
        "cold_start_ms": round(cold_add_ms, 2),
        "cold_recall_ms": round(cold_recall, 2),
        "add_ops_per_sec": round(add_ops_per_sec, 1),
        "rag_p50_ms": round(p50, 2),
        "rag_p95_ms": round(p95, 2),
        "rag_p99_ms": round(p99, 2),
        "rag_mean_ms": round(mean, 2),
        "recall_rate_pct": round(hits / n_queries * 100, 1),
        "rss_delta_mb": round(rss_delta, 1),
        "cost_per_1m_recalls_usd": 0.0,
        "requires_api_key": False,
        "local_embeddings": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Mem0 benchmark — live (requires pip install mem0ai + OPENAI_API_KEY)
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_mem0_live(
    n_memories: int = 100,
    n_queries: int = 50,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run a live Mem0 benchmark. Requires mem0ai and OPENAI_API_KEY."""
    try:
        from mem0 import Memory as Mem0Memory
    except ImportError:
        raise ImportError("mem0ai not installed: pip install mem0ai")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY environment variable not set.")

    if verbose:
        print("\n── Mem0 Live Benchmark ────────────────────────────────────────")
        print(f"   memories={n_memories}  queries={n_queries}  (requires API calls)")

    # Cost estimate for the configured OpenAI-backed comparison.
    OPENAI_INPUT_PRICE_PER_1M  = 0.005   # gpt-4o-mini input $/1M tokens (Jun 2026)
    OPENAI_OUTPUT_PRICE_PER_1M = 0.015
    AVG_TOKENS_PER_RECALL      = 1500    # ~500 input + 1000 output for LLM re-ranking

    # Cold start
    t0 = time.perf_counter()
    m = Mem0Memory()
    cold_start_ms = (time.perf_counter() - t0) * 1000

    memories = [_make_memory(i) for i in range(n_memories)]
    user_id = f"bench_user_{int(time.time())}"

    # Add throughput
    t0 = time.perf_counter()
    for content in memories:
        m.add(content, user_id=user_id)
    add_elapsed = time.perf_counter() - t0
    add_ops_per_sec = n_memories / add_elapsed

    # RAG latency
    queries = [_QUERIES[i % len(_QUERIES)] for i in range(n_queries)]
    rag_times: List[float] = []
    hits = 0

    for q in queries:
        t0 = time.perf_counter()
        results = m.search(q, user_id=user_id, limit=5)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        rag_times.append(elapsed_ms)
        if results:
            hits += 1

    p50 = statistics.median(rag_times)
    p95 = sorted(rag_times)[int(len(rag_times) * 0.95)]
    p99 = sorted(rag_times)[int(len(rag_times) * 0.99)]

    cost_per_1m = (
        (AVG_TOKENS_PER_RECALL / 1e6) * OPENAI_INPUT_PRICE_PER_1M * 500_000
        + (AVG_TOKENS_PER_RECALL / 1e6) * OPENAI_OUTPUT_PRICE_PER_1M * 500_000
    )

    if verbose:
        print(f"   add: {n_memories} ops in {add_elapsed:.2f}s → {add_ops_per_sec:.1f} ops/s")
        print(f"   rag: p50={p50:.1f}ms  p95={p95:.1f}ms  p99={p99:.1f}ms")

    return {
        "system": "Mem0",
        "n_memories": n_memories,
        "n_queries": n_queries,
        "cold_start_ms": round(cold_start_ms, 2),
        "add_ops_per_sec": round(add_ops_per_sec, 2),
        "rag_p50_ms": round(p50, 2),
        "rag_p95_ms": round(p95, 2),
        "rag_p99_ms": round(p99, 2),
        "recall_rate_pct": round(hits / n_queries * 100, 1),
        "cost_per_1m_recalls_usd": round(cost_per_1m, 2),
        "requires_api_key": True,
        "local_embeddings": False,
        "live": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Mem0 modeled baseline (no API key required)
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_mem0_model(n_memories: int = 5000, n_queries: int = 500) -> Dict[str, Any]:
    """
    Modeled Mem0 performance based on:
      1. OMem competitor.py measurements (benchmarks/competitor.py)
      2. Mem0 published documentation latency characteristics
      3. OpenAI API typical round-trip times (100–800ms per call)

    This baseline represents an LLM-backed extraction/scoring configuration.
    It is not a claim that every Mem0 deployment or version uses the same calls.
    With gpt-4o-mini at typical network conditions, the values used here are:
      - cold start:  ~15,000ms  (model load + first API call)
      - add ops/s:   <1          (API-bound, ~800-1500ms per add)
      - RAG p99:     ~638ms      (documented in benchmarks/competitor.py)
    """
    OPENAI_INPUT_PRICE_PER_1M  = 0.005
    OPENAI_OUTPUT_PRICE_PER_1M = 0.015
    AVG_TOKENS_PER_RECALL = 1500
    cost_per_1m = (AVG_TOKENS_PER_RECALL / 1e6) * (
        OPENAI_INPUT_PRICE_PER_1M + OPENAI_OUTPUT_PRICE_PER_1M
    ) * 1_000_000

    return {
        "system": "Mem0 (modeled — from competitor.py measurements)",
        "n_memories": n_memories,
        "n_queries": n_queries,
        "cold_start_ms": 15_000.0,
        "cold_recall_ms": 638.0,
        "add_ops_per_sec": 0.67,          # ~1,500ms per add with LLM extraction
        "rag_p50_ms": 420.0,
        "rag_p95_ms": 580.0,
        "rag_p99_ms": 638.0,
        "recall_rate_pct": 72.0,          # LLM extraction can miss/hallucinate
        "rss_delta_mb": 45.0,
        "cost_per_1m_recalls_usd": round(cost_per_1m, 2),
        "requires_api_key": True,
        "local_embeddings": False,
        "live": False,
        "note": (
            "Modeled from OMem competitor.py measurements and Mem0 architecture. "
            "Run with --live-mem0 for actual measurements (requires OPENAI_API_KEY)."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

def print_comparison(omem_r: Dict, mem0_r: Dict) -> None:
    def speedup(omem_val: float, mem0_val: float) -> str:
        if omem_val <= 0:
            return "N/A"
        ratio = mem0_val / omem_val
        return f"{ratio:.0f}×"

    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"

    print(f"\n{BOLD}{CYAN}{'═' * 72}{RESET}")
    print(f"{BOLD}{CYAN}  OMem vs Mem0 — Benchmark Results{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 72}{RESET}")
    print(f"  Memories: {omem_r['n_memories']:,}   Queries: {omem_r['n_queries']:,}")
    print()

    rows = [
        ("Metric",              "OMem",                              "Mem0",                              "Speedup"),
        ("─" * 30,              "─" * 16,                           "─" * 16,                            "─" * 10),
        ("Cold start",
            f"{omem_r['cold_start_ms']:.1f} ms",
            f"{mem0_r['cold_start_ms']:,.0f} ms",
            speedup(omem_r['cold_start_ms'], mem0_r['cold_start_ms'])),
        ("Add throughput",
            f"{omem_r['add_ops_per_sec']:.0f} ops/s",
            f"{mem0_r['add_ops_per_sec']:.1f} ops/s",
            speedup(1/max(omem_r['add_ops_per_sec'], 0.001), 1/max(mem0_r['add_ops_per_sec'], 0.001))),
        ("RAG p50 latency",
            f"{omem_r['rag_p50_ms']:.1f} ms",
            f"{mem0_r['rag_p50_ms']:.0f} ms",
            speedup(omem_r['rag_p50_ms'], mem0_r['rag_p50_ms'])),
        ("RAG p95 latency",
            f"{omem_r['rag_p95_ms']:.1f} ms",
            f"{mem0_r['rag_p95_ms']:.0f} ms",
            speedup(omem_r['rag_p95_ms'], mem0_r['rag_p95_ms'])),
        ("RAG p99 latency",
            f"{omem_r['rag_p99_ms']:.1f} ms",
            f"{mem0_r['rag_p99_ms']:.0f} ms",
            speedup(omem_r['rag_p99_ms'], mem0_r['rag_p99_ms'])),
        ("Recall rate",
            f"{omem_r['recall_rate_pct']:.1f}%",
            f"{mem0_r['recall_rate_pct']:.1f}%",
            ""),
        ("Est. API fees / 1M recalls",
            f"${omem_r['cost_per_1m_recalls_usd']:.2f}",
            f"${mem0_r['cost_per_1m_recalls_usd']:.2f}",
            ""),
        ("Requires API key",
            "No",
            "Yes (OpenAI)",
            ""),
        ("Local embeddings",
            "Yes",
            "No",
            ""),
    ]

    for row in rows:
        label, omem_val, mem0_val, sp = row
        sp_str = f"  {GREEN}{BOLD}{sp}{RESET}" if sp and "×" in sp else (f"  {sp}" if sp else "")
        print(f"  {label:<30}  {omem_val:<16}  {mem0_val:<16}{sp_str}")

    print(f"\n{BOLD}{GREEN}  Configuration comparison:{RESET}")
    cold_ratio = mem0_r['cold_start_ms'] / max(omem_r['cold_start_ms'], 0.1)
    p99_ratio  = mem0_r['rag_p99_ms']   / max(omem_r['rag_p99_ms'],   0.1)
    print(f"  {GREEN}•{RESET} Cold-start latency ratio: {cold_ratio:.0f}×")
    print(f"  {GREEN}•{RESET} p99 recall latency ratio: {p99_ratio:.0f}×")
    print(f"  {GREEN}•{RESET} OMem local path: $0 required third-party API fees")
    print(f"  {GREEN}•{RESET} Works offline — air-gapped environments, edge deployments")
    print(f"  {GREEN}•{RESET} Local infrastructure costs are not included")
    if not mem0_r.get("live", False):
        print(f"  {YELLOW}•{RESET} Mem0 values are modeled; use --live-mem0 for a live run")
    print()
    if mem0_r.get("note"):
        print(f"  {YELLOW}Note:{RESET} {mem0_r['note']}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="OMem vs Mem0 benchmark")
    parser.add_argument("--memories",   type=int,  default=5000, help="Memories to ingest")
    parser.add_argument("--queries",    type=int,  default=500,  help="Recall queries to run")
    parser.add_argument("--live-mem0",  action="store_true",     help="Run live Mem0 benchmark")
    parser.add_argument("--json",       action="store_true",     help="JSON output to stdout")
    parser.add_argument("--out",        type=str,  default="distribution/benchmark_results.json",
                        help="JSON output file path")
    args = parser.parse_args()

    random.seed(42)

    # ── OMem ──────────────────────────────────────────────────────────────────
    omem_result = benchmark_omem(
        n_memories=args.memories,
        n_queries=args.queries,
        verbose=not args.json,
    )

    # ── Mem0 ──────────────────────────────────────────────────────────────────
    if args.live_mem0:
        try:
            mem0_result = benchmark_mem0_live(
                n_memories=min(args.memories, 200),
                n_queries=min(args.queries, 100),
                verbose=not args.json,
            )
        except (ImportError, RuntimeError) as e:
            print(f"Live Mem0 benchmark unavailable: {e}", file=sys.stderr)
            print("Falling back to modeled baseline.", file=sys.stderr)
            mem0_result = benchmark_mem0_model(args.memories, args.queries)
    else:
        mem0_result = benchmark_mem0_model(args.memories, args.queries)

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "omem": omem_result,
        "mem0": mem0_result,
        "speedups": {
            "cold_start":    round(mem0_result["cold_start_ms"]   / max(omem_result["cold_start_ms"],   0.01), 1),
            "rag_p99":       round(mem0_result["rag_p99_ms"]      / max(omem_result["rag_p99_ms"],      0.01), 1),
            "add_throughput": round(omem_result["add_ops_per_sec"] / max(mem0_result["add_ops_per_sec"], 0.01), 1),
            "api_fee_comparison": "OMem local path requires no third-party API fees",
        },
    }

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_comparison(omem_result, mem0_result)

    # Write JSON file
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    if not args.json:
        print(f"  Results written to {out_path}")


if __name__ == "__main__":
    main()
