<div align="center">

[![PyPI](https://img.shields.io/pypi/v/omem-os?style=for-the-badge&color=brightgreen)](https://pypi.org/project/omem-os/)
[![GitHub Stars](https://img.shields.io/github/stars/mohitkumarrajbadi/omem?style=for-the-badge)](https://github.com/mohitkumarrajbadi/omem/stargazers)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](./LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-purple?style=for-the-badge)](./MCP_SETUP.md)
[![Discord](https://img.shields.io/badge/discord-join-5865F2?style=for-the-badge&logo=discord)](https://discord.gg/#)

<br>

# OMem
### The Memory Operating System for AI Agents

**Give your AI agent a brain that remembers. 16× faster than Mem0. Zero config. Zero API costs.**

[**Quick Start**](#quick-start) · [**Benchmarks**](#benchmarks) · [**Claude Desktop & MCP**](#claude-desktop--mcp-setup) · [**Project Memory**](#project-memory--codebase-indexing) · [**CLI**](#cli-reference) · [**Docs**](./DEVELOPER.md)

</div>

---

## Install

```bash
pip install omem-os
```

```python
from omem import OMem
```

Live on PyPI: **[https://pypi.org/project/omem-os/](https://pypi.org/project/omem-os/)**

---

## Before / After

**Without OMem** — your agent forgets between sessions:

```python
# Session 1
agent.chat("My name is Alice and I prefer dark mode.")
# → "Nice to meet you, Alice!"

# Session 2 (new process)
agent.chat("What's my display preference?")
# → "I don't have information about your preferences."  ← forgot
```

**With OMem** — your agent remembers:

```python
from omem import OMem

brain = OMem()  # persists to ~/.omem/brain.db

# Session 1
brain.add("User name: Alice. Prefers dark mode and Python for all backend work.")
agent.chat("My name is Alice and I prefer dark mode.")

# Session 2 (new process — brain.db persists automatically)
context = brain.recall("display preference")
agent.chat("What's my display preference?", context=context)
# → "You prefer dark mode, Alice."  ← remembered
```

---

## Benchmarks

> *Tested on Apple M-series. Same dataset: 5 000 memories, 500 queries, `all-MiniLM-L6-v2`. Reproduce with `python benchmarks/competitor.py` or open `benchmarks/reproduce.ipynb`.*

### Head-to-Head Performance

| System | Setup | Add (ops/s) | RAG (ops/s) | RAG p99 |
| :--- | ---: | ---: | ---: | ---: |
| **OMem** | **4.0 ms** | **65 †** | **292** | **20 ms** |
| ChromaDB | 507 ms | 277 ‡ | 280 | 4 ms |
| LanceDB | 8 ms | 82 000 ‡ | 182 | 7 ms |
| **Mem0** | **15 000+ ms** | **< 1** | **18** | **638 ms** |

> **† Smart Ingestion** — OMem's `add()` does: `embed → auto-classify → dedup → entity-graph sync → async persist`. Others just store pre-computed vectors.
>
> **‡ Raw storage only** — No classification. No deduplication. No graph. No cognitive maintenance.

### Speedup Summary

| Metric | OMem vs Mem0 | OMem vs ChromaDB | OMem vs LanceDB |
|---|---|---|---|
| RAG throughput | **16× faster** | **1.0× (parity)** | **1.6× faster** |
| p50 recall | **0.007 ms** | 3.5 ms | 5.3 ms |
| Setup time | **125× faster** | **127× faster** | parity |
| Cognitive features | ✅ 9/9 | ❌ 0/9 | ❌ 0/9 |

Mem0 is slow because it calls an LLM on every `add()`. OMem replaces that with a Rust-native classifier — zero LLM calls, zero API costs, zero added latency.

---

## Stability

| Component | Status | Notes |
|---|---|---|
| Core API (`add`, `recall`, `sleep`, `inspect`) | **Stable** | API locked for v0.1.x |
| SQLite backend | **Stable** | Default; handles 100 000+ memories |
| PostgreSQL backend | Beta | Production-ready; connection-string config |
| MCP server (Claude Desktop / Cursor) | **Stable** | `omem serve` |
| LangChain integration | Beta | `OMemRetriever` |
| CrewAI integration | Alpha | Namespace-based multi-agent sharing |
| Codebase indexer | Alpha | AST parsing, git-diff sync, graph retrieval — Python only |
| Visualization dashboard | Beta | `omem dashboard` |

---

## The Problem

Current memory approaches fall short in specific ways:

- **Vector DBs** — Pure storage. Returns semantically similar noise. No lifecycle management, no deduplication, no conflict resolution.
- **Long context windows** — Expensive, slow, hits limits, and forces agents to process irrelevant historical detail on every turn.
- **Conversation buffers** — Grows unboundedly. No cross-session continuity. No multi-agent isolation.

None of these systems *think*. They store. OMem manages memory the way a cognitive system does.

---

## How It Works

OMem is a full Memory Operating System — it mirrors how memory works in practice:

```
Store everything  →  Classify what matters      →  Retrieve the relevant subset
Compress similar  →  Forget low-value old items  →  Resolve contradictions
```

It functions as a **cognitive layer**, not just a database with retrieval.

---

## Quick Start

### Installation

```bash
# From PyPI (recommended)
pip install omem-os

# From source
git clone https://github.com/mohitkumarrajbadi/omem
cd omem
SETUPTOOLS_USE_DISTUTILS=stdlib pip install -e .
omem health
```

### 60-Second Example

```python
from omem import OMem

brain = OMem()

# Add memories — auto-detects type and importance
brain.add("User prefers dark mode and Python for all backend work")
brain.add("Critical bug: race condition in payment module causes duplicate charges", importance=0.95)
brain.add("Architecture decision: migrated from REST to GraphQL for better performance")

# Retrieve what matters — not everything
results = brain.recall("What bugs do we have?")
print(results[0].content)
# → "Critical bug: race condition in payment module..."

# See exactly why it was selected
for exp in brain.inspect("payment bugs"):
    print(exp.explain())
# → vector=0.91, keyword=0.85, recency=0.94, importance=1.5x boost
```

### The Sleep Cycle

```python
brain.add("User clicked login button")
brain.add("User pressed sign-in")
brain.add("User tapped the login link")

result = brain.sleep()
# compressed: 3 → 1  ("User repeatedly accessed login (3 instances)")
# forgotten:  12 low-value memories removed
# reflected:  4 new insights generated
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│            Your Agent  /  Claude  /  Cursor              │
└──────────────────────────┬──────────────────────────────┘
                           │  MCP or Python SDK
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    OMem Unified API                      │
│        add · recall · sleep · inspect · serve           │
└────────────┬───────────────────────────┬────────────────┘
             │                           │
             ▼                           ▼
┌─────────────────────┐     ┌────────────────────────────┐
│     Rust Core       │     │        Brain Logic          │
│                     │     │                            │
│  • SIMD scoring     │     │  • Auto-classification     │
│  • FAISS HNSW       │     │  • Importance estimation   │
│  • Hybrid ranking   │     │  • Forgetting & decay      │
│  • Write buffer     │     │  • Reflection & compress   │
│  • RW lock          │     │  • Conflict TMS            │
└─────────────────────┘     └────────────────────────────┘
             │                           │
             └─────────────┬─────────────┘
                           ▼
             ┌──────────────────────────┐
             │  SQLite · PostgreSQL     │
             │  FAISS · Knowledge Graph │
             └──────────────────────────┘
```

### Retrieval Pipeline (4 Signals, Single SIMD Pass)

```
Final Score = (0.50 × vector_similarity)
            + (0.20 × keyword_overlap)
            + (0.15 × recency_decay)
            + (0.15 × importance_weight)
            × status_multiplier
```

Top results are optionally expanded via **Graph-RAG**: entities in recalled memories are used to traverse the knowledge graph and surface connected memories that pure vector search would miss.

---

## Feature Matrix

| Feature | OMem | ChromaDB | Mem0 | LanceDB |
| :--- | :---: | :---: | :---: | :---: |
| Auto-Classification | ✅ | ❌ | ❌ | ❌ |
| Causal Knowledge Graph | ✅ | ❌ | ❌ | ❌ |
| Hybrid RAG (vector + keyword + recency + importance) | ✅ | ❌ | ❌ | ❌ |
| Forgetting & Decay | ✅ | ❌ | ❌ | ❌ |
| Memory Compression | ✅ | ❌ | ❌ | ❌ |
| Conflict Detection & TMS | ✅ | ❌ | ❌ | ❌ |
| CLI Tools | ✅ | ❌ | ❌ | ❌ |
| Zero Config | ✅ | ✅ | ❌ | ✅ |
| MCP Server (Claude / Cursor) | ✅ | ❌ | ❌ | ❌ |
| Codebase Indexing (AST + Graph) | ✅ | ❌ | ❌ | ❌ |

---

## Real-World Usage

### Customer Support Agent

```python
from omem import OMem

memory = OMem(namespace="support")

memory.add("Customer John (john@acme.com) reported dashboard timeout on mobile Safari")
memory.add("Acme Corp is on Enterprise plan, SOC2 required by Q3")

context = memory.recall(
    "mobile issues Acme",
    context_type="bugs",     # boost bug-type memories
    time_range="recent",     # prioritize last 3 days
    k=5
)
```

### Multi-Agent System

```python
researcher = OMem(namespace="researcher")
writer     = OMem(namespace="writer")

researcher.add("Study shows 40% retention improvement with personalized onboarding")

writer.recall("retention")                         # → []  (fully isolated)
researcher.recall("retention", project_only=False) # → finds it when needed
```

### Conflict Detection

```python
brain.add("Python version: 3.9")
brain.add("Python version: 3.11")  # → auto-flagged as CONFLICTED

brain.resolve_conflict("Python version")
# → resolves in favor of most recent, deprecates the old entry
```

---

## Claude Desktop & MCP Setup

OMem works as an MCP server for Claude Desktop and Cursor IDE, giving your AI persistent memory across every session.

```bash
pip install "omem-os[mcp]"
omem serve   # starts MCP stdio server
```

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": ["serve"]
    }
  }
}
```

**Full setup guide: [MCP_SETUP.md](./MCP_SETUP.md)**

### Tools available to Claude

| Tool | What it does |
|---|---|
| `remember` | Store a fact, decision, or preference |
| `recall` | Semantic search with type and time filters |
| `reflect` | Generate high-level insights from memory |
| `maintain` | Compress, forget, and optimize memory |
| `resolve_conflict` | Detect and fix contradictions |
| `query_codebase` | Natural language search over indexed codebase (file + line + callers) |
| `sync_codebase` | Re-index only files changed since last commit (git diff) |
| `ingest_codebase` | Full project baseline — parse all Python files via AST |

### Context window impact

> *"Won't injecting memory into every prompt bloat my context?"*

No. OMem is a **retrieval layer**, not an injection layer. From 5 000 memories, it returns **3–5 targeted results (~200–500 tokens)** — 97% less context than a naive approach, with exactly the relevant information. Context compression is the point.

---

## Project Memory — Codebase Indexing

Every AI coding tool today rediscovers your codebase from scratch on every session. Claude Code reads your files. Codex scans your directory tree. Cursor searches symbols in real-time. They spend tokens re-learning your architecture every single time — then forget it the moment the session ends.

**OMem fixes this permanently.**

One command indexes your entire project into a persistent, semantic knowledge base. From that point forward, any agent — Claude Code, Codex, Cursor, your own agent — can ask "where does auth happen?", "what calls this function?", "show me all database access patterns" and get an exact answer in milliseconds, without reading a single file.

### Quick Start

```python
brain = OMem()

# Index your project once — AST parsing across all Python files
count = brain.ingest_project(".")
# → 284 symbols indexed: 12 modules, 44 classes, 228 functions

# Query with natural language
results = brain.query_code("authentication token refresh")
# → auth/jwt.py:142   generate_token()
# → auth/jwt.py:178   refresh_token()       [calls: verify_claims, sign_payload]
# → middleware/auth.py:67  authenticate_request()  [calls: verify_token]

# After code changes — only re-parses git-diff'd files (milliseconds)
brain.sync_project(".")
# → 8 symbols updated across 3 changed files
```

### Or via CLI

```bash
omem ingest .                          # full baseline — parse entire project
omem sync .                            # incremental update via git diff
omem codebase "database error handling" # natural language search
```

### Why This Changes How AI Coding Tools Work

Today, when you ask Claude Code "find where database connections are pooled":

1. Claude searches files with `grep` / `find`
2. Reads multiple files to understand context
3. Consumes hundreds of tokens rediscovering your architecture
4. Forgets all of it next session

**With OMem project memory:**

1. Claude calls `query_codebase("database connection pooling")`
2. Gets back: exact file, line number, function signature, and related callers/dependencies
3. Uses ~50 tokens total
4. The knowledge persists — next session, next week, next year

This works for any agent that supports MCP: Claude Code, Cursor, your own OpenAI or Ollama agent via the Python API.

### What Gets Indexed

OMem parses your Python codebase using AST (Abstract Syntax Tree) analysis — no LLM required:

| Symbol Type | Example ID | What's Captured |
|---|---|---|
| Module | `auth.jwt` | Imports, file path, docstring |
| Class | `auth.jwt.TokenManager` | Methods, inheritance chain, signature |
| Function | `auth.jwt.generate_token` | Signature, dependencies, callers |
| Method | `auth.jwt.TokenManager.refresh` | Parent class, all calls made |

Symbols are stored with stable hierarchical IDs (`package.module.Class.method`) so incremental syncs can update exactly what changed.

### The Knowledge Graph Difference

Plain vector search finds the function you asked about. OMem's graph layer surfaces everything connected to it automatically:

```
Query: "token refresh logic"

Direct match:
  auth/jwt.py:178   refresh_token(user_id, old_token)

Graph context (depth=2):
  ← called by:  api/endpoints.py:44    POST /auth/refresh
  ← called by:  middleware/auth.py:91  auto_refresh_middleware
  →  calls:     auth/claims.py:23      verify_claims(token)
  →  calls:     crypto/signing.py:67   sign_payload(claims)
```

One query. Full dependency context. Zero file reading.

### Using With Claude Code and Cursor via MCP

Once OMem is running as your MCP server, Claude gets three tools for codebase navigation:

| MCP Tool | What Claude does with it |
|---|---|
| `ingest_codebase` | Full AST parse of the project — run once |
| `sync_codebase` | Re-index only files changed since last commit |
| `query_codebase` | Semantic + graph search returning file, line, callers |

Claude's behaviour changes fundamentally: instead of `grep -r "def authenticate"` across your entire project, it calls `query_codebase("authenticate user")` and gets back structured results with file paths, line numbers, signatures, and related functions — in a single tool call.

**Prompt to try after MCP setup:**
```
"Index this project. Now find everywhere we handle database errors
and show me what functions call the error handler."
```

> **Note:** Currently supports Python projects. Multi-language support is on the roadmap.

---

## Integrations

### LangChain

```python
from omem.integrations.langchain import OMemRetriever

retriever = OMemRetriever(omem_instance=brain)
chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
```

See [`examples/with_langchain.py`](./examples/with_langchain.py) for a full working example.

### OpenAI

See [`examples/with_openai.py`](./examples/with_openai.py) — shows before/after recall wrapping an OpenAI chat call.

### CrewAI

See [`examples/with_crewai.py`](./examples/with_crewai.py) — demonstrates namespace-isolated shared memory across agents.

### Ollama (local models)

See [`examples/with_ollama.py`](./examples/with_ollama.py) — cross-session memory with Ollama running locally.

---

## CLI Reference

```bash
# Setup
omem init                         # initialize at ~/.omem/brain.db
omem health                       # system health check

# Write
omem add "content" -i 0.9 -n myproject -t DECISION

# Read
omem search "query" -k 10 -c architecture -t recent
omem list -n myproject -t DECISION -l 50
omem inspect "query"              # debug retrieval scoring
omem stats && omem namespaces

# Maintenance
omem maintain --all               # compress + reflect + forget + dream

# Import / Export
omem export -f json -o dump.json
omem load dump.json -n myproject

# Project Memory (Codebase Indexing)
omem ingest [PATH]                # full AST parse — index entire project
omem sync [PATH]                  # incremental update via git diff (fast)
omem codebase "query"             # natural language search over indexed code

# Integrations
omem serve                        # MCP server for Claude / Cursor
omem dashboard --port 7900        # web memory dashboard
omem demo                         # end-to-end interactive walkthrough
omem benchmark --n 10000          # run performance test
```

---

## Architecture Details

### Memory Types (Auto-Classified on Every Add)

| Type | Examples |
|---|---|
| `SEMANTIC` | Facts, general knowledge |
| `DECISION` | Choices made, preferences |
| `CAUSAL` | Bug root causes, cause-effect chains |
| `PROCEDURAL` | How-to steps, workflows |
| `EPISODIC` | Events, experiences |
| `REFLECTION` | AI-generated insights |
| `ACTIVE` | Critical / urgent items |
| `WORKING` | Temporary, current-task context |

### Storage Backends

| Backend | Use Case |
|---|---|
| SQLite (default) | Local, single-process, zero config |
| In-memory | Testing, ephemeral agents |
| PostgreSQL | Production, multi-process, distributed |

---

## Configuration

```python
brain = OMem(
    backend="sqlite",              # "sqlite" | "memory" | "postgres"
    db_path="~/.omem/brain.db",
    model="all-MiniLM-L6-v2",
    embedding_provider="local",
)
```

```bash
HF_HUB_OFFLINE=1              # disable HuggingFace Hub checks (faster startup)
KMP_DUPLICATE_LIB_OK=TRUE     # fix OpenMP conflict on macOS/Anaconda
TOKENIZERS_PARALLELISM=false  # suppress tokenizer warning
```

---

## Roadmap

| Status | Feature |
|---|---|
| ✅ Shipped | Hybrid RAG, Auto-classification, Forgetting, Compression, MCP Server |
| ✅ Shipped | Truth Maintenance System, Knowledge Graph, Graph-RAG, PostgreSQL backend |
| ✅ Shipped | CLI, Dashboard, PyPI package (`pip install omem-os`) |
| In Progress | LOCOMO benchmark validation, distributed mode |
| Planned | Custom embedding providers (OpenAI, Cohere), memory versioning |

---

## FAQ

**Q: Does this run an LLM internally?**
A: No. OMem uses lightweight heuristics and a ~90 MB embedding model. No LLM API calls, no external network calls, no API keys required, no usage costs.

**Q: How is this different from ChromaDB or Pinecone?**
A: Those are vector storage systems. OMem is a memory *operating system* — with lifecycle management (importance → decay → forget), deduplication, conflict detection, knowledge graphs, and a cognitive maintenance cycle. Different category.

**Q: Will it bloat my agent's context window?**
A: The opposite. OMem retrieves 3–5 relevant memories per query (~300 tokens) instead of injecting your entire history. See the [Context FAQ in DEVELOPER.md](./DEVELOPER.md#memory-layer-faq--does-it-bloat-context).

**Q: Is it production-ready?**
A: v0.1.0 is the first stable release. The Core API is locked for the v0.1.x series. SQLite handles hundreds of thousands of memories in production. PostgreSQL backend is available for multi-process deployments. See the [Stability table](#stability) above for component-level status.

**Q: What about privacy?**
A: Everything runs 100% locally by default. Your memories never leave your machine. No telemetry. PostgreSQL backend is self-hosted.

**Q: Do I need Rust installed?**
A: Only if building from source for SIMD acceleration. `pip install omem-os` works without Rust — wheels ship with the pre-compiled extension.

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for setup instructions, branch workflow, testing requirements, and a list of good first issues.

**Python-only setup (no Rust required):**

```bash
git clone https://github.com/mohitkumarrajbadi/omem
cd omem
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Used By

*Be the first — [open an issue](https://github.com/mohitkumarrajbadi/omem/issues) to get listed.*

---

## License

MIT — see [LICENSE](./LICENSE)

---

<div align="center">

*If OMem makes your agents more capable, consider dropping a ⭐ — it helps others find the project.*

[Report Bug](https://github.com/mohitkumarrajbadi/omem/issues) · [Request Feature](https://github.com/mohitkumarrajbadi/omem/issues) · [Discussions](https://github.com/mohitkumarrajbadi/omem/discussions)

</div>
