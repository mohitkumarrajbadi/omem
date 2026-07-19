# Design-partner tech preview

**Status:** tech preview — not GA. Scope claims to what this pack proves.

OMem Cloud's SOC2 Type I evidence collection is **not yet started**, tracked in
[TENANT_HARDENING.md](../guarantees/TENANT_HARDENING.md).

This pack evaluates **Governed Agent Memory**: prove what an agent knew,
when it knew it, and who is allowed to see it — not “store more facts faster.”

## Contents

| Artifact | Purpose |
|----------|---------|
| [PITCH.md](./PITCH.md) | One-pager for investors / sponsors |
| [COFOUNDER_FIRST_HIRE.md](./COFOUNDER_FIRST_HIRE.md) | YC-facing cofounder / first-hire decision framing |
| [DESIGN_PARTNER_QUICKSTART.md](../guides/DESIGN_PARTNER_QUICKSTART.md) | 15–20 minute evaluation path |
| [TENANT_HARDENING.md](../guarantees/TENANT_HARDENING.md) | Explicit guarantees / non-guarantees |
| [design_partner_governance.py](../../examples/design_partner_governance.py) | Runnable governance demo |
| CLI `omem governance audit --format json` | Audit export for security review |
| [public_benchmark_results.json](../../distribution/public_benchmark_results.json) | July 2026 retrieval scorecard |

## Framing for reviewers

- Product posture: **design-partner tech preview**
- Local OSS: audit + retention + field encryption + `harden_namespace` helpers
- Cloud RLS / gateway RBAC enforcement: **omem-cloud** (separate package)
- Local RBAC roles are **informative** until cloud gateway enforcement

## One command

```bash
pip install "omem-os[secure]"
python examples/design_partner_governance.py
omem governance audit --format json --limit 100 --out /tmp/omem-audit.json
```
