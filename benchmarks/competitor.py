"""
Competitor Comparison Framework - head-to-head benchmarks against Mem0, ChromaDB, LanceDB.

Provides a standardised harness that benchmarks OMem against competitors
on identical workloads. Competitors are optional - if not installed, their
columns show "N/A" instead of failing.

Metrics compared:
- Setup time (cold start)
- Add throughput (ops/s)
- Query latency (p50/p95/p99)
- Memory footprint (RSS delta)
- Feature completeness score

Fix log:
  [1] KMP_DUPLICATE_LIB_OK set programmatically — no prefix needed.
  [2] OMem: recall() uses k=, not top_k=.
  [3] Mem0: skips gracefully if OPENAI_API_KEY missing; tries local config first.
  [4] ChromaDB + LanceDB: now use the same all-MiniLM-L6-v2 embeddings as OMem.
      All competitors process raw text strings, not pre-computed random vectors.
  [5] time.sleep(1) between runs for OS settle; gc.collect() before + after every run.
  [6] RSS memory improved: tracemalloc peak used as fallback when RSS delta is zero.
"""

import gc
import os
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# ── Fix [1]: Handle OpenMP duplicate lib conflict programmatically ──────────
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

# ── Shared embedding model (Fix [4]) ────────────────────────────────────────
# All competitors embed using the same model so the comparison is apples-to-apples.
_SHARED_EMBEDDER = None
_SHARED_EMBEDDER_MB = (
    0.0  # baseline memory of the model itself (subtracted from all results)
)


def _get_shared_embedder():
    """Lazy-load the shared embedding model once across all competitors."""
    global _SHARED_EMBEDDER, _SHARED_EMBEDDER_MB
    if _SHARED_EMBEDDER is None:
        import tracemalloc

        tracemalloc.start()
        from omem.core.retrieval.embeddings import Embedder

        _SHARED_EMBEDDER = Embedder("all-MiniLM-L6-v2")
        # Warm up so model weights are fully loaded into RAM
        _SHARED_EMBEDDER.encode("warmup")
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        _SHARED_EMBEDDER_MB = peak / (1024 * 1024)
        print(
            f"  [Shared embedder loaded: {_SHARED_EMBEDDER_MB:.1f} MB — excluded from all competitor results]"
        )
    return _SHARED_EMBEDDER


# ── Result type ──────────────────────────────────────────────────────────────


@dataclass
class CompetitorResult:
    name: str
    available: bool
    setup_ms: float = 0.0
    add_ops_per_s: float = 0.0
    add_p50_ms: float = 0.0
    add_p99_ms: float = 0.0
    rag_ops_per_s: float = 0.0
    rag_p50_ms: float = 0.0
    rag_p95_ms: float = 0.0
    rag_p99_ms: float = 0.0
    memory_mb: float = 0.0
    features: Dict[str, bool] = field(default_factory=dict)
    error: str = ""


def _percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = int(len(s) * p / 100.0)
    return s[min(k, len(s) - 1)]


# ── Fix [6]: Improved memory measurement ─────────────────────────────────────


def _get_rss_mb() -> float:
    """Get current RSS in MB. Falls back to 0 on unsupported platforms."""
    try:
        import resource

        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS returns bytes, Linux returns kilobytes
        return raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024
    except Exception:
        return 0.0


def _measure_peak_mb(fn: Callable) -> tuple:
    """Run fn(), return (result, peak_memory_mb).
    Uses both RSS delta and tracemalloc peak — takes the larger of the two.
    """
    gc.collect()
    rss_before = _get_rss_mb()

    tracemalloc.start()
    result = fn()
    _, peak_traced = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    gc.collect()
    rss_after = _get_rss_mb()

    rss_delta_mb = max(rss_after - rss_before, 0.0)
    traced_mb = peak_traced / (1024 * 1024)

    # Use whichever is more informative
    memory_mb = max(rss_delta_mb, traced_mb)
    return result, memory_mb


