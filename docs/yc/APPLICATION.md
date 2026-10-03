# YC Winter 2027 — paste answers

Fill `[BRACKETS]` with truth only. Copy into the form. Align with [NARRATIVE.md](./NARRATIVE.md).

## Company

**Name:** OMem Labs  

**≤50 chars:** `Audit & rollback layer for AI agents`

**URL:** `[YOUR SITE OR GITHUB]`

**Product link:** `[DEMO URL OR GITHUB README]` · creds if needed: `[NONE / user pass]`

**What will you make?**
> OMem is the audit, governance, and state-rollback layer for multi-agent systems. Teams already have vector memory. They lack proof: what the agent knew at time T, who wrote it, that Org A cannot read Org B, and that erasure reached agent memory. We ship open-source governed memory (snapshot/rollback, encryption, audit export, MCP) and OMem Cloud (multi-tenant API with Postgres RLS and key rotation). Buyers are CISOs and platform/compliance teams—not developers shopping for better recall.

**Where live / after YC:** `[City, Country] / [City, Country]`  

**Why location:** `[2–3 sentences]`

## Progress

**How far along?**
> Working product. OSS with governed memory, AES-256-GCM, snapshot/rollback, provenance audit, MCP for Cursor/Claude, and a GovernedMem0 adapter. Cloud tech preview with fail-closed Postgres RLS, API key rotation, and a console focused on Memory, State, Governance, Team, Traces. Design-partner tech preview — not GA. Seeking one design partner on audit/tenant/erasure.

**How long / FT?**  
> `[N months total; X months full-time. Solo technical founder; all product code founder-written with AI coding tools.]`

**Stack:**  
> Python, FastAPI, PostgreSQL + pgvector, RLS, SQLite, React console, MCP. Cursor for coding. We sit under the agent; we are not the chat model.

**People using?** `[Yes/No — Yes only if real users beyond you]`  
**Revenue?** `[Yes/No — Yes only if money received]`

## Idea

**Why / expertise / need:**
> I built agent systems and kept hitting the production wall: recall demos are easy; prove, isolate, erase, and roll back is what blocks enterprise deploy. Vector memory is commoditizing; governance is the budget line. `[1 sentence on your relevant background.]`

**Competitors / insight:**
> Mem0, Zep, LangMem, DIY RAG win on remember/recall. We don’t out-vector them. We own the layer above: immutable audit, org isolation in Postgres RLS, belief-state rollback, erasure that reaches the agent store. They treat governance as a checkbox; we treat it as the product.

**Money:**
> Open-core: OSS free; Cloud = governed tier (audit, RLS, encryption, retention). Near term: design-partner pilots. `[Honest 12-month revenue range or “$0 until first pilot”.]`

**Other ideas:** `[optional list]`

## Founders

**Who writes code?**  
> I (Mohit Kumar Raj Badi) write all OMem OSS and Cloud product code. No non-founder employees. AI coding tools (Cursor) used heavily; architecture and shipping ownership are mine.

**Looking for cofounder?**  
> Yes — a technical cofounder with systems/security depth and/or a commercial cofounder who has sold infra or compliance tooling. I am not waiting to ship; I want someone who accelerates enterprise GTM.

## Equity / Curious / Batch

**Entity / investment / fundraising:** `[Yes/No each — truth]`  
**Why YC:** `[2–4 sentences]`  
**How heard:** `[source]`  
**Batch:** Winter 2027

## Required uploads (you)

- [ ] Founder video ≤100MB (script in [DEMO.md](./DEMO.md))  
- [ ] Optional product demo file ≤3 min  
- [ ] Company description field filled (one-liner above)
