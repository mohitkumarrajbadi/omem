# Design-partner outreach

Send **5 personalized notes** this week. Same ask every time: 20-minute eval of audit / tenant / erasure — not a sales deck.

## Who to target (pick real people)

| Persona | Where to find | Why |
|---------|---------------|-----|
| Platform / AI eng lead | Companies shipping internal agents | Feels the “can’t prove what agent knew” pain |
| AppSec / CISO staff eng | Regulated or enterprise SaaS | Owns audit / isolation questions |
| Ex-Mem0 / LangChain user | Twitter, Discord, GitHub issues | Already bought “memory”; missing governance |

Skip: random “AI startup” founders with no compliance pressure.

## Email (copy, personalize first line)

**Subject:** 20 min — prove / rollback agent memory?

```
Hi [Name],

I’m Mohit, building OMem — the audit and rollback layer for AI agents
(not another vector memory).

Most teams can store facts. Few can show what the agent knew at time T,
roll back a poisoned belief, and export an audit trail for SecOps.

Would you take 20 minutes this week to run one command and tell me if
this is useful for [their company / agent use case]?

  pip install omem-os
  OMEM_EMBEDDER=hash omem demo poison-recovery

One-pager: [link to PARTNER_ONE_PAGER or GitHub docs/yc/PARTNER_ONE_PAGER.md]
Repo: https://github.com/mohitkumarrajbadi/omem

Thanks,
Mohit
```

## LinkedIn (shorter)

```
Building the audit/rollback layer for AI agents (not another Mem0).
Looking for one platform or security eng to spend 20 min on a poison→
rollback→audit demo. Useful for your agent stack at [Company]?
```

## After they reply

1. Send [DEMO.md](./DEMO.md) — they run the command  
2. Ask: “Would you evaluate this as a design partner for audit/tenant?”  
3. If yes → calendar + note in CHECKLIST (even unpaid)  
4. Do **not** pitch SOC2, AST, or benchmarks  

## Tracking (edit locally)

| # | Name | Company | Sent | Reply | Next |
|---|------|---------|------|-------|------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
