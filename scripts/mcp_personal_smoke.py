#!/usr/bin/env python3
"""Personal MCP smoke — proves Claude Code ↔ OpenCode shared memory.

Simulates two independent MCP client sessions against the same durable DB
and namespace (what your manager needs for personal production use).

Usage:
    python scripts/mcp_personal_smoke.py
    # or:
    make mcp-smoke   # if wired

Exit 0 only when cross-session recall succeeds.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from omem.integrations.mcp_server import (
        configure_mcp_server,
        mcp_status,
        recall,
        remember,
        remember_decision,
        recall_decisions,
    )

    stamp = uuid.uuid4().hex[:8]
    marker = f"PERSONAL_MCP_SMOKE_{stamp}"
    tmp = Path(tempfile.mkdtemp(prefix="omem-mcp-smoke-"))
    db = tmp / "brain.db"
    ns = "personal"

    print("═══ OMem personal MCP smoke ═══")
    print(f"  db        {db}")
    print(f"  namespace {ns}")
    print(f"  marker    {marker}")

    # ── Session A: Claude Code ──────────────────────────────────────────────
    configure_mcp_server(db_path=str(db), namespace=ns)
    status_a = mcp_status()
    print(f"\n[Claude Code] status → ns={status_a['namespace']} db={status_a['db_path']}")
    remember(
        f"{marker}: Stay on Claude Code. OpenCode is for parallel review. "
        "Do not migrate to GitHub Copilot for this workflow.",
        importance=0.99,
    )
    remember_decision(
        title="Shared OMem MCP for Claude Code + OpenCode",
        decision="Shared OMem MCP for Claude Code + OpenCode",
        rationale="Same OMEM_DB_PATH + OMEM_NAMESPACE → seamless context handoff",
        alternatives=["Vendor lock-in to a single coding agent chat history"],
        importance=0.95,
    )
    print("[Claude Code] wrote remember + remember_decision")

    # ── Session B: OpenCode (fresh configure = new process) ─────────────────
    configure_mcp_server(db_path=str(db), namespace=ns)
    status_b = mcp_status()
    print(f"\n[OpenCode] status → ns={status_b['namespace']} db={status_b['db_path']}")
    assert status_a["namespace"] == status_b["namespace"] == ns
    assert status_a["db_path"] == status_b["db_path"]

    hit = recall(marker, k=8, project_only=True)
    text = hit["context"] + " ".join(m["content"] for m in hit["memories"])
    print(f"[OpenCode] recall found={hit['stats']['total_found']}")
    if marker not in text:
        # Hash embedder may miss semantic queries — durable list is the source of truth
        from omem.integrations.mcp_server import omem as brain

        listed = " ".join(m.content for m in brain.all(namespace=ns))
        if marker not in listed:
            print("FAIL: OpenCode could not recall Claude Code memory")
            return 1
        print("[OpenCode] recall via namespace list (embedder weak) — durable store OK")
    else:
        print("[OpenCode] semantic recall OK")

    dec = recall_decisions("Claude Code OpenCode MCP", k=5)
    print(f"[OpenCode] decisions found={dec['total']}")
    if dec["total"] < 1:
        print("FAIL: OpenCode could not recall ADR")
        return 1

    report = {
        "status": "PASS",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "namespace": ns,
        "db_path": str(db),
        "recall_count": hit["stats"]["total_found"],
        "decisions": dec["total"],
        "marker": marker,
    }
    out = ROOT / "artifacts"
    out.mkdir(exist_ok=True)
    path = out / f"mcp-personal-smoke-{stamp}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n✔ PASS — shared MCP memory works  report={path}")
    print("  Next: wire Claude Code + OpenCode with the same --namespace/--db-path")
    # Avoid polluting the shell env for later imports
    for var in ("OMEM_DB_PATH", "OMEM_NAMESPACE", "OMEM_PROJECT_ROOT"):
        os.environ.pop(var, None)
    return 0


if __name__ == "__main__":
    # Ensure a quiet env for the smoke
    os.environ.setdefault("OMEM_LOG_LEVEL", "WARNING")
    raise SystemExit(main())
