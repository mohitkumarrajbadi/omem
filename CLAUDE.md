# OMem — Project Memory for Claude Code & AI Agents

---

## Live Project Memory — Use This for Code Navigation

This `CLAUDE.md` is the **static orientation layer** — it loads at session start with no dependencies.

OMem also ships its own **live MCP layer** that indexes every symbol in this codebase via AST, builds a dependency graph, and lets you jump to exact `file:line` with a natural-language query. That is the smart layer — use it instead of grep or file reads once it is set up.

### One-time setup (run once per machine)

```bash
pip install omem-os[mcp,embeddings]

# Index this codebase into OMem's project memory
python -c "
from omem import OMem
n = OMem().ingest_project('.')
print(f'{n} symbols indexed into project memory')
"
```

Add to `claude_desktop_config.json` (Claude Desktop) or Cursor MCP settings:

```json
{
  "mcpServers": {
    "omem": { "command": "omem", "args": ["serve"] }
  }
}
```

### MCP tools — prefer these over file search

| Tool | What it does |
|---|---|
| `query_codebase("auth logic")` | Semantic search → returns symbol + `file:line` + dependencies |
| `ingest_codebase(".")` | Full baseline index (run once on first use) |
| `sync_codebase(".")` | Incremental update after editing files (uses git diff, fast) |
| `recall("architectural decisions")` | Retrieve stored project knowledge by topic |
| `remember("decided X over Y because Z")` | Persist a decision for future sessions |
| `reflect()` | Generate high-level insights from accumulated knowledge |
| `maintain()` | Compress + forget low-value memories, keep context lean |
| `summarize_state()` | Birds-eye view of current project understanding |

> The MCP server's onboarding prompt explicitly instructs: **"NEVER use grep, find, or recursive file search to navigate code. Use `query_codebase` instead."**

After any significant code change run `sync_codebase(".")` — it re-parses only what git diff shows changed.

---

## Project Overview

**OMem** (`omem-os` on PyPI) is a **Memory Operating System for AI Agents** — persistent, intelligent memory with automatic classification, hybrid RAG retrieval, conflict resolution, forgetting, and memory consolidation. It is **not** a vector database wrapper; it is a full cognitive lifecycle system.

- **Version:** 0.0.1 pre-alpha | **Python:** 3.9+ | **Rust** core via PyO3
- **Active branch:** `dev` — all PRs target `dev`
- **Install:** `SETUPTOOLS_USE_DISTUTILS=stdlib pip install -e ".[dev]"`

---

## Quick Commands Reference

```bash
# Dev setup
python3 -m venv .venv && source .venv/bin/activate
SETUPTOOLS_USE_DISTUTILS=stdlib pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Benchmarks — REQUIRED if touching rust/, core/retrieval/, or core/engine/add.py
python benchmarks/competitor.py
omem benchmark --n 10000

# Linting
ruff check omem/ && ruff format omem/

# CLI
omem health                   # sanity check
omem serve                    # MCP stdio server (Claude Desktop / Cursor)
omem maintain --all           # full sleep cycle from CLI
omem dashboard --port 7900    # web dashboard
```

**macOS / Anaconda — add to shell profile once:**
```bash
export KMP_DUPLICATE_LIB_OK=TRUE      # prevents FAISS/OpenMP crash
export HF_HUB_OFFLINE=1               # skip HuggingFace network check on startup
export TOKENIZERS_PARALLELISM=false   # suppress tokenizer warning
```

---

## Architecture Map