# ── Shared workload ───────────────────────────────────────────────────────────


def _make_workload(n: int) -> List[str]:
    """Generate the shared text corpus used by all competitors."""
    return [
        f"Benchmark entry {i}: domain knowledge area {i % 100}, subtopic {i % 50}"
        for i in range(n)
    ]


def _make_queries(n_queries: int) -> List[str]:
    """Generate the shared query set used by all competitors."""
    return [
        f"domain knowledge area {i % 100} subtopic {i % 50}" for i in range(n_queries)
    ]


# ── OMem benchmark ────────────────────────────────────────────────────────────


def _bench_omem(corpus: List[str], queries: List[str]) -> CompetitorResult:
    # Pre-load shared embedder so OMem reuses it — no double model loading
    embedder = _get_shared_embedder()

    def run():
        # Patch OMem to use the already-loaded shared embedder
        from omem import OMem

        t0 = time.perf_counter()
        m = OMem(backend="memory")
        # Replace the internal embedder with the pre-loaded shared one to avoid double-load
        m.brain.embedder = embedder
        setup_ms = (time.perf_counter() - t0) * 1000

        # --- Individual add (Smart Ingestion mode) ---
        add_latencies = []
        for content in corpus:
            t0 = time.perf_counter()
            m.add(content)
            add_latencies.append((time.perf_counter() - t0) * 1000)

        add_total = sum(add_latencies) / 1000.0

        # --- Recall (k=, not top_k=) ---
        rag_latencies = []
        for q in queries:
            t0 = time.perf_counter()
            m.recall(q, k=5)
            rag_latencies.append((time.perf_counter() - t0) * 1000)

        rag_total = sum(rag_latencies) / 1000.0
        return setup_ms, add_latencies, add_total, rag_latencies, rag_total

    (setup_ms, add_latencies, add_total, rag_latencies, rag_total), mem_mb = (
        _measure_peak_mb(run)
    )
    # Subtract shared embedder baseline — OMem's overhead only
    mem_mb = max(mem_mb - _SHARED_EMBEDDER_MB, 0.0)
    n, n_q = len(corpus), len(queries)

    return CompetitorResult(
        name="OMem",
        available=True,
        setup_ms=setup_ms,
        add_ops_per_s=n / add_total if add_total > 0 else 0,
        add_p50_ms=_percentile(add_latencies, 50),
        add_p99_ms=_percentile(add_latencies, 99),
        rag_ops_per_s=n_q / rag_total if rag_total > 0 else 0,
        rag_p50_ms=_percentile(rag_latencies, 50),
        rag_p95_ms=_percentile(rag_latencies, 95),
        rag_p99_ms=_percentile(rag_latencies, 99),
        memory_mb=mem_mb,
        features={
            "memory_categories": True,
            "auto_classification": True,
            "hybrid_rag": True,
            "causal_graphs": True,
            "zero_config": True,
            "cli_tools": True,
            "pluggable_backends": True,
            "compression": True,
            "reflection": True,
        },
    )


# ── OMem add throughput note ──────────────────────────────────────────────────
# OMem's add() does: embed + classify + dedup-check + entity-extract + graph-link + persist.
# This is "Smart Ingestion" — not raw storage. Compare fairly by noting what each system does:
#   ChromaDB add = store pre-computed vector → disk write only
#   LanceDB  add = bulk-insert pre-computed vectors (no per-item overhead)
#   OMem     add = embed + classify + dedup + knowledge-graph + async persist
# For bulk loads, use OMem.add_batch() which pipelines embedding computation.


# ── ChromaDB benchmark ────────────────────────────────────────────────────────


