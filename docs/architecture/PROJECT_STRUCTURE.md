# Project Structure

Quick reference for contributors. For the full architecture (layers, dependency rules, security model), see [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## Canonical Layout

```text
omem/
├── agent_state.py          # Product facade (Memory + State + Context + …)
├── agent_config.py         # Validated configuration
├── api.py                  # v1 OMem SDK (stable forever)
├── cli.py                  # CLI entrypoint
├── types.py                # Shared public contracts
│
├── memory/                 # Layer 1 — facts, experiences
│   ├── layer.py            # MemoryOS
│   └── org/                # Namespace hierarchy, scoped recall
├── state/                  # Layer 2 — goals, plans, checkpoints
├── context/                # Layer 3 — LLM context assembly
├── knowledge/              # Layer 4 — graph query facade
│   └── codebase/           # Project Memory (AST + code graph)
├── observe/                # Layer 5 — traces, replay, cost
│   └── dashboard/          # Local web UI (`omem dashboard`)
├── governance/             # Layer 6 — RBAC, retention, compliance
│   ├── layer.py            # GovernanceOS
│   ├── audit.py            # Audit trail
│   └── encryption.py       # AES-256-GCM field encryption
├── provenance/             # Cross-cutting lineage
├── runtime/                # Multi-agent coordination
├── cloud/                  # HTTP client + remote backend + server
├── backends/               # sqlite | postgres | (future) cloud
├── core/                   # Private engine — BrainTrace (do not import directly)
│   ├── engine/             # add, RAG, lifecycle, maintenance
│   ├── brain/              # dream, forget, TMS, classify, secrets
│   ├── graph/              # knowledge, causal, dependency
│   ├── retrieval/          # vector, fusion, ranker, embeddings
│   └── utils/              # metrics, logging, retry, snapshots
└── integrations/           # MCP, LangChain, CrewAI, LlamaIndex
```

Legacy import guard modules (raise `ImportError` in v3.0): `org.py`, `security.py`, `codebase.py`, `viz.py`, `classify.py`

---

## Contribution Map

| Goal | Start Here | Tests |
|------|------------|-------|
| Product facade | `omem/agent_state.py` | `tests/test_agent_state_facade.py` |
| Public SDK (v1) | `omem/api.py` | `tests/test_api.py` |
| Memory layer | `omem/memory/layer.py` | `tests/test_memory_os.py` |
| Org / namespace memory | `omem/memory/org/` | `tests/test_org_memory.py` |
| State checkpoints | `omem/state/layer.py` | `tests/test_state_engine.py` |
| Context assembly | `omem/context/engine.py` | `tests/test_context_engine.py` |
| Knowledge graph | `omem/knowledge/layer.py` | `tests/test_knowledge_os.py` |
| Codebase cognition | `omem/knowledge/codebase/` | manual + MCP smoke |
| Observability | `omem/observe/events.py` | `tests/test_observe.py` |
| Dashboard | `omem/observe/dashboard/` | `omem dashboard` |
| Governance | `omem/governance/layer.py` | `tests/test_governance.py` |
| Audit / encryption | `omem/governance/audit.py` | governance tests |
| Add / ingestion | `omem/core/engine/add.py` | `tests/test_memory_os.py` |
| Retrieval | `omem/core/engine/rag.py` | `tests/test_phase2_retrieval.py` |
| MCP tools | `omem/integrations/mcp_server.py` | `tests/test_cli.py` |
| Cloud server | `omem/cloud/server.py` | manual |
| Backends | `omem/backends/` | backend tests |

---

## Design Rules

1. **One front door** — `AgentState` for new users; `OMem` for v1 compat.
2. **Extend facades, not BrainTrace callers** — layers delegate to `core/`.
3. **No new top-level packages** without an ADR.
4. **Local-first** — base install must work offline with zero config.
5. **Security in governance** — audit, encryption, RBAC, retention.
6. **Tests stay offline** — no network calls in `tests/`.
7. **Rust for batch math** — array scoring in `rust/`, not Python hot loops.

---

## Repo Root (non-package)

```text
benchmarks/eval/     Evaluation scenarios (dev tooling — not shipped)
benchmarks/          Performance and research harnesses
deploy/docker/       Canonical Dockerfiles and compose files
docs/                Architecture, roadmap, guides
examples/            User-facing recipes
rust/                PyO3 native extension
tests/               Pytest suite
```

Docker (use `deploy/docker/` only — no root-level Dockerfile):

```bash
docker compose -f deploy/docker/docker-compose.local.yml up --build
```

---

## Related

- [ARCHITECTURE.md](./ARCHITECTURE.md) — full system design
- [ADR-001: Facade Pattern](./adr/001-facade-pattern.md)
- [ADR-002: Canonical Package Layout](./adr/002-canonical-package-layout.md)
- [ADR-003: v3.0 Release](./adr/003-v3-release.md)
- [Full Implementation Plan](../roadmap/FULL_IMPLEMENTATION_PLAN.md)
