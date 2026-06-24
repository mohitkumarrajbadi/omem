# Project Structure

OMem is organized around a small public API and modular internal engines. Keep new work close to the layer it belongs to, and avoid adding top-level modules unless they represent a durable v2 package boundary.

```text
omem/
├── api.py                  # Public OMem SDK facade
├── cli.py                  # CLI entrypoint
├── types.py                # Public dataclasses, enums, retrieval explanations
├── backends/               # SQLite, PostgreSQL, and future storage engines
├── codebase/               # Project memory and AST-based code indexing
├── core/
│   ├── engine/             # Add, RAG, lifecycle, maintenance mixins
│   ├── brain/              # Cognitive engines: dream, forget, TMS, scheduling
│   ├── graph/              # Knowledge graph substrate
│   ├── retrieval/          # Vector, fusion, ranking, KV cache
│   └── utils/              # Metrics, logging, retry, snapshots, concurrency
├── eval/                   # Evaluation scenarios and benchmark runner
├── integrations/           # MCP, LangChain, LlamaIndex, CrewAI adapters
├── security/               # Audit logging and encryption helpers
└── viz/                    # Local dashboard
```

## Contribution Map

| Goal | Start Here | Tests |
|---|---|---|
| Public SDK behavior | `omem/api.py` | `tests/test_api.py` |
| Add/ingestion pipeline | `omem/core/engine/add.py` | `tests/test_graph_substrate.py`, `tests/test_memory_os.py` |
| Retrieval quality | `omem/core/engine/rag.py`, `omem/core/retrieval/` | `tests/test_phase2_retrieval.py` |
| Memory lifecycle | `omem/core/engine/lifecycle.py`, `omem/core/brain/forgetting.py` | `tests/test_v070_cognitive.py` |
| Graph substrate | `omem/core/graph/knowledge.py` | `tests/test_graph_substrate.py` |
| MCP tools | `omem/integrations/mcp_server.py` | `tests/test_cli.py` plus manual MCP smoke test |
| CLI | `omem/cli.py` | `tests/test_cli.py`, `tests/test_cli.sh` |
| Backend support | `omem/backends/` | `tests/test_backends.py` |

## V2 Package Direction

The current repo keeps v2 functionality in the existing package layout to avoid a disruptive migration. New v2 modules should converge toward these package boundaries:

```text
omem.memory       # remember, recall, consolidate, forget, explain
omem.state        # snapshots, restore, rollback, fork, session state
omem.knowledge    # entities, facts, graph query, reasoning
omem.observe      # metrics, traces, replay, cost/context accounting
omem.eval         # memory, state, retrieval, and agent benchmarks
omem.governance   # policies, audit, retention, deletion workflows
omem.provenance   # source lineage, versions, confidence, attribution
omem.runtime      # scheduler, agent registry, coordination, recovery
```

Add compatibility facades gradually. The stable `from omem import OMem` path should continue to work through the v2 transition.

Target top-level facade:

```text
omem/agent_state.py   # AgentState — composes memory + state + context + knowledge
```

Cloud connector:

```text
omem/cloud/           # HTTP client, remote backend, FastAPI server
deploy/               # Linode provision, deploy, teardown scripts
```

See [Full Implementation Plan](../roadmap/FULL_IMPLEMENTATION_PLAN.md) and [Akamai / Linode Deployment Plan](../roadmap/AKAMAI_LINODE_DEPLOYMENT.md) for phased delivery.

## Design Rules

- Keep `OMem` as the friendly entrypoint.
- Prefer small, typed dataclasses for cross-layer contracts.
- Keep external services optional. Base install must remain local-first and zero-config.
- Do not add network calls to tests.
- Put public behavior in docs and examples before announcing it in README.
- Add a focused test for every change in `omem/core/`.