```
omem/api.py              ← THE ONLY PUBLIC SURFACE. OMem class lives here.
omem/types.py            ← All dataclasses and enums. Start here for any new type.
omem/classify.py         ← Auto-classification engine (regex rules + ML fallback)
omem/cli.py              ← Click CLI. All `omem <cmd>` commands defined here.

omem/core/engine/
  base.py                ← BrainTrace — internal orchestrator. ALL ops route here.
  add.py                 ← Full ingestion pipeline (embed→classify→dedup→graph→persist)
  rag.py                 ← Full retrieval pipeline (4-signal hybrid scoring)
  lifecycle.py           ← Archive, prune, snapshot operations

omem/core/brain/         ← Cognitive heuristics. Each file = one brain function.
  importance.py          ← Heuristic importance scorer (0.0–1.0)
  forgetting.py          ← Time-based utility decay + forgetting sweep
  dream.py               ← Sleep-cycle consolidation (cluster → summarize)
  tms.py                 ← Truth Maintenance System: detects + flags conflicts
  reflection.py          ← Generates REFLECTION-type insight memories
  compression.py         ← Deduplicates similar memories into merged summaries
  noise_gate.py          ← Filters out low-signal / trivial inputs
  secrets.py             ← Auto-detects credentials, masks them before storage
  corruption_guard.py    ← Data integrity checks
  quotas.py              ← Namespace storage limits
  prefetch.py            ← Prefetches likely-needed memories based on recent context
  updater.py             ← Handles in-place memory content updates

omem/core/retrieval/
  vector.py              ← FAISS HNSW index management (add/search/rebuild)
  kv.py                  ← Key-value lookups (get by ID, list all, filter)
  embeddings.py          ← Embedding generation + LRU cache

omem/core/graph/
  knowledge.py           ← Knowledge graph: entity extraction + edge management
  causal.py              ← Causal relationship edges
  dependency.py          ← Symbol/concept dependency tracking

omem/core/utils/
  cache.py               ← LRU cache wrapper
  concurrency.py         ← RW locks, thread safety primitives
  write_buffer.py        ← Async write buffer (batches backend writes)
  metrics.py             ← Performance counters / timers
  circuit_breaker.py     ← Fault tolerance for backend calls
  retry.py               ← Retry logic with backoff
  snapshot.py            ← State snapshots for rollback
  structured_logging.py  ← JSON-structured log output
  inspector.py           ← Debugging / introspection helpers

omem/backends/
  base.py                ← Abstract StorageBackend interface (implement this to add backends)
  sqlite.py              ← Default: ~/.omem/brain.db
  postgres.py            ← Production / multi-process

omem/codebase/           ← Project Memory feature (code indexing)
  ingester.py            ← AST crawl Python files → extract symbols
  graph.py               ← Build symbol dependency graph in OMem
  retriever.py           ← Code symbol semantic search
  sync.py                ← Incremental sync via git diff
  types.py               ← CodeSymbol, SymbolType, etc.
  utils.py

omem/integrations/
  mcp_server.py          ← MCP stdio server (tools: remember/recall/reflect/maintain/...)
  langchain.py           ← OMemRetriever (drop-in LangChain retriever)
  crewai.py              ← CrewAI agent adapter
  agent_wrapper.py       ← Generic wrapper for any agent framework

omem/security/
  encryption.py          ← AES-256-GCM encrypt/decrypt (used by backends)
  audit.py               ← Append-only audit log for all add/recall/delete ops

rust/src/lib.rs          ← PyO3 extension `omem_rust`: SIMD scoring, FAISS HNSW,
                            batched distance metrics, thread-safe write buffer
```

---

## Where to Make Changes — Task Routing Guide

This is the most important section. For any task, go directly to these files.

### Changing classification behavior
- **What type a memory gets auto-assigned** → `omem/classify.py`
- **Add a new MemoryType** → `omem/types.py` first, then update regex rules in `omem/classify.py`

### Changing retrieval / scoring
- **Scoring weights** (50/20/15/15 formula) → `rust/src/lib.rs` (SIMD path) + `omem/core/engine/rag.py` (Python fallback)
- **Graph-RAG expansion logic** → `omem/core/graph/knowledge.py`
- **context_type alias mapping** → `omem/api.py` (`_CONTEXT_TYPE_MAP` inside `recall()`)
- **Embedding model or generation** → `omem/core/retrieval/embeddings.py`
- **FAISS index parameters** (HNSW M, efConstruction) → `rust/src/lib.rs` + `omem/core/retrieval/vector.py`

