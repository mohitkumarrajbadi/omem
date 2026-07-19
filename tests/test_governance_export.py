"""Tests for GovernanceOS.export_audit (design-partner pack)."""

from __future__ import annotations

import json
from pathlib import Path

from omem import AgentState


def test_export_audit_json_and_jsonl(tmp_path):
    agent = AgentState(
        session_id="gov-export",
        namespace="acme/test",
        backend="sqlite",
        db_path=str(tmp_path / "brain.db"),
    )
    agent.remember("exportable decision")
    agent.governance.flush_audit()

    json_path = str(tmp_path / "audit.json")
    out = agent.governance.export_audit(format="json", path=json_path, limit=50)
    assert out == json_path
    payload = json.loads(Path(json_path).read_text())
    assert "entries" in payload
    assert payload["count"] == len(payload["entries"])

    body = agent.governance.export_audit(format="jsonl", limit=50)
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert lines
    assert all(json.loads(ln) for ln in lines)


def test_export_audit_rejects_bad_format(tmp_path):
    agent = AgentState(backend="memory", db_path=str(tmp_path / "x.db"))
    try:
        agent.governance.export_audit(format="csv")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "json" in str(exc)
