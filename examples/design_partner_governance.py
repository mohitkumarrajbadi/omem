#!/usr/bin/env python3
"""Design-partner tech preview — Governed Agent Memory path.

Focuses on the evaluation criteria security / compliance partners care about:
  1. Field encryption at rest (AES-256-GCM)
  2. Tenant namespace hardening (ignore spoofed org headers)
  3. Retention policy + enforcement
  4. Audit trail query + JSON export
  5. Scoped deletion

Run:
    pip install "omem-os[secure]"
    python examples/design_partner_governance.py
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from omem import AgentState
from omem.governance import (
    RetentionPolicy,
    TenantBinding,
    TenantScope,
    harden_namespace,
)


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def main() -> None:
    print("OMem Design-Partner Tech Preview — Governed Agent Memory")
    print("=" * 60)

    key = os.urandom(32).hex()
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "partner.db")
        audit_db = str(Path(tmp) / "partner_audit.db")
        os.environ["OMEM_AUDIT_DB_PATH"] = audit_db

        section("1. Encrypted agent (AES-256-GCM at rest)")
        agent = AgentState(
            session_id="partner-eval",
            namespace="acme/payments/agent/alice",
            backend="sqlite",
            db_path=db,
            encryption_key=key,
        )
        mid = agent.remember(
            "Decision ADR-42: never store PAN in agent memory. Approved by security.",
            importance=0.95,
        )
        agent._omem.brain.write_buffer.flush()
        print(f"  stored memory_id={mid}")
        print(f"  encrypted={agent._omem.brain.backend._enc is not None}")

        section("2. Tenant hardening (spoofed org prefix refused)")
        binding = TenantBinding(
            scope=TenantScope(org_id="acme", workspace_id="payments", agent_id="agent", user_id="alice"),
            role="writer",
            key_id="key_demo",
        )
        spoofed = harden_namespace("evil-org/payments/agent/alice", binding)
        print(f"  client sent: evil-org/payments/agent/alice")
        print(f"  hardened to: {spoofed}")
        assert spoofed.startswith("acme/"), "harden_namespace must ignore client org"

        section("3. Retention policy")
        agent.governance.set_policy(
            RetentionPolicy(namespace_pattern="acme/*", max_age_days=90, max_count=10_000)
        )
        print(f"  policies={len(agent.governance.list_policies())}")

        section("4. Audit trail + JSON export")
        agent.governance.flush_audit()
        # Touch another op so the trail is non-empty for demo
        agent.recall("PAN policy", k=3)
        agent.governance.flush_audit()
        entries = agent.governance.audit(limit=20)
        print(f"  audit entries={len(entries)}")
        export_path = str(Path(tmp) / "audit_export.json")
        agent.governance.export_audit(format="json", path=export_path, limit=100)
        payload = json.loads(Path(export_path).read_text())
        print(f"  export count={payload['count']} → {export_path}")

        section("5. Scoped deletion")
        report = agent.governance.delete_scope("memory_id", mid, cascade=True)
        print(f"  deleted_memories={report.deleted_memories} errors={report.errors}")

        print("\n✓ Design-partner governance path exercised.")
        print("  Docs: docs/design-partner/README.md")
        print("  Guarantees: docs/guarantees/TENANT_HARDENING.md")


if __name__ == "__main__":
    main()