### Changing ingestion / add behavior
- **Deduplication logic** → `omem/core/engine/add.py`
- **Importance scoring** → `omem/core/brain/importance.py`
- **Noise filtering** → `omem/core/brain/noise_gate.py`
- **Secret/credential detection** → `omem/core/brain/secrets.py`
- **Entity extraction for graph** → `omem/core/graph/knowledge.py`

### Changing memory lifecycle / maintenance
- **Forgetting / decay rules** → `omem/core/brain/forgetting.py`
- **Compression / deduplication during sleep** → `omem/core/brain/compression.py`
- **Dream / consolidation cycle** → `omem/core/brain/dream.py`
- **Reflection insight generation** → `omem/core/brain/reflection.py`
- **Sleep cycle orchestration** → `omem/core/engine/base.py` (`BrainTrace.sleep()`)
- **Conflict detection rules** → `omem/core/brain/tms.py`
- **Conflict resolution logic** → `omem/api.py` (`resolve_conflict()`) + `omem/core/brain/tms.py`

### Changing storage / persistence
- **SQLite schema or queries** → `omem/backends/sqlite.py`
- **PostgreSQL schema or queries** → `omem/backends/postgres.py`
- **Add a new backend** → new file in `omem/backends/`, inherit `base.py`, register in `omem/api.py.__init__`
- **Encryption** → `omem/security/encryption.py`
- **Write buffering** → `omem/core/utils/write_buffer.py`

### Changing the public API
- **Add/modify a method that users call** → `omem/api.py` only
- **Never expose `BrainTrace` or engine internals directly**

### Changing the CLI
- **Add/modify a CLI command** → `omem/cli.py` (Click command groups)

### Changing integrations
- **MCP tools** (add/rename/modify tools) → `omem/integrations/mcp_server.py`
- **LangChain** → `omem/integrations/langchain.py`
- **CrewAI** → `omem/integrations/crewai.py`

### Changing codebase indexing
- **AST parsing / symbol extraction** → `omem/codebase/ingester.py`
- **Code graph edges** → `omem/codebase/graph.py`
- **Code search / retrieval** → `omem/codebase/retriever.py`
- **Git-based incremental sync** → `omem/codebase/sync.py`

### Changing Rust core
- **Any SIMD or batched array operation** → `rust/src/lib.rs`, then `pip install -e .`
- **Never put Python logic in Rust** — keep boundary thin (primitive arrays only)

---

## Call Chains — What Actually Happens

### brain.add(content) — full trace
```
OMem.add()                          omem/api.py
  └─ BrainTrace.add()               omem/core/engine/base.py
       └─ ingestion pipeline        omem/core/engine/add.py
            ├─ generate embedding   omem/core/retrieval/embeddings.py
            ├─ auto-classify type   omem/classify.py
            ├─ score importance     omem/core/brain/importance.py
            ├─ noise gate check     omem/core/brain/noise_gate.py
            ├─ secret detection     omem/core/brain/secrets.py
            ├─ deduplication check  (hashes compared in add.py)
            ├─ entity extraction    omem/core/graph/knowledge.py
            ├─ async persist        omem/backends/sqlite.py (via write_buffer)
            └─ update FAISS index   omem/core/retrieval/vector.py
  └─ audit log                      omem/security/audit.py
```

### brain.recall(query) — full trace
```
OMem.recall()                       omem/api.py
  ├─ context_type → type_boosts     omem/api.py (inline _CONTEXT_TYPE_MAP)
  └─ BrainTrace.rag()               omem/core/engine/base.py
       └─ retrieval pipeline        omem/core/engine/rag.py
            ├─ embed query          omem/core/retrieval/embeddings.py
            ├─ FAISS ANN search     omem/core/retrieval/vector.py  (→ rust/src/lib.rs)
            ├─ SIMD hybrid scoring  rust/src/lib.rs  (omem_rust extension)
            └─ graph-RAG expansion  omem/core/graph/knowledge.py
  ├─ post-filter namespace          omem/api.py
  ├─ post-filter time_range         omem/api.py
  └─ audit log                      omem/security/audit.py
```