def _bench_chromadb(corpus: List[str], queries: List[str]) -> CompetitorResult:
    try:
        import chromadb  # type: ignore
    except ImportError:
        return CompetitorResult(
            name="ChromaDB",
            available=False,
            error="not installed — pip install chromadb",
        )

    embedder = _get_shared_embedder()  # Fix [4]: same embedder as OMem

    def run():
        t0 = time.perf_counter()
        client = chromadb.Client()
        collection = client.create_collection(
            "benchmark",
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # we supply vectors directly
        )
        setup_ms = (time.perf_counter() - t0) * 1000

        # Pre-compute embeddings (same model as OMem)
        add_latencies = []
        for i, content in enumerate(corpus):
            vec = embedder.encode(content).tolist()
            t0 = time.perf_counter()
            collection.add(
                embeddings=[vec],
                documents=[content],
                ids=[f"id-{i}"],
            )
            add_latencies.append((time.perf_counter() - t0) * 1000)

        add_total = sum(add_latencies) / 1000.0

        rag_latencies = []
        for q in queries:
            qvec = embedder.encode(q).tolist()
            t0 = time.perf_counter()
            collection.query(query_embeddings=[qvec], n_results=5)
            rag_latencies.append((time.perf_counter() - t0) * 1000)

        rag_total = sum(rag_latencies) / 1000.0
        return setup_ms, add_latencies, add_total, rag_latencies, rag_total

    try:
        (setup_ms, add_latencies, add_total, rag_latencies, rag_total), mem_mb = (
            _measure_peak_mb(run)
        )
    except Exception as e:
        return CompetitorResult(name="ChromaDB", available=False, error=str(e))

    n, n_q = len(corpus), len(queries)
    return CompetitorResult(
        name="ChromaDB",
        available=True,
        setup_ms=setup_ms,
        add_ops_per_s=n / add_total if add_total > 0 else 0,
        add_p50_ms=_percentile(add_latencies, 50),
        add_p99_ms=_percentile(add_latencies, 99),
        rag_ops_per_s=n_q / rag_total if rag_total > 0 else 0,
        rag_p50_ms=_percentile(rag_latencies, 50),
        rag_p95_ms=_percentile(rag_latencies, 95),
        rag_p99_ms=_percentile(rag_latencies, 99),
        memory_mb=mem_mb,
        features={
            "memory_categories": False,
            "auto_classification": False,
            "hybrid_rag": False,
            "causal_graphs": False,
            "zero_config": True,
            "cli_tools": False,
            "pluggable_backends": False,
            "compression": False,
            "reflection": False,
        },
    )


# ── Mem0 benchmark ────────────────────────────────────────────────────────────


