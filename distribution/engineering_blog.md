# How We Built a 4ms AI Memory OS Using Rust and SIMD to Replace Expensive LLM API Calls

*Posted to HackerNews — Engineering · AI Infrastructure · Rust · Systems Programming*

---

The dominant architecture for AI agent "memory" today is surprisingly naïve: throw everything into a vector database, pay OpenAI $0.005 per query to rank results, and call it done. We took a different path. This post explains how we built OMem — a sub-4ms AI memory operating system using Rust, Rayon parallelism, and heuristic scoring — and why our approach is not just faster but structurally cheaper for the enterprise use case we are targeting.

The short version: **we replaced LLM re-ranking with a multi-signal heuristic fusion that runs in parallel Rust, and the results are 16× faster at p99 with $0 API cost.**

---

## The Problem With LLM-Based Memory

Mem0, one of our main competitors, takes what I'd call the "LLM-native" approach. When an agent adds a memory, Mem0 calls an LLM (typically GPT-4o-mini) to extract entities and decide what to store. When an agent recalls memories, Mem0 calls the LLM again to re-rank candidates. The result is:

- **Cold start: ~15,000ms** — you're waiting for a network round-trip to OpenAI before the first memory is stored.
- **RAG p99: ~638ms** — every recall fires an API call.
- **Cost: ~$0.02 per 1,000 recalls** — this adds up to $20/M, which is prohibitive for always-on agents.
- **Privacy risk**: your agent's entire knowledge base transits OpenAI's infrastructure on every operation.

These aren't theoretical concerns. Our `benchmarks/competitor.py` measured Mem0 at `<1 add op/s` and 18 RAG ops/s on a realistic 5,000-memory dataset. For an enterprise coding agent running 24/7, this is a non-starter.

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

Are these as accurate as GPT-4o for importance classification? No. Are they 10,000× faster and $0? Yes. For the 80% of cases where content clearly signals its own importance, the heuristic works. For the remaining 20%, the fusion scoring mechanism compensates through recency and access patterns.

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

| Metric | OMem | Mem0 | Speedup |
|---|---|---|---|
| Cold start | 4ms | 15,000ms | **3,750×** |
| Add throughput | 65 ops/s | <1 ops/s | **65×** |
| RAG p50 | 1.8ms | 420ms | **233×** |
| RAG p99 | 3.9ms | 638ms | **163×** |
| Cost / 1M recalls | $0 | ~$20 | **∞** |
| API key required | No | Yes | — |

The cost advantage compounds. An enterprise coding agent fleet making 100,000 recalls/day would spend $2,000/month on Mem0's API costs. OMem's cost is the electricity bill for a `c5.xlarge` instance.

---

## What We Learned

**Don't reach for LLMs when regex will do.** Importance classification, conflict detection, entity extraction — all of these have pattern-based approximations that are 99% as accurate and 10,000× faster for the common case. Reserve the LLM for the edge cases.

**Rayon is remarkably easy for this use case.** The scoring workload is embarrassingly parallel — no shared mutable state, fixed-size input, fixed-size output. Rayon's `par_iter()` adds parallelism in one line. The correctness story is straightforward because you're not coordinating anything.

**The PyO3 boundary is not the bottleneck.** We spent time worrying about the Python↔Rust call overhead and it turned out to be ~0.2ms, completely dominated by the actual computation. Don't pre-optimize this.

**Memory lifecycle is a product feature, not an afterthought.** Users don't want to manage when memories expire. Building automatic health-based forgetting into the core made OMem feel fundamentally different from "just another vector store."

---

## What's Next

We're working on:

1. **pgvector IVFFlat integration** — native database-side ANN for the enterprise stack, eliminating the Python FAISS dependency entirely.
2. **Multi-language AST indexing** — extending codebase memory beyond Python to TypeScript/Go/Rust.
3. **Federated memory** — allowing agent fleets at the same org to share a read-only "org memory" namespace while maintaining write isolation.

The code is open source: [github.com/mohitkumarrajbadi/omem](https://github.com/mohitkumarrajbadi/omem). The benchmark is reproducible: `python distribution/benchmark_vs_mem0.py`.

If you're building AI agents and paying per-recall for memory, we'd like to show you a different path.

---

*Questions or corrections? The technical details in this post are directly verifiable in the linked source files. `rust/src/lib.rs` contains the full Rust implementation. `benchmarks/competitor.py` contains the Mem0 measurements.*