### brain.sleep() — full trace
```
OMem.sleep()                        omem/api.py
  └─ BrainTrace.sleep()             omem/core/engine/base.py
       ├─ run_decay()               omem/core/brain/forgetting.py
       ├─ forget()                  omem/core/brain/forgetting.py
       ├─ compress()                omem/core/brain/compression.py
       ├─ reflect()                 omem/core/brain/reflection.py
       └─ dream()                   omem/core/brain/dream.py
```

### brain.ingest_project(path) — full trace
```
OMem.ingest_project()               omem/api.py
  ├─ ProjectIngester(path).crawl()  omem/codebase/ingester.py  (AST parse)
  └─ ProjectGraph(omem).sync_symbols()  omem/codebase/graph.py
       └─ omem.add() per symbol     (routes through full add pipeline above)
```

---

## Key Types (omem/types.py)

```python
class MemoryType(Enum):
    WORKING=0    # short-term, current-task context
    EPISODIC=1   # events and experiences
    SEMANTIC=2   # facts, general knowledge, architecture
    CAUSAL=3     # bug root causes, cause-effect chains
    DECISION=4   # choices made, preferences, settings
    PROCEDURAL=5 # how-to steps, deployment workflows
    ACTIVE=6     # high-priority, urgent items
    REFLECTION=7 # AI-generated insights (from reflect())
    INSIGHT=8    # consolidated summaries (from dream())
    SENSORY=9    # raw, short-lived input (seconds TTL)

class MemoryStatus(Enum):
    ACTIVE=0       # normal, appears in RAG
    DEPRECATED=1   # superseded, excluded from RAG
    CONFLICTED=2   # flagged by TMS, needs resolution
    ARCHIVED=3     # hidden, recoverable via restore()

class MemoryTier(Enum):
    CORE=0     # never forgotten (identity-level)
    ACTIVE=1   # normal operation
    ARCHIVE=2  # temporarily hidden
    FORGOTTEN=3
    SENSORY=4  # brief storage
    INSIGHT=5  # consolidated results

@dataclass
class Memory:
    id: str
    type: MemoryType
    content: str
    vector: np.ndarray          # embedding — NOT stored in DB, rebuilt on load
    timestamp: float            # unix time of creation
    importance: float           # 0.0–1.0, set at ingestion
    utility_score: float        # updated by access patterns
    access_count: int
    last_accessed: float
    namespace: str              # isolation key
    source: str                 # "user", "agent", "system", etc.
    active: bool                # False = excluded from everything
    status: MemoryStatus
    tier: MemoryTier
    priority: MemoryPriority    # affects score multiplier (CORE=2×, HIGH=1.5×)
    entities: List[str]         # extracted named entities
    dependencies: List[str]     # IDs of memories this depends on
    confidence_score: float     # 0.0–1.0 source reliability
    metadata: Dict[str, Any]
    score: float                # DYNAMIC — set at retrieval, not persisted
```

---

## Public API — OMem Class (omem/api.py)

