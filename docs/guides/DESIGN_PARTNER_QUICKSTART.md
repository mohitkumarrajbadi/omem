# Design-partner quickstart — Governed Agent Memory

**Time:** ~15–20 minutes  
**Status:** tech preview  
**Goal:** Decide whether OMem’s governance primitives are enough to start a
security / platform design-partner evaluation.

## 0. Install

```bash
pip install "omem-os[secure]"
# from a checkout:
# pip install -e ".[secure,dev]"
```

## 1. Encrypted write path

```python
from omem import AgentState
import os

key = os.urandom(32).hex()  # or set OMEM_ENCRYPTION_KEY
agent = AgentState(
    session_id="eval-1",
    namespace="acme/payments/default/alice",
    encryption_key=key,
)
agent.remember("Never store card PANs in agent memory.")
```

With a key present, content/metadata columns are AES-256-GCM ciphertext at rest
(prefix `ENC:v1:`). Vectors stay plaintext so ANN indexing works — see
[TENANT_HARDENING.md](../guarantees/TENANT_HARDENING.md).

## 2. Tenant hardening

```python
from omem.governance import TenantBinding, TenantScope, harden_namespace

binding = TenantBinding(
    scope=TenantScope(org_id="acme", workspace_id="payments"),
    key_id="server-verified-key",
)
# Client-supplied org prefix is ignored
ns = harden_namespace("evil-org/payments", binding)
assert ns.startswith("acme/")
```

## 3. Retention + deletion

```python
from omem.governance import RetentionPolicy

agent.governance.set_policy(
    RetentionPolicy(namespace_pattern="acme/*", max_age_days=90)
)
agent.governance.enforce_retention()
agent.governance.delete_scope("namespace", "acme/payments/default/alice")
```

## 4. Audit export (what you send to SecOps)

```bash
omem governance audit --format json --limit 1000 --out audit.json
# or JSONL:
omem governance audit --format jsonl --limit 1000 --out audit.jsonl
```

SDK:

```python
agent.governance.export_audit(format="json", path="audit.json", limit=1000)
```

## 5. Observability handoff

```python
# Optional: push in-process traces to your collector
agent.observe.push_otel(endpoint="http://localhost:4318/v1/traces")
```

## Evaluation checklist

- [ ] Ciphertext visible in SQLite when encryption key is set
- [ ] Spoofed org prefix rejected by `harden_namespace`
- [ ] Retention policy registers and enforces
- [ ] Audit JSON opens in your SIEM / jq pipeline
- [ ] `delete_scope` removes the memories you expect
- [ ] Claims scoped as **tech preview** (no HA/DR / SOC2 until roadmap ships)

## Next

- Guarantees sheet: [TENANT_HARDENING.md](../guarantees/TENANT_HARDENING.md)
- Full stack demo: `examples/enterprise_agent.py`
- Runnable partner script: `examples/design_partner_governance.py`