def _bench_mem0(corpus: List[str], queries: List[str]) -> CompetitorResult:
    """Mem0 benchmark.

    Mem0 requires an LLM for its extraction pipeline.
    Priority order:
      1. Local Ollama (llama3) + ChromaDB — no API key needed
      2. OpenAI (OPENAI_API_KEY in env) + ChromaDB
      3. Skip with clear instructions
    """
    try:
        from mem0 import Memory  # type: ignore
    except ImportError:
        return CompetitorResult(
            name="Mem0", available=False, error="not installed — pip install mem0ai"
        )

    has_openai_key = bool(os.environ.get("OPENAI_API_KEY"))

    # Try Ollama first (no API key needed)
    ollama_config = {
        "embedder": {
            "provider": "huggingface",
            "config": {"model": "all-MiniLM-L6-v2"},
        },
        "llm": {
            "provider": "ollama",
            "config": {"model": "llama3", "temperature": 0},
        },
        "vector_store": {
            "provider": "chroma",
            "config": {"collection_name": "mem0_bench", "path": "/tmp/mem0_bench"},
        },
    }

    # OpenAI fallback
    openai_config = {
        "embedder": {
            "provider": "huggingface",
            "config": {"model": "all-MiniLM-L6-v2"},
        },
        "llm": {
            "provider": "openai",
            "config": {"model": "gpt-4o-mini", "temperature": 0},
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "mem0_bench_oai",
                "path": "/tmp/mem0_bench_oai",
            },
        },
    }

    def run():
        t0 = time.perf_counter()
        mem = None
        backend_used = ""

        # Try Ollama
        try:
            mem = Memory.from_config(ollama_config)
            # Probe with one call to verify Ollama is actually running
            mem.add("probe", user_id="probe")
            backend_used = "Ollama/llama3"
        except Exception:
            mem = None

        # Fall back to OpenAI
        if mem is None and has_openai_key:
            try:
                mem = Memory.from_config(openai_config)
                backend_used = "OpenAI/gpt-4o-mini"
            except Exception as e:
                raise RuntimeError(f"OpenAI config failed: {e}")

        if mem is None:
            raise RuntimeError(
                "Mem0 needs either:\n"
                "    • Ollama running locally:  ollama pull llama3 && ollama serve\n"
                "    • OpenAI API key:           export OPENAI_API_KEY=sk-..."
            )

        setup_ms = (time.perf_counter() - t0) * 1000
        print(f"    [Mem0 backend: {backend_used}]")

        sample = corpus[
            :200
        ]  # Mem0 extraction is slow; cap to keep benchmark time reasonable
        add_latencies = []
        for content in sample:
            t0 = time.perf_counter()
            mem.add(content, user_id="bench")
            add_latencies.append((time.perf_counter() - t0) * 1000)

        add_total = sum(add_latencies) / 1000.0

        q_sample = queries[:50]
        rag_latencies = []
        for q in q_sample:
            t0 = time.perf_counter()
            mem.search(q, user_id="bench", limit=5)
            rag_latencies.append((time.perf_counter() - t0) * 1000)

        rag_total = sum(rag_latencies) / 1000.0
        return setup_ms, add_latencies, add_total, rag_latencies, rag_total

    try:
        (setup_ms, add_latencies, add_total, rag_latencies, rag_total), mem_mb = (
            _measure_peak_mb(run)
        )
    except Exception as e:
        return CompetitorResult(name="Mem0", available=False, error=str(e))

    n, n_q = len(add_latencies), len(rag_latencies)
    return CompetitorResult(
        name="Mem0",
        available=True,
        setup_ms=setup_ms,
        add_ops_per_s=n / add_total if add_total > 0 else 0,
        add_p50_ms=_percentile(add_latencies, 50),
        add_p99_ms=_percentile(add_latencies, 99),
        rag_ops_per_s=n_q / rag_total if rag_total > 0 else 0,
        rag_p50_ms=_percentile(rag_latencies, 50),
        rag_p95_ms=_percentile(rag_latencies, 95),
        rag_p99_ms=_percentile(rag_latencies, 99),
        memory_mb=mem_mb,
        features={
            "memory_categories": False,
            "auto_classification": False,
            "hybrid_rag": False,
            "causal_graphs": False,
            "zero_config": False,
            "cli_tools": False,
            "pluggable_backends": True,
            "compression": False,
            "reflection": False,
        },
    )


# ── LanceDB benchmark ─────────────────────────────────────────────────────────


