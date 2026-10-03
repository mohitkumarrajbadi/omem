# YC Winter 2027 — paste answers

**TODOs** = you must replace before submit. Everything else is frozen narrative.

## Company

**Name:** OMem Labs  

**≤50 chars:** `Audit & rollback layer for AI agents`

**URL:** `https://github.com/mohitkumarrajbadi/omem`  
*(TODO: swap for omem.dev if that page is live and accurate)*

**Product link:** `https://github.com/mohitkumarrajbadi/omem` · README + `omem demo poison-recovery`  
**Login:** none for OSS demo

**What will you make?**
> OMem is the audit, governance, and state-rollback layer for multi-agent systems. Teams already have vector memory. They lack proof: what the agent knew at time T, who wrote it, that Org A cannot read Org B, and that erasure reached agent memory. We ship open-source governed memory (snapshot/rollback, encryption, audit export, MCP) and OMem Cloud (multi-tenant API with Postgres RLS and key rotation). Buyers are CISOs and platform/compliance teams—not developers shopping for better recall.

**Where live / after YC:**  
`TODO: City, Country / City, Country`  
Example shape: `Bengaluru, India / San Francisco, USA`

**Why location:**
> TODO: 2–3 sentences. Suggested draft — edit for truth:  
> I’m based in [city] while building. After YC the company would be US-oriented (SF or remote-first US entity) to sit next to enterprise design partners and the AI infra ecosystem, while keeping efficient eng execution from India.

## Progress

**How far along?**
> Working product. OSS with governed memory, AES-256-GCM, snapshot/rollback, provenance audit, MCP for Cursor/Claude, and a GovernedMem0 adapter. Cloud tech preview with fail-closed Postgres RLS, API key rotation, and a console focused on Memory, State, Governance, Team, Traces. Design-partner tech preview — not GA. Seeking one design partner on audit/tenant/erasure.

**How long / FT?**  
> TODO: `N months total; X months full-time. Solo technical founder; all product code founder-written with AI coding tools (Cursor).`

**Stack:**  
> Python, FastAPI, PostgreSQL + pgvector, RLS, SQLite, React console, MCP. Cursor for coding. We sit under the agent; we are not the chat model.

**People using?** TODO: `No` unless real users beyond you — then `Yes` + one sentence who  
**Revenue?** TODO: `No` unless money received — then `Yes` + amount/type

## Idea

**Why / expertise / need:**
> I built agent systems and kept hitting the production wall: recall demos are easy; prove, isolate, erase, and roll back is what blocks enterprise deploy. Vector memory is commoditizing; governance is the budget line.  
> TODO: one sentence on your background (Akamai / systems / whatever is true).

**Competitors / insight:**
> Mem0, Zep, LangMem, DIY RAG win on remember/recall. We don’t out-vector them. We own the layer above: immutable audit, org isolation in Postgres RLS, belief-state rollback, erasure that reaches the agent store. They treat governance as a checkbox; we treat it as the product.

**Money:**
> Open-core: OSS free; Cloud = governed tier (audit, RLS, encryption, retention). Near term: design-partner pilots.  
> TODO: e.g. `$0 today; target first paid pilot within 12 months` — use only numbers you’ll defend.

**Other ideas:** TODO or leave blank

## Founders

**Who writes code?**  
> I (Mohit Kumar Raj Badi) write all OMem OSS and Cloud product code. No non-founder employees. AI coding tools (Cursor) used heavily; architecture and shipping ownership are mine.

**Looking for cofounder?**  
> Yes — a technical cofounder with systems/security depth and/or a commercial cofounder who has sold infra or compliance tooling. I am not waiting to ship; I want someone who accelerates enterprise GTM.

## Equity / Curious / Batch

**Have you formed ANY legal entity yet?** TODO: Yes/No  
**Have you taken any investment yet?** TODO: Yes/No  
**Are you currently fundraising?** TODO: Yes/No  

**Why YC?**
> TODO — suggested draft:  
> YC is the fastest path to serious design partners, a clean US company shape, and a bar that forces focus on customers over features. OMem’s category only works next to enterprise AI buyers—not as a solo local OSS project forever.

**How did you hear about YC?** TODO  

**Batch:** Winter 2027

## Required uploads (you)

- [ ] Founder video ([VIDEO.md](./VIDEO.md))  
- [ ] Optional longer demo ≤3 min  
- [ ] Company description = one-liner above  
- [ ] All TODOs above replaced with truth
