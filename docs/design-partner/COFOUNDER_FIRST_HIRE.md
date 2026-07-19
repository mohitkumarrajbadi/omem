# Cofounder / first-hire decision framing

> **STATUS: §4 not yet completed — must be filled in before any YC application
> or design-partner interview that raises the cofounder / bus-factor question.**

**Purpose:** Answer the question YC (and every enterprise design partner) will
ask: *who else is on this, and what breaks if you’re hit by a bus?*  
**Date:** July 2026 · **Status:** decision memo — fill in blanks before apply

This is a framing doc, not a job post. Leave options open; pick one before the
interview, not in the interview.

---

## 1. Why this question matters for OMem specifically

OMem’s wedge is **Governed Agent Memory** — trust, audit, tenant isolation,
encryption. Buyers are security / platform teams. They underwrite *people* as
much as code:

- Solo infra founders are fundable at YC, but **undifferentiated** risk vs Mem0
  ($24.5M, team) and Zep / Letta.
- Your Akamai production metrics and Mark Van Horn signal are the founder
  advantage. A gap remains on: GTM for compliance buyers, SOC2 process, and
  “second brain” on the codebase.

**Bar for a good answer:** concrete name *or* concrete first-hire profile with
timeline and what you stop doing once they’re in.

---

## 2. Decision tree (pick one primary path)

### Option A — Technical cofounder (equity)

**Hire for:** distributed systems / security engineering (Postgres RLS, KMS,
OTLP at scale, SOC2 evidence automation) **or** GTM-technical hybrid who has
sold to infosec.

| Pros | Cons |
|------|------|
| Derisks YC “solo founder” objection | Equity + chemistry take time |
| Shared narrative ownership | Wrong pick is expensive |

**Look for:** someone who has shipped multi-tenant infra or compliance tooling;
not “another RAG engineer.”

**Signal you’re ready:** you can name 2–3 people you’d ask this week, and what
% equity band you’d open with.

### Option B — First hire, not cofounder (cash or mix)

**Hire for (ranked for this wedge):**

1. **Founding security / platform engineer** — turns tech preview → design-
   partner trust (encryption E2E, audit export → SIEM, HA/DR design).
2. **Founding solutions / design-partner engineer** — runs POCs with SecOps;
   writes the guarantee docs with customers.
3. **Part-time compliance advisor** — SOC2 Type I path; cheaper early signal.

| Pros | Cons |
|------|------|
| Faster than cofounder search | YC still hears “solo” unless you over-index on hiring plan |
| Clearer employer control | Cash burn |

**Signal you’re ready:** JD + budget + interview loop written before application.

### Option C — Stay solo through design-partner traction

**Only choose this if:** you land ≥1 external design partner *before* YC, and
you present a dated first-hire plan (week 1 after batch / after seed).

| Pros | Cons |
|------|------|
| Keeps story clean if partners are inbound | Weakest answer if asked “why no one else” |

---

## 3. Role that best matches the wedge (recommended default)

If forced to pick one profile for the next 90 days:

> **Founding Design-Partner Engineer (security-shaped)**  
> Owns: design-partner POCs, audit/OTLP/encryption demos, guarantee sheet
> updates, first SOC2 evidence stubs.  
> Does *not* own: generic “grow GitHub stars” or “build another SDK.”

Why: your unique risk is not “can we recall facts” — it’s “can we survive an
enterprise security questionnaire without hand-waving.”

---

## 4. Fill-in before YC / sponsor conversation

Copy this block and complete it honestly:

```
Primary path:          A / B / C  (circle one)
If A — candidates I'll contact this week:
  1.
  2.
If B — first hire title + start window:
  Title:
  Start by (date):
  Comp shape (cash / equity / mix):
If C — design partner target + first-hire trigger:
  Partner:
  Hire triggered when:
What I personally stop doing after that hire:
  -
Bus-factor doc lives at:  (link to runbooks / architecture)
```

---

## 5. Answer scripts (keep short)

**Best:**  
“I’m raising / applying as the domain founder with production proof at Akamai.
Governance is the product. My first hire is a security-shaped design-partner
engineer within 30 days of partner signature / batch start — JD already written.
I’m also in conversations with [N] people for a possible technical cofounder,
but I won’t force chemistry for the application.”

**Avoid:**  
“I’ll find someone during the batch.” / “AI will help me stay solo forever.” /
Naming a cofounder who hasn’t agreed.

---

## 6. Tie-back to the 90-day plan

| Weeks | Link to this doc |
|-------|------------------|
| 1–3 | Encryption e2e + in-process OTLP JSON export shipped — less need for hire #1 on those |
| 3–8 | Design partner → triggers Option B hire conversation |
| 6–12 | **Decide A/B/C explicitly** (this file) |
| YC interview | Bring filled §4 + design-partner pack |

---

*Related: [PITCH.md](./PITCH.md) · [TENANT_HARDENING.md](../guarantees/TENANT_HARDENING.md) · strategy memo July 2026*
