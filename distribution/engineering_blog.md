# How We Built a Local AI Memory OS with Rust and Hybrid Scoring

*Posted to HackerNews — Engineering · AI Infrastructure · Rust · Systems Programming*

---

Many AI memory systems use model calls for extraction, classification, or
ranking. OMem takes a different path: local embeddings, heuristic
classification, and multi-signal scoring accelerated with Rust and Rayon. This
post explains that architecture and the trade-off it makes: lower latency and
no required third-party API fees in exchange for heuristic rather than
LLM-based extraction.

The short version: **OMem's default path requires no LLM calls or API fees. In
our Apple M-series benchmark it measured 3.9 ms p99 local recall at 5,000
memories.**

---

## The Problem With LLM-Based Memory

The Mem0 configuration represented by our comparison uses an LLM-based
extraction/scoring pipeline. That is a different category of operation from
OMem's local heuristic path. Our default reproducible script models the Mem0
baseline from prior measurements and documented API-bound behavior; it does
not run Mem0 live unless invoked with `--live-mem0` and an API key. In that
modeled configuration:

- **Cold start: ~15,000ms** — the modeled value includes model initialization
  and a network-bound extraction request.
- **RAG p99: ~638ms** — the modeled scoring path includes a third-party request.
- **Estimated API cost: ~$0.02 per 1,000 recalls** — approximately $20/M,
  excluding infrastructure.
- **Data handling consideration:** content included in a model request leaves
  the local process and is governed by the configured provider's policies.

The modeled figures use prior `benchmarks/competitor.py` observations and
documented network/API characteristics. They are useful for comparing the
tested configurations, but they are not an apples-to-apples microbenchmark of
equivalent underlying operations. Run
`python distribution/benchmark_vs_mem0.py --live-mem0` to collect live Mem0
results in your own environment.

The LLM approach made sense when the only way to rank text was to ask a model. But in 2025, we have better tools.

---

## Our Architecture: Multi-Signal Heuristic Fusion

The core insight is that **memory relevance is a composite signal**, and you don't need a language model to compute it. You need:

1. **Semantic similarity** — is this memory about the same topic?
2. **Keyword overlap** — does this memory share specific tokens with the query?
3. **Recency** — was this memory created or accessed recently?
4. **Importance** — was this memory flagged as high-value when stored?
5. **Graph proximity** — is this memory connected to other relevant memories?
6. **Access frequency** — has the agent returned to this memory before?

We fuse all six signals with learned weights:

```
score = α·semantic + β·keyword + γ·recency + δ·importance + ε·confidence + ζ·graph
```

The weights are not fixed — they adapt based on the retrieval mode. A `coding` mode recall biases toward importance and keyword (architectural decisions use precise terminology). A `planning` mode recall weights recency and graph (what did we decide most recently, and what connects to it?).

This is not novel mathematics. What makes it practical at scale is **where we compute it**.

---

## The Rust Hot Path: `rag_score_batch`

The scoring function above needs to run against hundreds of candidate memories in milliseconds. Python's GIL makes true parallelism impossible here. NumPy helps, but you still pay Python dispatch overhead per candidate.