def _bench_lancedb(corpus: List[str], queries: List[str]) -> CompetitorResult:
    try:
        import lancedb  # type: ignore
        import pyarrow as pa  # type: ignore
    except ImportError:
        return CompetitorResult(
            name="LanceDB",
            available=False,
            error="not installed — pip install lancedb pyarrow",
        )

    import tempfile

    embedder = (
        _get_shared_embedder()
    )  # Fix [4]: same embedder as OMem, no random vectors
    DIM = embedder.dim

    def run():
        tmpdir = tempfile.mkdtemp()
        t0 = time.perf_counter()
        db = lancedb.connect(os.path.join(tmpdir, "bench.lance"))
        setup_ms = (time.perf_counter() - t0) * 1000

        # Pre-compute all embeddings using the shared model
        print("    [LanceDB] Pre-computing embeddings with all-MiniLM-L6-v2...")
        vecs = embedder.encode_batch(corpus)  # (N, DIM) float32

        # Build the table in one shot (LanceDB is optimised for bulk inserts)
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), DIM)),
            ]
        )
        data = pa.table(
            {
                "id": [f"id-{i}" for i in range(len(corpus))],
                "text": corpus,
                "vector": vecs.tolist(),
            },
            schema=schema,
        )

        t0 = time.perf_counter()
        table = db.create_table("benchmark", data=data)
        add_total = time.perf_counter() - t0
        add_latency_per_op = (add_total / len(corpus)) * 1000  # per-item ms

        rag_latencies = []
        for q in queries:
            qvec = embedder.encode(q).tolist()
            t0 = time.perf_counter()
            table.search(qvec).limit(5).to_list()
            rag_latencies.append((time.perf_counter() - t0) * 1000)

        rag_total = sum(rag_latencies) / 1000.0
        return setup_ms, add_total, add_latency_per_op, rag_latencies, rag_total

    try:
        (setup_ms, add_total, add_lat_per_op, rag_latencies, rag_total), mem_mb = (
            _measure_peak_mb(run)
        )
    except Exception as e:
        return CompetitorResult(name="LanceDB", available=False, error=str(e))

    n, n_q = len(corpus), len(queries)
    return CompetitorResult(
        name="LanceDB",
        available=True,
        setup_ms=setup_ms,
        add_ops_per_s=n / add_total if add_total > 0 else 0,
        add_p50_ms=add_lat_per_op,
        add_p99_ms=add_lat_per_op,
        rag_ops_per_s=n_q / rag_total if rag_total > 0 else 0,
        rag_p50_ms=_percentile(rag_latencies, 50),
        rag_p95_ms=_percentile(rag_latencies, 95),
        rag_p99_ms=_percentile(rag_latencies, 99),
        memory_mb=mem_mb,
        features={
            "memory_categories": False,
            "auto_classification": False,
            "hybrid_rag": False,
            "causal_graphs": False,
            "zero_config": True,
            "cli_tools": False,
            "pluggable_backends": False,
            "compression": False,
            "reflection": False,
        },
    )


# ── Comparison runner ─────────────────────────────────────────────────────────


def run_comparison(
    n: int = 5_000,
    n_queries: int = 500,
    competitors: Optional[List[str]] = None,
    verbose: bool = True,
) -> List[CompetitorResult]:
    """Run head-to-head comparison against available competitors.

    All competitors share:
      - Same text corpus (n entries)
      - Same query set (n_queries entries)
      - Same embedding model (all-MiniLM-L6-v2)
    """
    all_benches = {
        "omem": _bench_omem,
        "chromadb": _bench_chromadb,
        "mem0": _bench_mem0,
        "lancedb": _bench_lancedb,
    }

    if competitors is None:
        competitors = list(all_benches.keys())

    # Pre-generate the shared workload ONCE
    corpus = _make_workload(n)
    queries = _make_queries(n_queries)

    results: List[CompetitorResult] = []

    if verbose:
        print("=" * 90)
        print("  OMem Competitor Comparison — Head-to-Head Benchmark")
        print(f"  Dataset: {n:,} memories | Queries: {n_queries:,} | top_k=5")
        print("  Embedding model: all-MiniLM-L6-v2 (shared across all competitors)")
        print("=" * 90)

    for name in competitors:
        bench_fn = all_benches.get(name)
        if bench_fn is None:
            continue

        if verbose:
            print(f"\n{'─' * 40}")
            print(f"  Benchmarking {name.upper()}...")

        # Fix [5]: GC + OS settle before each run
        gc.collect()
        time.sleep(1)

        try:
            result = bench_fn(corpus, queries)
        except Exception as e:
            result = CompetitorResult(name=name, available=False, error=str(e))

        # Fix [5]: GC after each run
        gc.collect()

        results.append(result)

        if verbose:
            if result.available:
                print(f"  Setup:   {result.setup_ms:.1f} ms")
                print(
                    f"  Add:     {result.add_ops_per_s:,.0f} ops/s  "
                    f"(p50={result.add_p50_ms:.3f}ms  p99={result.add_p99_ms:.3f}ms)"
                )
                print(
                    f"  Recall:  {result.rag_ops_per_s:,.0f} ops/s  "
                    f"(p50={result.rag_p50_ms:.3f}ms  p95={result.rag_p95_ms:.3f}ms  "
                    f"p99={result.rag_p99_ms:.3f}ms)"
                )
                print(f"  Memory:  {result.memory_mb:.1f} MB")
            else:
                print(f"  ⚠ Skipped: {result.error}")

    if verbose:
        print("\n")
        _print_comparison_table(results)
        _print_feature_matrix(results)
        _print_speedup_summary(results)

    return results


