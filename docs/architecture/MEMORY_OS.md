# Memory Operating System — Charter → Code Map

**Canonical charter:** OMem is a Memory Operating System for AI agents — not a
vector database, not a RAG framework, not a chat-history wrapper.

This document maps the Memory OS brief to the live codebase (`omem-oss` +
`omem-cloud`). Extend facades and `omem.core`; do **not** rewrite BrainTrace.

Related: [ARCHITECTURE.md](./ARCHITECTURE.md) · Cloud pointer:
[`omem-cloud/docs/MEMORY_OS.md`](../../../omem-cloud/docs/MEMORY_OS.md)

---

## Gap-closure phases (status)

| Phase | Scope | Status |
|-------|--------|--------|
| **A** | BM25 on live fusion + E2E recall p95 SLO gate | **Done** |
| **B** | Per-type retrieval strategies + lifecycle FSM | **Done** |
| **C** | L0–L4 auto conveyor + cold spill on sleep | **Done** |
| **D** | Batch ingest (classify→index→graph, defer embed) | **Done** |
| **E** | Rust graph BFS + org namespace prefix harden | **Done** |
| **F** | Scorecard + regression tests | **Done** |

Remaining scale goals (not blocking charter completeness of core): true 100k+/sec
sustained with ANN indexing in Rust; LanceDB secondary (deferred); GA JWT tenancy.

---

## Product layers

| Charter | Code | Status |
|---------|------|--------|
| Memory (cognitive objects) | `omem.memory.MemoryOS`, `omem.types.Memory` | Stable + TOOL/SKILL |
| State (git-like) | `omem.state.StateOS` | Stable |
| Context (token pack) | `omem.context.ContextEngine` | Stable |
| Knowledge graph | `omem.knowledge` + `omem.core.graph` | Beta + Rust BFS |
| Governance / Observe | `omem.governance`, `omem.observe` | Cross-cutting |

StateMemory in the charter is **StateOS**, not a `MemoryType`.

---

## Memory types (cognitive objects)

| Charter | `MemoryType` | Retrieval strategy |
|---------|----------------|--------------------|
| WorkingMemory | `WORKING` | temporal / recency-heavy |
| EpisodicMemory | `EPISODIC` | temporal |
| SemanticMemory | `SEMANTIC` | semantic + graph |
| DecisionMemory | `DECISION` | importance + semantic |
| ToolMemory | `TOOL` | exact / keyword |
| SkillMemory | `SKILL` | semantic + keyword |
| StateMemory | StateOS | state APIs |

Strategies: [`type_strategies.py`](../../omem/core/retrieval/type_strategies.py)

---

## Hierarchy L0–L4

Auto conveyor: [`hierarchy.py`](../../omem/core/brain/hierarchy.py) during `sleep()`.

| Layer | Level | Behavior |
|-------|-------|----------|
| L0 | working | Active task; TTL/decay |
| L1 | short_term | Events / incidents |
| L2 | long_term + semantic | Facts / decisions / rules |
| L3 | long_term + skill/procedural | Reusable procedures |
| L4 | archive | Tier ARCHIVE; cold via `ColdArchive` when `OMEM_COLD_ENABLED=1` |

---

## Retrieval

```
FinalScore = w_s·S + w_k·BM25_blend + w_r·R + w_i·I + w_c·C + w_g·G
           + w_p·P + w_success·Success + w_goal·Goal
```

- BM25: [`bm25.py`](../../omem/core/retrieval/bm25.py) → Rust `bm25_scores` when available
- Fusion: [`fusion.py`](../../omem/core/retrieval/fusion.py) / [`ranker.py`](../../omem/core/retrieval/ranker.py)
- Rust rank: `rag_fuse_batch`
- Lookups + type engines: [`lookup.py`](../../omem/core/retrieval/lookup.py)
- Explain: `RetrievalExplanation.to_dict()`

**SLO gate:** `python -m benchmarks.slo_recall_latency` (target p95 &lt; 10ms @ N≤5k).

---

## Lifecycle

FSM: [`lifecycle_fsm.py`](../../omem/core/brain/lifecycle_fsm.py)

```
remember → recall → consolidate/sleep → archive → forget
new → reinforced → consolidated → compressed → archived → forgotten
```

---

## Ingestion

[`ingest_pipeline.py`](../../omem/core/brain/ingest_pipeline.py) + `MemoryOS.ingest_batch()`:

classify → placeholder/index → graph → write buffer → optional embed flush

LLM-free hot path. Throughput depends on `defer_embed=True`.

---

## Storage

| Store | Role |
|-------|------|
| Postgres + pgvector | Durable primary (cloud) |
| SQLite | Local default |
| Rust | Score/rank/BM25/graph BFS |
| `ColdArchive` | L4 spill (`OMEM_COLD_*`) |
| LanceDB | **Deferred** |

---

## Multi-tenancy

`organization → workspace → agent → user` via
[`governance/tenant.py`](../../omem/governance/tenant.py). Cloud `_ctx` pins
namespaces under API-key `org_id` (prefix guard).

---

## Observability & benchmarks

- Prometheus Memory OS SLIs on cloud `/v1/metrics`
- OTel: `/v1/remember` + `/v1/recall`
- Benchmarks: Naive / Hybrid / GraphRAG / OMem — MRR, NDCG@5, Recall@K, latency
  ([`rag_comparison.py`](../../benchmarks/rag_comparison.py))
- Token reduction: cloud token-savings benches

---

## Non-goals

Do not build another chatbot, general-purpose vector DB product, or
LangChain wrapper. Ship a Memory Operating System.