We wrote the hot path in Rust using [PyO3](https://pyo3.rs/) for the Python bridge and [Rayon](https://docs.rs/rayon) for work-stealing parallelism:

```rust
// rust/src/lib.rs — the actual production code

#[pyfunction]
fn rag_score_batch(
    query: PyReadonlyArray1<f32>,
    vectors: PyReadonlyArray2<f32>,
    base_scores: PyReadonlyArray1<f32>,
    recencies: PyReadonlyArray1<f32>,
    mem_types: PyReadonlyArray1<u8>,
    weights: Vec<f32>,
    type_boosts: Vec<f32>,
    top_k: usize,
) -> PyResult<Vec<(usize, f32)>> {
    let scores: Vec<f32> = (0..n)
        .into_par_iter()  // Rayon: work-stealing across all CPU cores
        .map(|i| {
            let vector = &flat[i * dim..(i + 1) * dim];
            score_memory_simd(query, vector, base[i], recency[i], types[i], &w, &boosts)
        })
        .collect();

    // Bounded min-heap: O(n log k) instead of O(n log n) full sort
    let mut heap: BinaryHeap<ScoredIndex> = BinaryHeap::with_capacity(top_k + 1);
    for (index, &score) in scores.iter().enumerate() {
        heap.push(ScoredIndex { index, score });
        if heap.len() > top_k { heap.pop(); }
    }
    // ...
}
```

The per-candidate scorer:

```rust
#[inline(always)]
pub fn score_memory_simd(
    query: &[f32],
    vector: &[f32],
    base_score: f32,
    recency: f32,
    mem_type: u8,
    weights: &[f32; 4],
    type_boosts: &[f32; 10],
) -> f32 {
    let mut dot = 0.0;
    for i in 0..query.len() {
        dot += query[i] * vector[i];
    }
    let t_boost = type_boosts[mem_type as usize];
    (dot * weights[0] + base_score * weights[1] + recency * weights[2]) * t_boost
}
```

A few architectural decisions worth explaining:

**Why Rayon over async Tokio?** Scoring is CPU-bound, not I/O-bound. Rayon's work-stealing thread pool saturates CPU cores without the overhead of async runtime scheduling. On an M2 with 8 performance cores, we get near-linear scaling up to the core count.

**Why a min-heap over sorting?** We only need the top-k results, not a fully sorted list. A bounded min-heap gives us O(n log k) instead of O(n log n). At n=5,000 and k=10, this is a 9× reduction in comparison operations.

**Why scalar dot products, not SIMD intrinsics?** LLVM's auto-vectorizer handles this correctly for packed f32 arrays when you compile with `target-cpu=native`. We tested hand-written AVX2 intrinsics and saw <2% improvement over the auto-vectorized version on Apple Silicon, which uses a different SIMD model. The readability cost wasn't worth it.

---

## BM25 in Rust: Keyword Scoring Without Elasticsearch

The semantic vector score handles conceptual similarity, but coding agents need exact token matching. If you stored a memory about "`PostgreSQL connection pooling`" and query for "`psycopg2 pool`", a semantic score might be low (different vocabulary) but a BM25 score will be high.

We implemented BM25 entirely in Rust with bigram tokenization:

```rust
fn lower_tokens(text: &str, stopwords: &HashSet<String>, ...) -> Vec<String> {
    // Unigrams + bigrams in a single pass
    let token_re = Regex::new(r"[a-z0-9]{2,}").unwrap();
    // ...
    for window in tokens.windows(2) {
        if let [first, second] = window {
            terms.push(format!("{} {}", first, second));
        }
    }
    terms
}

fn bm25_scores(documents: Vec<Vec<String>>, query: Vec<String>, k1: f32, b: f32) -> Vec<f32> {
    // Classic BM25 over document-frequency map
    // Parallelized via .into_par_iter() on the doc collection
}
```

The Python layer calls `omem_rust.bm25_scores()` with pre-tokenized documents. At N=5,000, this runs in ~0.08ms. The equivalent Python implementation with NLTK ran in ~1.2ms — a 15× speedup that matters when you're trying to stay under 4ms end-to-end.

---

## The Forgetting Engine: Keeping Memory Healthy

One dimension entirely absent from vector databases is the concept of **memory lifecycle**. A vector store will faithfully return a three-year-old outdated fact with perfect similarity — it has no concept of staleness.

We model memory health as:

```
health(m) = importance(m) × 2^(-age/half_life) × log₅(1 + access_count)
```

Memories with `health < archive_threshold` are demoted to cold storage. Memories with `health < delete_threshold` are purged. This runs in a background `sleep()` cycle via the Rust `sleep_cycle` function, which parallelizes health computation across all stored memories.

The practical effect: after a week of coding sessions, the agent's working memory contains the 500 most relevant facts, not the 50,000 raw observations it accumulated. This is the difference between an agent with good recall and one that spends its context window on noise.

---

## Heuristic Importance Scoring: Bypassing the LLM

The most expensive part of Mem0's architecture is calling an LLM to determine whether a memory is worth storing and how important it is. We replace this with a pattern-matching heuristic that runs in microseconds:

```rust
fn heuristic_score(content: String, triggers: Vec<(String, f32)>, ...) -> f32 {
    let text = content.to_lowercase();
    let mut multiplier = default_multiplier;
    for (pattern, weight) in triggers {
        let re = Regex::new(&pattern).unwrap();
        if re.is_match(&text) { multiplier *= weight; }
    }
    multiplier.clamp(0.0, 10.0)
}
```

The trigger patterns are learned heuristics:
- `"critical|bug|security|vulnerability"` → importance × 1.5
- `"note|fyi|reminder"` → importance × 0.6
- `"decision|chose|migration|refactor"` → importance × 1.4

These heuristics are not equivalent to model-based classification and the
benchmark does not establish classification-quality parity. Their advantage is
that they execute locally without required third-party API calls; applications
that need stronger semantic judgment should evaluate the optional embedding or
model-backed paths against their own data.

---

## The Python / Rust Boundary

One of the trickiest parts of this architecture is the PyO3 boundary. Every call from Python to Rust involves:

1. Python argument marshalling (numpy arrays → Rust slices via zero-copy)
2. Rust computation
3. Result marshalling back to Python

We minimize boundary crossings by batching. Rather than calling `rag_score_batch` once per candidate, we pass the entire candidate matrix in a single call. The numpy → `PyReadonlyArray2<f32>` path is zero-copy (no data is duplicated), so the overhead is purely the function call dispatch: ~0.2ms, paid once per recall.

The Python fallback (`rank_memories()` in `omem/core/retrieval/ranker.py`) runs when the Rust module is unavailable. It produces identical results but at 3-4× higher latency. We use this as a correctness oracle during development.

---

## Multi-Tenant Enterprise Architecture

When we began targeting enterprise customers — coding agent fleets at SaaS companies — single-tenant isolation became a hard requirement. An engineer at Acme Corp cannot, under any circumstances, see memories stored by an engineer at Initech.

We solved this at three layers:

**Application layer**: every memory has `org_id` and `user_id` fields. All queries include these in WHERE clauses.

**Database layer** (PostgreSQL RLS):
```sql
CREATE POLICY memories_tenant_rls ON memories
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (
        org_id  = current_setting('omem.org_id',  true)
        AND
        user_id = current_setting('omem.user_id', true)
    );
```

Before any query, the connection sets:
```sql
SET LOCAL omem.org_id  = 'acme-corp';
SET LOCAL omem.user_id = 'alice';
```

This means even if there is a bug in the application layer that forgets to include tenant filtering, the database policy blocks the query. Defense in depth.

**pgvector layer**: we use `pgvector/pgvector:pg16` in our enterprise Docker stack, enabling native `vector(384)` columns with IVFFlat approximate nearest-neighbor search. This replaces FAISS for cloud deployments and enables tenant-scoped ANN queries via standard SQL.

---

## The Numbers

On Apple M-series, 5,000 memories, 500 queries, `all-MiniLM-L6-v2` embeddings:

The OMem column is measured locally. Unless `--live-mem0` is used, the Mem0
column is a modeled baseline for an LLM-based extraction/scoring configuration.
Because the systems perform different operation pipelines, the ratios describe
these configurations rather than equivalent primitive operations.

| Metric | OMem (measured) | Mem0 (modeled default) | Ratio |
|---|---|---|---|
| Cold start | 4ms | 15,000ms | **3,750×** |
| Add throughput | 65 ops/s | <1 ops/s | **65×** |
| RAG p50 | 1.8ms | 420ms | **233×** |
| RAG p99 | 3.9ms | 638ms | **163×** |
| Third-party API fees / 1M recalls | $0 | ~$20 | — |
| API key required | No | Yes | — |

At the modeled rate of $20 per million recalls, 100,000 recalls/day is
approximately $60/month in third-party API fees. OMem's local path has no
third-party API fee, but its compute, storage, and operational costs are not
included here.

---

## What We Learned

**Use the least expensive method that meets the quality requirement.**
Importance classification, conflict detection, and entity extraction can use
fast pattern-based approximations, but their quality must be evaluated for the
target dataset. Reserve model calls for cases where the additional semantic
judgment justifies their latency and cost.

**Rayon is remarkably easy for this use case.** The scoring workload is embarrassingly parallel — no shared mutable state, fixed-size input, fixed-size output. Rayon's `par_iter()` adds parallelism in one line. The correctness story is straightforward because you're not coordinating anything.

**The PyO3 boundary is not the bottleneck.** We spent time worrying about the Python↔Rust call overhead and it turned out to be ~0.2ms, completely dominated by the actual computation. Don't pre-optimize this.

**Memory lifecycle is a product feature, not an afterthought.** Users don't want to manage when memories expire. Building automatic health-based forgetting into the core made OMem feel fundamentally different from "just another vector store."

---

## What's Next

We're working on:

1. **pgvector IVFFlat integration** — native database-side ANN for the enterprise stack, eliminating the Python FAISS dependency entirely.
2. **Multi-language AST indexing** — extending codebase memory beyond Python to TypeScript/Go/Rust.
3. **Federated memory** — allowing agent fleets at the same org to share a read-only "org memory" namespace while maintaining write isolation.

The code is open source: [github.com/mohitkumarrajbadi/omem](https://github.com/mohitkumarrajbadi/omem). Reproduce the local OMem run and modeled comparison with `python distribution/benchmark_vs_mem0.py`, or add `--live-mem0` for a live comparison.

If you're building AI agents and paying per-recall for memory, we'd like to show you a different path.

---

*Questions or corrections? `rust/src/lib.rs` contains the Rust implementation.
`distribution/benchmark_vs_mem0.py` documents which results are measured and
which are modeled.*