# ── Pretty printing ───────────────────────────────────────────────────────────


def _print_comparison_table(results: List[CompetitorResult]) -> None:
    W = 95
    print("=" * W)
    print("  PERFORMANCE COMPARISON")
    print("=" * W)
    print(
        "  Note: OMem 'Add' includes: embed + auto-classify + dedup + entity-graph + async-persist"
    )
    print(
        "        ChromaDB/LanceDB 'Add' = store pre-computed vector only (raw storage)"
    )
    print(
        f"        Memory figures exclude the shared all-MiniLM-L6-v2 model ({_SHARED_EMBEDDER_MB:.0f} MB)"
    )
    print("─" * W)
    header = (
        f"{'System':<12} {'Setup':>8} | "
        f"{'Add ops/s':>10} {'Add p99':>9} | "
        f"{'RAG ops/s':>10} {'RAG p95':>9} {'RAG p99':>9} | "
        f"{'Mem MB':>7}"
    )
    print(header)
    print("─" * W)

    for r in results:
        if r.available:
            print(
                f"{r.name:<12} {r.setup_ms:>7.1f}ms | "
                f"{r.add_ops_per_s:>10,.0f} {r.add_p99_ms:>8.3f}ms | "
                f"{r.rag_ops_per_s:>10,.0f} {r.rag_p95_ms:>8.3f}ms {r.rag_p99_ms:>8.3f}ms | "
                f"{r.memory_mb:>6.1f}MB"
            )
        else:
            print(
                f"{r.name:<12} {'N/A':>8} | "
                f"{'N/A':>10} {'N/A':>9} | "
                f"{'N/A':>10} {'N/A':>9} {'N/A':>9} | "
                f"{'N/A':>7}"
            )
    print("─" * W)


def _print_speedup_summary(results: List[CompetitorResult]) -> None:
    omem = next((r for r in results if r.name.lower() == "omem" and r.available), None)
    if not omem:
        return

    print("\n  SPEEDUP vs OMem (RAG ops/s)")
    print("─" * 50)
    for r in results:
        if r.name.lower() == "omem" or not r.available or r.rag_ops_per_s == 0:
            continue
        speedup = omem.rag_ops_per_s / r.rag_ops_per_s
        direction = "faster" if speedup >= 1.0 else "slower"
        ratio = speedup if speedup >= 1.0 else 1 / speedup
        print(
            f"  OMem is {ratio:5.1f}× {direction} than {r.name:<10} "
            f"({omem.rag_ops_per_s:,.0f} vs {r.rag_ops_per_s:,.0f} ops/s)"
        )


def _print_feature_matrix(results: List[CompetitorResult]) -> None:
    available = [r for r in results if r.available and r.features]
    if not available:
        return

    all_features = sorted(set(f for r in available for f in r.features))

    print("\n  FEATURE MATRIX")
    print("─" * (26 + 13 * len(available)))
    print(f"  {'Feature':<25}", end="")
    for r in available:
        print(f"  {r.name:<11}", end="")
    print()
    print("─" * (26 + 13 * len(available)))

    for feat in all_features:
        print(f"  {feat:<25}", end="")
        for r in available:
            val = r.features.get(feat, False)
            mark = "✓" if val else "✗"
            print(f"  {mark:<11}", end="")
        print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_comparison()
