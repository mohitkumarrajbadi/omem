<div align="center">

[![PyPI](https://img.shields.io/pypi/v/omem-os?style=for-the-badge&color=brightgreen)](https://pypi.org/project/omem-os/)
[![CI](https://img.shields.io/github/actions/workflow/status/mohitkumarrajbadi/omem/ci.yml?branch=main&style=for-the-badge)](https://github.com/mohitkumarrajbadi/omem/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](./LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Claude%20%2F%20Cursor-purple?style=for-the-badge)](./docs/guides/MCP_SETUP.md)
[![GitHub Stars](https://img.shields.io/github/stars/mohitkumarrajbadi/omem?style=for-the-badge)](https://github.com/mohitkumarrajbadi/omem/stargazers)

<br>

# OMem

### The Memory Operating System for AI Agents

Persistent memory, Graph-RAG, sleep cycles, codebase memory, MCP, and local-first retrieval in one Python package.

**Zero config. Zero API costs. Local by default. Built for agents that should remember.**

[Quick Start](#quick-start) · [Why OMem](#why-omem) · [MCP](#claude-desktop--cursor-mcp) · [Project Memory](#project-memory-for-codebases) · [Architecture](#architecture) · [V2 Roadmap](./docs/roadmap/ROADMAP.md) · [Contributing](./CONTRIBUTING.md)

</div>

---

## Quick Start

```bash
pip install omem-os
```

```python
from omem import OMem

brain = OMem()  # persists to ~/.omem/brain.db

brain.add("Alice prefers dark mode and Python for backend work.")
brain.add("Critical bug: payment retry can duplicate charges.", importance=0.95)
brain.add("Decision: migrate public API from REST to GraphQL.")

for memory in brain.recall("What should I know about payment bugs?", k=3):
    print(memory.content)
```

Run maintenance when the agent is idle:

```python
brain.sleep()  # compress, forget, reflect, consolidate
```

Inspect why something was recalled:

```python
for item in brain.inspect("payment bugs"):
    print(item.explain())
```

## Why OMem

Most agent memory systems are either conversation buffers or vector databases. They store text, but they do not manage memory.

OMem is a memory layer with:

| Capability | What it gives your agent |
|---|---|
| Persistent memory | Cross-session continuity without stuffing prompts |
| Hybrid retrieval | Vector + keyword + recency + importance + confidence + graph signals |
| Graph-RAG | Entities and relationships connect related memories |
| Sleep cycle | Compresses, forgets, reflects, and consolidates |
| Truth maintenance | Detects stale or conflicting facts |
| Project memory | Indexes codebases for fast AI coding context |
| MCP server | Works with Claude Desktop, Cursor, and other MCP clients |
| Local-first storage | SQLite by default, PostgreSQL for production |

## Before / After

Without OMem:

```python
agent.chat("My name is Alice and I prefer dark mode.")
# New process tomorrow:
agent.chat("What's my display preference?")
# "I don't have information about your preferences."
```

With OMem:

```python
brain.add("User name: Alice. Prefers dark mode.")
context = brain.recall("display preference")
agent.chat("What's my display preference?", context=context)
# "You prefer dark mode, Alice."
```

## Benchmarks

Tested on Apple M-series with 5,000 memories, 500 queries, and `all-MiniLM-L6-v2`.
Reproduce with:

```bash
python benchmarks/competitor.py
```

| System | Setup | Add ops/s | RAG ops/s | RAG p99 |
|---|---:|---:|---:|---:|
| **OMem** | **4.0 ms** | **65** | **292** | **20 ms** |
| ChromaDB | 507 ms | 277 | 280 | 4 ms |
| LanceDB | 8 ms | 82,000 | 182 | 7 ms |
| Mem0 | 15,000+ ms | < 1 | 18 | 638 ms |

OMem's `add()` does more than raw storage: embed, classify, deduplicate, sync the entity graph, and persist asynchronously. The benchmark is meant to compare useful agent memory behavior, not just vector insert speed.

## Claude Desktop / Cursor MCP

Install with MCP extras:

```bash
pip install "omem-os[mcp]"
omem serve
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

MCP tools include:

| Tool | Purpose |
|---|---|
| `remember` | Store facts, preferences, decisions, and events |
| `recall` | Retrieve relevant memories with filters |
| `reflect` | Generate higher-level insights |
| `maintain` | Run memory maintenance |
| `resolve_conflict` | Handle contradictions |
| `ingest_codebase` | Index a project |
| `sync_codebase` | Incrementally update project memory |
| `query_codebase` | Ask natural-language questions about code |

Full guide: [docs/guides/MCP_SETUP.md](./docs/guides/MCP_SETUP.md)

## Project Memory for Codebases

OMem can index a Python project into a persistent knowledge graph so coding agents do not rediscover the same architecture every session.

```python
from omem import OMem

brain = OMem()
brain.ingest_project(".")

for result in brain.query_code("database connection pooling"):
    print(result)
```

CLI:

```bash
omem ingest .
omem sync .
omem codebase "where do we refresh auth tokens?"
```

OMem captures modules, classes, functions, methods, imports, signatures, callers, and dependency edges. Current codebase indexing is Python-first; multi-language support is on the roadmap.

## Architecture

```text
Agent / App / MCP Client
        |
        v
OMem Public API
        |
        +-- Memory Engine: add, recall, inspect, sleep
        +-- Brain Logic: importance, forgetting, TMS, dream, scheduler
        +-- Knowledge Graph: entities, nodes, relations, evidence
        +-- Retrieval: vector, keyword, recency, confidence, graph fusion
        +-- Backends: SQLite, PostgreSQL, in-memory
```

Repository map:

| Path | Purpose |
|---|---|
| `omem/api.py` | Public SDK facade |
| `omem/core/engine/` | Add, retrieval, lifecycle, maintenance |
| `omem/core/brain/` | Cognitive memory engines |
| `omem/core/graph/` | Knowledge graph substrate |
| `omem/core/retrieval/` | Fusion, ranking, vector and KV retrieval |
| `omem/backends/` | Storage backends |
| `omem/integrations/` | MCP, LangChain, LlamaIndex, CrewAI |
| `omem/codebase/` | Project memory and AST indexing |
| `tests/` | Unit and integration tests |

See [docs/architecture/PROJECT_STRUCTURE.md](./docs/architecture/PROJECT_STRUCTURE.md) for the contributor map.

## V2: AI State Infrastructure

The current repo already has the memory core: persistent memory, graph substrate, multi-objective retrieval, sleep cycles, MCP, and codebase memory.

V2 expands OMem into broader AI state infrastructure:

| Layer | Goal |
|---|---|
| Memory | Store, retrieve, consolidate, forget, explain |
| State | Save, restore, rollback, fork agent execution state |
| Knowledge | Facts, concepts, graph reasoning |
| Observability | Metrics, traces, replay, context efficiency |
| Evaluation | Recall quality, agent continuity, benchmark reports |
| Governance | Policies, retention, deletion, audit |
| Provenance | Source lineage, versions, confidence, attribution |
| Runtime | Agent registry, scheduling, sync, recovery |

Read the roadmap: [docs/roadmap/ROADMAP.md](./docs/roadmap/ROADMAP.md)

## Integrations

```python
# LangChain
from omem.integrations.langchain import OMemRetriever

retriever = OMemRetriever(omem_instance=brain)
```

Examples:

- [OpenAI](./examples/with_openai.py)
- [Ollama](./examples/with_ollama.py)
- [LangChain](./examples/with_langchain.py)
- [CrewAI](./examples/with_crewai.py)
- [Memory assistant](./examples/memory_assistant.py)

## CLI

```bash
omem health
omem add "Architecture decision: use PostgreSQL for shared memory" -i 0.9
omem search "database decision" -k 5
omem inspect "database decision"
omem maintain --all
omem dashboard --port 7900
omem serve
```

## Install From Source

Python-only development:

```bash
git clone https://github.com/mohitkumarrajbadi/omem
cd omem
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

Rust is only needed when changing the native acceleration layer in `rust/`.

## Contributing

OMem is ready for team-based v2 work. Start here:

- [CONTRIBUTING.md](./CONTRIBUTING.md) - setup, branch workflow, tests, good first issues
- [docs/architecture/PROJECT_STRUCTURE.md](./docs/architecture/PROJECT_STRUCTURE.md) - where to make changes
- [docs/roadmap/ROADMAP.md](./docs/roadmap/ROADMAP.md) - implementation lanes
- [GOVERNANCE.md](./GOVERNANCE.md) - review and release standards
- [SUPPORT.md](./SUPPORT.md) - where to ask for help

Good first contribution lanes:

| Lane | Example |
|---|---|
| Docs | Add recipes and integration examples |
| Tests | Add coverage for lifecycle or namespace behavior |
| CLI | Improve output, export formats, flags |
| Integrations | Add LangGraph, AutoGen, OpenAI Agents examples |
| Benchmarks | Add reproducible retrieval quality scenarios |

If OMem helps your agent remember something useful, star the repo and share what you built in Discussions. That helps contributors find the project and helps maintainers prioritize real use cases.

## Stability

| Component | Status |
|---|---|
| Core API: `add`, `recall`, `sleep`, `inspect` | Stable for v0.1.x |
| SQLite backend | Stable |
| PostgreSQL backend | Beta |
| MCP server | Stable |
| LangChain integration | Beta |
| CrewAI integration | Alpha |
| Codebase memory | Alpha |
| Dashboard | Beta |

## FAQ

**Does OMem call an LLM internally?**
No. Base OMem uses local embeddings and heuristics. No API keys are required.

**Will memory bloat my context window?**
No. OMem retrieves a small set of relevant memories instead of injecting full history.

**How is this different from a vector database?**
Vector databases store vectors. OMem manages memory lifecycle, confidence, graph relations, conflict handling, consolidation, and agent integrations.

**Is my data sent anywhere?**
No. OMem is local-first. SQLite is the default backend.

**Do I need Rust?**
No for normal use. Rust is only needed for native acceleration development.

## License

MIT - see [LICENSE](./LICENSE).
