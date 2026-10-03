<div align="center">

[![PyPI](https://img.shields.io/pypi/v/omem-os?style=for-the-badge&color=brightgreen)](https://pypi.org/project/omem-os/)
[![CI](https://img.shields.io/github/actions/workflow/status/mohitkumarrajbadi/omem/ci.yml?branch=main&style=for-the-badge)](https://github.com/mohitkumarrajbadi/omem/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](./LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Cursor%20%2F%20Claude-purple?style=for-the-badge)](./docs/guides/MCP_SETUP.md)

<br>

# OMem

### Governed, Auditable Memory and State Management for AI Agents

**The audit, governance, and state-rollback layer for multi-agent systems.**

AES-256-GCM encryption · belief revision · git-like snapshot / rollback ·
provenance audit export · tenant hardening · MCP for Cursor & Claude.

**Current development line: 0.0.3 (unreleased).** Latest public artifacts:
0.0.1 on PyPI and v0.0.2 on GitHub.

[Quickstart](#quickstart) · [Enterprise controls](#enterprise-controls) ·
[Limits](./docs/LIMITATIONS.md) · [Design partners](./docs/design-partner/README.md) ·
[Architecture](#architecture)

</div>

---

## Who this is for

CISOs, lead architects, and compliance teams who must make agents defensible
under enterprise data policy and the EU AI Act: provenance, auditability,
right to erasure, and memory isolation.

OMem is **not** competing as another Mem0 or Zep. Keep your semantic store if
you already have one. Wrap the agent in OMem when you need to prove what it
knew, roll it back, and export the trail.

> *Prove what the agent knew at time T. Show who wrote that fact.
> Show that Org A cannot read Org B. Show that erasure reached agent memory,
> not only the source database.*

---

## Quickstart

```bash
pip install omem-os
```

Wrap an existing agent in an OMem audit context:

```python
from omem import AgentState

with AgentState(session_id="payments-agent") as agent:
    agent.remember("Wire beneficiary is acct-100")
    snap = agent.snapshot(label="before-tool-call")
    print(agent.governance.export_audit(format="json"))
```

That is the product: durable memory under a session, a recoverable checkpoint,
and a machine-readable audit export. Set `OMEM_ENCRYPTION_KEY` for AES-256-GCM
at rest. Call `agent.rollback(snap.id)` to restore the prior state.

```bash
pip install "omem-os[mcp]"
omem init          # durable DB + one MCP JSON line
omem init --cursor # merge into ~/.cursor/mcp.json
```

---

## Enterprise controls

| Control | What OMem does |
|---|---|
| **AES-256-GCM encryption** | Field-level encryption at rest when `OMEM_ENCRYPTION_KEY` is set |
| **Belief revision** | Superseded facts stay in the trail; current belief is explicit |
| **Git-like state** | `snapshot`, `rollback`, `fork` / `clone`, `checkpoint` / `resume` |
| **Provenance audit** | `governance.export_audit` / CLI JSON for SecOps and compliance review |
| **Tenant hardening** | Namespace scopes and `harden_namespace` primitives; live Postgres RLS is enforced in OMem Cloud |
| **Right to erasure path** | Retention and deletion policies on the governance layer — erasure must reach agent memory and logs |

Design-partner pack: [docs/design-partner/](./docs/design-partner/README.md) ·
Guarantees: [docs/guarantees/TENANT_HARDENING.md](./docs/guarantees/TENANT_HARDENING.md) ·
Limits: [docs/LIMITATIONS.md](./docs/LIMITATIONS.md)

---

## Layer maturity

| Layer | Status |
|-------|--------|
| Memory | Stable — local API and lifecycle covered by the OSS test suite |
| State | Stable — snapshots, rollback, forks, and checkpoints covered |
| Context | Stable — token budgeting and context assembly covered |
| Knowledge | Beta — link/query/reasoning covered; Python-only AST index remains Alpha |
| Observe | Beta — local traces **Stable**; OTLP JSON export/push covers **in-process** ObserveOS events only (not full auto-instrumentation); HTTP-path OTel is **omem-cloud only** (partial `/v1/remember`); dashboard remains Alpha |
| Governance | Stable for local audit/retention/encryption; tenant and cloud enforcement remain Beta |

For managed, multi-tenant hosting see [OMem Cloud](../omem-cloud/)
(**design-partner tech preview** — not GA).

---

## MCP for coding agents

OMem attaches as an MCP server so Cursor, Claude Code, and OpenCode share the
same governed store across sessions.

```bash
pip install "omem-os[mcp]"
omem init
```

Paste the printed JSON into the agent MCP config, or run `omem init --cursor`.

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": ["serve", "--namespace", "personal", "--db-path", "~/.omem/brain.db"]
    }
  }
}
```

Ready-made configs: `deploy/mcp/claude_code.mcp.json`, `opencode.mcp.json`,
`cursor.mcp.json`. Personal multi-tool setup:
[`docs/guides/PERSONAL_MCP.md`](./docs/guides/PERSONAL_MCP.md).

Core tools focus on decisions, provenance, and session continuity
(`remember`, `recall`, `lineage`, `remember_decision`, `recall_decisions`).
The Python AST codebase index is Alpha and is not the enterprise pitch.

---

## OMem Cloud

**OMem Cloud** is the commercial multi-tenant service on the same core:
managed API, PostgreSQL + pgvector, background worker, React ops console,
Prometheus/Grafana, and Linode/Akamai deploy. **Status: design-partner tech
preview — not GA.**

| Feature | omem-os (open source) | omem-cloud (commercial) |
|---|---|---|
| Local SQLite memory + audit | ✅ | ✅ |
| Snapshot / rollback / fork | ✅ | ✅ |
| MCP server | ✅ | ✅ |
| Multi-tenant REST API | — | ✅ |
| Postgres RLS + team keys | design / beta | preview (operator gates) |
| Linode / Akamai Terraform | — | ✅ |
| SLA support | — | planned for GA |

> **Access:** [https://omem.dev/cloud](https://omem.dev/cloud) · [support@omem.dev](mailto:support@omem.dev)

### Enterprise PostgreSQL backend (open source)

```python
from omem.backends.postgres_enterprise import EnterprisePostgresBackend

backend = EnterprisePostgresBackend(
    connection_string="postgresql://omem:secret@localhost:5432/omem",
    org_id="acme-corp",
    user_id="alice",
)
```

---

## Architecture

Four product layers (Memory, State, Context, Knowledge). Governance and
Observability wrap every operation.

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent / MCP Client                      │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│   Memory      │    State     │   Context    │   Knowledge     │
│  remember /   │  snapshot /  │  budgeted    │  entity graph   │
│  recall       │  rollback /  │  pack        │  (AST index     │
│               │  fork        │              │   Alpha)        │
├──────────────┴──────────────┴──────────────┴─────────────────┤
│  Governance & Observability  (cross-cutting — every op)       │
│  audit · retention · encryption · tenants · traces            │
├─────────────────────────────────────────────────────────────┤
│  Backend: SQLite (local) │ PostgreSQL (enterprise / cloud)    │
└─────────────────────────────────────────────────────────────┘
```

Canonical reference: [docs/architecture/ARCHITECTURE.md](./docs/architecture/ARCHITECTURE.md).

### State forking

```python
agent = AgentState(session_id="planner")
snap = agent.snapshot(label="decision-point")

plan_a = agent.clone("plan-postgres")
plan_b = agent.clone("plan-dynamodb")
# Independent memories and state per fork; rollback via snap.id
```

---

## CLI

```bash
omem init                                       # durable DB + MCP line
omem serve                                      # MCP server for Cursor / Claude
omem remember "Decision: use GraphQL for the API" -i 0.9
omem recall "database decision" -k 5
omem governance audit --format json             # compliance export
omem status                                     # session health dashboard
```

---

## Install options

```bash
pip install omem-os                     # core (SQLite)
pip install "omem-os[mcp]"              # + MCP server
pip install "omem-os[postgres]"         # + PostgreSQL backend
pip install "omem-os[secure]"           # + cryptography for AES-256-GCM
pip install "omem-os[all]"              # everything open-source
# omem-cloud (managed API) → https://omem.dev/cloud
```

From source:

```bash
git clone https://github.com/mohitkumarrajbadi/omem
cd omem
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Stability

| Component | Status |
|---|---|
| Core API: remember, recall, snapshot, rollback, export_audit | Stable — local coverage |
| SQLite backend | Stable |
| MCP server (Cursor / Claude) | Beta — no real-client CI |
| PostgreSQL backend | Beta — live RLS verification belongs to omem-cloud |
| Codebase AST indexing | Alpha — not the enterprise pitch |
| Local dashboard | Alpha |
| Managed cloud API (omem-cloud) | Design-partner preview |

Diligence artifacts (retrieval suites, KV probes) live under
[`distribution/`](./distribution/) and are **not** the product claim. See
[docs/LIMITATIONS.md](./docs/LIMITATIONS.md).

---

## FAQ

**Does OMem replace Mem0 / Zep / a vector DB?**
No. Those systems optimize recall. OMem is the governance and rollback layer.
Use them for search if you already do; route through OMem when you need audit,
erasure, and recoverable state.

**Does OMem call an LLM internally?**
Not on the default path. Optional embedding providers can call external APIs
when you configure them.

**Is my data sent anywhere?**
No. Default storage is local SQLite at `~/.omem/brain.db`. Enterprise Postgres
runs in your infrastructure. No telemetry dependency.

**How does multi-tenant isolation work?**
Application namespace / org scoping in omem-os; Postgres RLS and key binding
in omem-cloud. OSS unit tests cover scoping; live RLS is an omem-cloud operator
gate (`make rls-proof`).

---

## License

MIT — see [LICENSE](./LICENSE).

---

<div align="center">

**[Limits](./docs/LIMITATIONS.md) · [MCP Setup](./docs/guides/MCP_SETUP.md) · [Personal MCP](./docs/guides/PERSONAL_MCP.md) · [OMem Cloud](https://omem.dev/cloud)**

</div>