```python
brain = OMem(
    backend="sqlite",           # "sqlite" | "memory" | "postgres"
    db_path="~/.omem/brain.db", # or "postgresql://user:pass@host:5432/omem"
    model="all-MiniLM-L6-v2",
    embedding_provider="local",
    encryption_key=None,        # base64-encoded AES-256 key
)

# --- Write ---
brain.add(content, mem_type=None, importance=None, namespace="default",
          source="user", force=False, memory_id=None) -> str
brain.add_batch(contents, mem_types=None, namespaces=None, sources=None) -> List[str]
brain.update(memory_id, new_content, merge=False) -> Optional[str]
brain.delete(memory_id) -> bool

# --- Read ---
brain.recall(query, k=5, context_type=None, time_range=None,
             namespace=None, project_only=False) -> List[Memory]
brain.get(memory_id) -> Optional[Memory]
brain.inspect(query, top_k=5, namespace=None) -> List[RetrievalExplanation]
brain.all(namespace=None, include_inactive=False) -> List[Memory]

# --- Maintenance ---
brain.sleep(speed="normal", llm_fn=None) -> Dict
brain.dream(llm_fn=None, threshold=0.60, min_cluster_size=3) -> DreamResult
brain.compress(threshold=0.75, namespace=None, summarizer=None) -> Dict
brain.reflect(threshold=0.65, namespace=None, summarizer=None) -> List[Memory]
brain.forget() -> ForgetResult
brain.decay() -> List[str]
brain.restore(memory_id) -> bool
brain.archived(namespace=None) -> List[Memory]
brain.resolve_conflict(query) -> Dict
brain.auto_maintenance(enabled=True, interval=3600.0)

# --- Graph ---
brain.link(src_id, dst_id, weight=1.0, label="")
brain.graph_query(entity_name, depth=2) -> List[Memory]
brain.entities() -> List[Dict]

# --- Codebase (Project Memory) ---
brain.ingest_project(path=".", namespace="project") -> int   # returns symbol count
brain.sync_project(path=".", namespace="project") -> int
brain.query_code(query, include_dependencies=True, include_callers=True,
                 context_depth=2, top_k=5, namespace="project") -> List[Dict]

# --- Utilities ---
brain.stats() -> Dict
brain.namespaces() -> List[str]
brain.namespace_stats(namespace) -> Dict
brain.summarize_state(namespace=None) -> str
brain.get_audit_log(limit=100, operation=None, namespace=None, memory_id=None)
brain.prefetch() -> Dict
brain.clear(namespace=None)
```

### recall() — context_type aliases
| Alias | MemoryType boosted (2.5×) |
|---|---|
| `"bugs"`, `"errors"`, `"root_cause"`, `"causal"` | `CAUSAL` |
| `"decisions"`, `"preferences"`, `"settings"` | `DECISION` |
| `"architecture"`, `"arch"`, `"system"`, `"semantic"` | `SEMANTIC` |
| `"procedures"`, `"howto"`, `"actions"` | `PROCEDURAL` |
| `"episodic"`, `"events"`, `"history"` | `EPISODIC` |
| `"working"`, `"current"` | `WORKING` |
| `"insights"`, `"reflections"` | `INSIGHT` / `REFLECTION` |

### recall() — time_range values
`"today"` = last 24h | `"recent"` = last 3 days | `"last_week"` = last 7 days

---

## Retrieval Scoring Formula

```
Final Score = (0.50 × vector_similarity)
            + (0.20 × keyword_overlap)
            + (0.15 × recency_decay)
            + (0.15 × importance_weight)
            × status_multiplier
            × priority_multiplier   # CORE=2.0, HIGH=1.5, NORMAL=1.0, LOW=0.7
```

Computed in SIMD via `rust/src/lib.rs`. Python fallback in `omem/core/engine/rag.py`.
Graph-RAG expansion runs after scoring — `omem/core/graph/knowledge.py`.

---

## Critical Gotchas (Things That Trip Up Contributors)

1. **`omem/api.py` is the only public surface.** Never expose `BrainTrace`, engine internals, or backends directly. All user-facing changes go through `OMem` class.

2. **`BrainTrace` (core/engine/base.py) is the internal orchestrator.** Everything routes through it. Don't call `add.py`, `rag.py`, or brain modules directly from `api.py` — go via `BrainTrace`.

3. **`score` on `Memory` is dynamic.** It is set at retrieval time by the scoring pipeline and is NOT persisted in the database. Do not rely on `memory.score` outside of a `recall()` or `inspect()` result.

