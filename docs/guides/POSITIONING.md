# Positioning — what OMem is (and is not)

**Category:** Agent State infrastructure (Memory OS + governed Cloud SKU)  
**Status:** Tech preview — not GA. Not SOC2.

## One sentence

OMem is the **operational safety net** for production agents: durable run state (checkpoint / resume / rollback) plus governance (audit / encryption / tenancy) — not a collaborative shared-facts memory server.

## The problem we own

Agents are processes. Processes die. Chat history is not:

1. a **notebook** across sessions  
2. a **save game** when a job dies at step 7  
3. a **locked cabinet** between tenants  

Libraries that optimize recall (“remember my preference”) do not replace those three.

## The problem we do *not* own as the headline

“Shared persistent knowledge across agents/teams with deep hybrid search and memory decay.”

That is a **collaborative brain** product. Useful — orthogonal. If you already have Mem0 / Zep / a shared-memory API, keep it for facts; use OMem when you need **state + governance**. Optional bridge: `GovernedMem0`.

## Name collision

Other GitHub projects may also brand “omem.” We are not them.

| Signal | This repo (`mohitkumarrajbadi/omem`) | Typical memory-brain server |
|--------|--------------------------------------|-------------------------------|
| PyPI | `omem-os` | often a hosted API / Rust server |
| Lead verbs | `checkpoint` · `resume` · `rollback` · `audit` | `store` · `search` · `share` · `decay` |
| Proof demo | `omem demo kill-resume` / `poison-recovery` | hybrid retrieval / space sharing |
| Buyer | Platform + security (prove / isolate / undo) | Builders wanting shared facts |

## Product surfaces

| Surface | Role |
|---------|------|
| **omem-os** (MIT) | Local Memory OS + state + MCP into Cursor/OpenCode |
| **omem-cloud** (commercial) | Multi-tenant Agent State Cloud — API, RLS, console (preview) |

Memory (`remember` / `recall`) is a **projection** on top of state — not the whole product.

## What we claim / do not claim

**Claim (demoable):** kill-resume, poison → rollback, audit export, local MCP, design-partner Cloud gates on a controlled stack.

**Do not claim:** Cloud GA, SOC2, “better recall than Mem0,” multi-region HA, exactly-once external side effects.

See [LIMITATIONS.md](../LIMITATIONS.md).

## Pitch line (reuse)

> Memory libraries solve recall. Agents still die mid-run and fail risk review. OMem is Agent State + governance — notebook, save game, locked cabinet.
