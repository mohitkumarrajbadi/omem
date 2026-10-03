# 5-minute demo (founder video + partner)

**Goal:** show governance, not recall quality.  
**Time:** ≤5 minutes live · ≤90 seconds for YC video (same beats, cut talk).

## Setup (30s)

```bash
cd omem-oss
pip install -e ".[dev]"
export OMEM_EMBEDDER=hash
omem demo poison-recovery
```

Optional JSON for screen:

```bash
omem demo poison-recovery --json | head -c 2000
```

## Script (say this)

1. **Setup (10s)**  
   “Treasury agent remembers a verified wire beneficiary. We snapshot state.”

2. **Incident (15s)**  
   “Untrusted scrape injects an OVERRIDE — memory is poisoned. Agent would route money wrong.”

3. **Provenance (20s)**  
   “We don’t guess. We show source, actor, trust, memory id.”

4. **Remediation (40s)**  
   “Rollback restores the session checkpoint. Soft-delete removes the poison from recall. Both matter — rollback alone does not erase the row.”

5. **Audit (20s)**  
   “Every step is in the governance ledger — exportable for SecOps.”

6. **Close (15s)**  
   “That’s OMem: prove what the agent knew, roll it back, leave a trail. Cloud adds tenant RLS and key rotation for enterprises. We’re in design-partner preview.”

## YC video cut (60–75s)

- 0–5s: name + “OMem Labs”  
- 5–50s: run demo on screen, narrate beats 1–5  
- 50–70s: “looking for design partners + YC Winter 2027”  
- No architecture slides. No benchmark tables.

## Partner handoff

```bash
# After install, they run once:
omem demo poison-recovery
omem governance audit --format json --limit 20
```

If they have Mem0: `pip install "omem-os[mem0]"` → `GovernedMem0` wrap (see package docs). Do not lead with Mem0 unless they ask.

## Do not demo

- AST / codebase index  
- Console Alpha tabs  
- LongMemEval scoreboards  
- “We’re GA / SOC2 done”