4. **`force=True` in `add()` bypasses deduplication.** Default is `False` — duplicate content will be detected and rejected. Use `force=True` in tests or bulk imports.

5. **`project_only=False` searches broader than the namespace.** With a namespace set, `project_only=False` (default) searches across that namespace + "global". Set `project_only=True` to strictly isolate.

6. **CONFLICTED memories still appear in RAG** unless explicitly filtered. The TMS flags them but does not remove them. Call `resolve_conflict()` to deprecate the losers.

7. **All backend writes are async-buffered.** `write_buffer.py` batches writes. In tests, call `brain._backend.flush()` or use `OMem(backend="memory")` to avoid async ordering issues.

8. **Rust extension is optional at runtime.** If `omem_rust` is not available, Python fallback runs silently. This fallback is slower — only use it in tests. CI builds always include the Rust extension.

9. **Embedding model loads on first use.** `all-MiniLM-L6-v2` (~90MB) is downloaded by `sentence-transformers` on first call to `add()` or `recall()`. Set `HF_HUB_OFFLINE=1` to prevent network checks after first download.

10. **Namespace is set per-memory, not per-OMem instance.** The `namespace` param on `OMem()` is not saved on the instance — pass `namespace=` explicitly to `add()` and `recall()`.

---

## Performance Requirements — Do Not Regress

| Operation | Limit |
|---|---|
| `add()` end-to-end | < 5 ms |
| `recall()` RAG p99 | < 30 ms |
| `OMem()` setup time | < 10 ms |

Run benchmarks after touching: `rust/`, `omem/core/retrieval/`, `omem/core/engine/add.py`
```bash
python benchmarks/competitor.py   # head-to-head vs ChromaDB, LanceDB, Mem0
omem benchmark --n 10000
```

---

## Rust Extension

- **Location:** `rust/src/lib.rs` — exposes `omem_rust` Python module via PyO3
- **Use Rust for:** SIMD vector scoring, batched distance metrics, HNSW index management
- **Keep boundary thin:** only pass `numpy` arrays or simple primitive types across the PyO3 boundary
- **After any change:** `pip install -e .` to recompile
- **Never put business logic in Rust** — only performance-critical array operations

---

## Coding Standards

- **Strict type hints everywhere:** `def fn(x: str, y: float = 0.5) -> Optional[str]:`
- **No LLM API calls in hot paths** — `add()` and `recall()` must be zero-API-cost
- **Brain modules are heuristics** — never block the ingestion or retrieval loop synchronously
- **Comments in `brain/`** must explain *why* the heuristic exists, not just *what* it does
- **Rust** for any operation over arrays of memories or computing distance metrics at scale

---

## Testing

```bash
pytest tests/ -v
pytest tests/test_api.py -v
pytest tests/test_backends.py -v
pytest tests/test_truth_maintenance.py -v
```

Rules:
- All new `omem/core/` logic needs a test in `tests/test_<module>.py`
- **Mock all LLM and external API calls** — tests must be deterministic and offline
- Use `OMem(backend="memory")` in tests (in-memory SQLite, no disk I/O)
- Tests must pass before opening a PR to `dev`

---

## Git / Branch Workflow

| Branch | Purpose |
|---|---|
| `dev` | **All PRs target here.** Active development. |
| `staging` | Pre-release integration testing |
| `main` / `prod` | Stable tagged releases only |

```bash
git checkout dev
git checkout -b feat/my-feature
# make changes, run pytest, run benchmarks if needed
git push origin feat/my-feature
# open PR → target: dev
```

Commit prefixes: `feat:` `fix:` `chore:` `change:` `docs:` `refactor:`

---

## Adding a New Backend

1. Create `omem/backends/<name>.py`
2. Inherit from `omem.backends.base.StorageBackend`
3. Implement: `save`, `load`, `delete`, `query`
4. Register in `omem/api.py` `__init__` factory block (the `if backend in (...)` chain)
5. Add tests in `tests/test_backends.py`

