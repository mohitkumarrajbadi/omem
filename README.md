<div align="center">

[![PyPI](https://img.shields.io/pypi/v/omem-os?style=for-the-badge&color=brightgreen)](https://pypi.org/project/omem-os/)
[![CI](https://img.shields.io/github/actions/workflow/status/mohitkumarrajbadi/omem/ci.yml?branch=main&style=for-the-badge)](https://github.com/mohitkumarrajbadi/omem/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](./LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Claude%20%2F%20Cursor-purple?style=for-the-badge)](./docs/guides/MCP_SETUP.md)
[![STATE-Bench](https://img.shields.io/badge/STATE--Bench-81.2%2F100-brightgreen?style=for-the-badge)](./benchmarks/state_bench.py)
[![GitHub Stars](https://img.shields.io/github/stars/mohitkumarrajbadi/omem?style=for-the-badge)](https://github.com/mohitkumarrajbadi/omem/stargazers)

<br>

# OMem

### Persistent State Infrastructure for AI Agents

Memory · Session State · Context Engine · Knowledge Graph · Observability · Governance · Multi-Agent Runtime

**One SDK. Every layer your agent needs to remember, reason, recover, and be audited.**

[60-Second Start](#60-second-start) · [Why OMem](#why-omem) · [State Forking](#state-forking) · [Explainability](#explainability) · [STATE-Bench](#state-bench) · [MCP](#claude-desktop--cursor-mcp) · [Architecture](#architecture)

</div>

---

## 60-Second Start

```bash
pip install omem-os
```

```python
from omem import AgentState

with AgentState(session_id="my-agent") as agent:
    # Memory
    agent.remember("FastAPI uses Pydantic v2 for validation", importance=0.9)

    # State
    agent.set_goal("Build a production REST API")
    agent.set_plan(["Design schema", "Write models", "Add tests", "Deploy"])

    # Knowledge graph
    agent.learn("FastAPI", "uses", "Pydantic")

    # Context — token-efficient prompt assembly
    ctx = agent.build_context("implement auth middleware", budget_tokens=4000)
    # → pass ctx.text to your LLM; saves ~40% tokens vs naive concatenation

    # Explainability
    print(agent.explain("What framework should I use?").format())

    # Snapshot — like git commit for agent state
    agent.snapshot(label="before-auth")
```

```bash
# Or from the CLI (set once, use everywhere)
export OMEM_SESSION=my-agent
omem agent remember "FastAPI is the primary framework"
omem agent status
omem agent explain "framework choice"
omem bench --suite state --suite context
```

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

Most agent frameworks bolt on a vector store and call it "memory." OMem is different — it is a **complete state infrastructure layer** that answers the questions production agents actually ask:

> *Can I reproduce a decision? Can I roll back? Can I fork? Can I audit? Can I recover from a crash?*

| Layer | What you get |
|---|---|
| **Memory OS** | Hybrid retrieval: vector + keyword + recency + importance + graph |
| **State OS** | Git-like snapshots, rollback, fork, checkpoint, resume |
| **Context Engine** | Token-efficient prompt assembly — ~40% savings vs. naive inclusion |
| **Knowledge Graph** | Typed entity-relation graph with multi-hop reasoning |
| **Explainability** | Full score breakdown: *why* each memory was recalled |
| **Observability** | Per-operation traces, metrics, OpenTelemetry export |
| **Provenance** | Lineage chain for every memory and state change |
| **Governance** | Retention policies, RBAC, audit log, deletion workflows |
| **Multi-Agent Runtime** | Agent registry, heartbeats, state sync, crash recovery |
| **Org Memory** | Team / org namespace hierarchy with memory promotion |
| **MCP Server** | `omem serve` — works with Claude Desktop, Cursor, CrewAI |
| **Local-first** | SQLite default, PostgreSQL for production, zero API keys |

---

## State Forking

The killer feature no other memory system has. Evaluate **multiple realities in parallel**:

```python
from omem import AgentState

agent = AgentState(session_id="planner")
agent.set_goal("Evaluate API frameworks")
agent.remember("FastAPI is fast but newer")
agent.snapshot(label="decision-point")

# Fork two plans — each gets its own independent state
plan_a = agent.clone("plan-fastapi")
plan_b = agent.clone("plan-django")

plan_a.set_goal("Go with FastAPI — evaluate performance")
plan_b.set_goal("Go with Django — evaluate ecosystem")

# Each fork runs independently; merge back when done
```

---

## Explainability

Enterprise-grade transparency into every recall decision:

```python
report = agent.explain("What database should I use?", k=5)
print(report.format())
```

```
╔══ Explain: 'What database should I use?'
║  session=planner  namespace=default  mode=recall  elapsed=12.3ms
║  goal relevance [████████░░] 82%  →  'Evaluate API frameworks'
╠════════════════════════════════════════════════════════════
║  [1] id=45451792a80b  score=[██████████░░░░░] 0.8821
║      vector=0.721  keyword=0.850  recency=1.000  importance=0.900
║      confidence=1.000  graph=0.760  frequency=0.120
║      keywords: database, postgresql
║      provenance: depth=3  create → update → share
║      knowledge: PostgreSQL –[supports]→ JSONB; Redis –[used-for]→ caching
╚════════════════════════════════════════════════════════════
```

---

## STATE-Bench

The only benchmark that measures what agent state systems actually need:

```bash
omem bench              # run all suites (~2 seconds)
omem bench --json       # CI-friendly JSON output
```

| Suite | OMem Score | What it measures |
|---|---|---|
| **State** | 100 / 100 | Snapshot/rollback fidelity, fork independence, checkpoint recovery |
| **Explainability** | 100 / 100 | Score decomposition coverage, provenance tracing, explain latency |
| **Concurrency** | 100 / 100 | Parallel agent throughput (3,000+ ops/sec) |
| **Context** | 67 / 100 | Token savings, budget adherence, build latency |
| **Continuity** | 67 / 100 | Crash recovery, workflow resume fidelity |
| **Memory** | 54 / 100 | Recall@K, MRR, latency |
| **Overall** | **81 / 100** | Cite as `STATE-Bench v1.0` |

Contribute your system's results: [STATE-Bench Leaderboard](https://github.com/omem-ai/state-bench)

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
| `omem/agent_state.py` | Product facade (`AgentState`) |
| `omem/memory/` | Layer 1 — memory + org namespaces |
| `omem/state/` | Layer 2 — checkpoints, fork, rollback |
| `omem/context/` | Layer 3 — token-budget context assembly |
| `omem/knowledge/` | Layer 4 — graph + codebase cognition |
| `omem/observe/` | Layer 5 — traces + dashboard |
| `omem/governance/` | Layer 6 — audit, encryption, RBAC |
| `omem/core/` | Private engine (BrainTrace) |
| `omem/backends/` | SQLite, PostgreSQL storage |
| `omem/integrations/` | MCP, LangChain, LlamaIndex, CrewAI |
| `benchmarks/eval/` | Evaluation scenarios (dev tooling) |
| `tests/` | Unit and integration tests |
| `deploy/docker/` | Docker images and compose files |

See [docs/architecture/ARCHITECTURE.md](./docs/architecture/ARCHITECTURE.md) for the full layout.

## V3: Persistent State Infrastructure

OMem v3 is the six-layer Agent State platform. Use `AgentState` as the single entry point:

```python
from omem import AgentState
```

See [docs/architecture/ARCHITECTURE.md](./docs/architecture/ARCHITECTURE.md) and [CHANGELOG.md](./CHANGELOG.md#300---2026-06-25) for v3 migration notes.

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