---

## MCP Integration (Claude Desktop / Cursor)

```bash
omem serve   # starts MCP stdio server on stdin/stdout
```

`claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "omem": { "command": "omem", "args": ["serve"] }
  }
}
```

Tools exposed: `remember`, `recall`, `reflect`, `maintain`, `resolve_conflict`, `summarize_state`

Python: `from omem.integrations.mcp_server import serve_mcp; serve_mcp()`

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `OMEM_DB_PATH` | `~/.omem/brain.db` | SQLite database path |
| `OMEM_MODEL` | `all-MiniLM-L6-v2` | Embedding model name |
| `OMEM_CACHE_SIZE` | `128000` | LRU embedding cache size |
| `OMEM_POOL_SIZE` | `5` | DB connection pool (PostgreSQL) |
| `OMEM_LOG_LEVEL` | `INFO` | Logging verbosity |
| `OMEM_MCP_PORT` | `3000` | MCP server port |
| `OMEM_ENCRYPTION_KEY` | — | Base64 AES-256 key for encryption at rest |
| `KMP_DUPLICATE_LIB_OK` | — | `TRUE` → fixes FAISS crash on macOS/Anaconda |
| `HF_HUB_OFFLINE` | — | `1` → skip HuggingFace Hub network check |

---

## Optional Extras

```bash
pip install omem-os[fast]        # FAISS + Numba acceleration
pip install omem-os[embeddings]  # sentence-transformers (~90MB model)
pip install omem-os[postgres]    # psycopg2 for PostgreSQL
pip install omem-os[mcp]         # MCP server support
pip install omem-os[secure]      # AES-256-GCM encryption
pip install omem-os[langchain]   # LangChain OMemRetriever
pip install omem-os[openai]      # OpenAI embeddings provider
pip install omem-os[dev]         # pytest, ruff, coverage
pip install omem-os[all]         # everything
```

---

## Common Usage Patterns

```python
# Basic persistent agent memory
from omem import OMem
brain = OMem()
brain.add("User prefers Python for all backend work", importance=0.8)
context = brain.recall("preferred language", k=3)

# Multi-agent isolation (namespaces are fully isolated)
agent_a = OMem()
agent_a.add("my private data", namespace="agent-a")
agent_a.recall("data", namespace="agent-a", project_only=True)  # strict isolation

# Debug retrieval scoring
for exp in brain.inspect("payment bug"):
    print(exp.explain())
# → vector=0.91, keyword=0.85, recency=0.94, importance=1.5x boost → Final: 0.93

# Run maintenance (call after a session ends)
stats = brain.sleep()
# → {"forgotten": 12, "consolidated": 3, "reflected": 4}

# Ingest this codebase into memory
n = brain.ingest_project(".", namespace="project")
results = brain.query_code("authentication flow", top_k=5)

# Conflict resolution
brain.add("Python version: 3.9")
brain.add("Python version: 3.11")   # auto-flagged CONFLICTED by TMS
brain.resolve_conflict("Python version")  # keeps most recent, deprecates old

# LangChain integration
from omem.integrations.langchain import OMemRetriever
retriever = OMemRetriever(omem_instance=brain)
chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
```

---

## Project Root Structure

```
omem/              Python package (the product)
rust/              Rust PyO3 extension (omem_rust SIMD core)
tests/             pytest suite — run before every PR
benchmarks/        competitor.py, latency.py, scale.py, etc.
examples/          quickstart.py, demo.py, demo_ollama.py, etc.
.claude/           Claude Code settings (attribution disabled)
.cursorrules       Cursor AI assistant context
pyproject.toml     Packaging, deps, extras, CLI entrypoint
DEVELOPER.md       Full technical contributor guide
README.md          Public-facing docs
SECURITY.md        Security policy
CHANGELOG.md       Release history
```
