"""MCP server unit tests — personal multi-client sharing contract."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("OMEM_NAMESPACE", "OMEM_DB_PATH", "OMEM_PROJECT_ROOT", "OMEM_BACKEND"):
        monkeypatch.delenv(var, raising=False)
    yield


def test_namespace_prefers_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OMEM_NAMESPACE", "personal")
    from omem.integrations import mcp_server as ms

    ms.configure_mcp_server(db_path=str(tmp_path / "a.db"), namespace="personal")
    assert ms.get_project_namespace() == "personal"


def test_configure_rebinds_db(tmp_path: Path):
    from omem.integrations import mcp_server as ms

    db = tmp_path / "shared.db"
    ms.configure_mcp_server(db_path=str(db), namespace="mgr-work")
    mid = ms.omem.add("manager prefers Claude Code", namespace="mgr-work", importance=0.95)
    assert mid
    hits = ms.omem.recall("Claude Code", k=5, namespace="mgr-work", project_only=True)
    assert any("Claude Code" in h.content for h in hits)


def test_cross_client_sim_same_db_namespace(tmp_path: Path):
    """Simulate Claude Code write + OpenCode recall on shared SQLite."""
    from omem.integrations import mcp_server as ms

    db = str(tmp_path / "brain.db")
    ns = "personal"
    marker = "CROSS_CLIENT_MARKER_9f3c_claude_opencode"

    # Client A (Claude Code)
    ms.configure_mcp_server(db_path=db, namespace=ns)
    out = ms.remember(
        f"{marker}: Stay on Claude Code; use OpenCode for parallel reviews.",
        importance=0.98,
    )
    assert "personal" in out
    ms._durable_flush()

    # Client B (OpenCode) — new process would re-open same file
    ms.configure_mcp_server(db_path=db, namespace=ns)
    # Exact-token query works even with hash embedder fallback
    recalled = ms.recall(marker, k=8, project_only=True)
    assert recalled["stats"]["project_namespace"] == ns
    # Fallback: list namespace if embedder is weak
    if recalled["stats"]["total_found"] < 1:
        contents = [m.content for m in ms.omem.all(namespace=ns)]
        assert any(marker in c for c in contents), contents
    else:
        blob = recalled["context"] + " ".join(m["content"] for m in recalled["memories"])
        assert marker in blob
        assert "Claude Code" in blob


def test_mcp_status_reports_shared_config(tmp_path: Path):
    from omem.integrations import mcp_server as ms

    db = str(tmp_path / "status.db")
    ms.configure_mcp_server(db_path=db, namespace="personal")
    ms.remember("status probe", importance=0.5)
    status = ms.mcp_status()
    assert status["ok"] is True
    assert status["namespace"] == "personal"
    assert status["db_path"] == db
    assert status["project_memories"] >= 1


def test_coding_tools_use_shared_namespace(tmp_path: Path):
    from omem.integrations import mcp_server as ms

    db = str(tmp_path / "coding.db")
    ms.configure_mcp_server(db_path=db, namespace="acme-api")
    stored = ms.remember_decision(
        title="Use Postgres with pgvector",
        decision="Use Postgres with pgvector",
        rationale="Need RLS + semantic recall without a separate vector SaaS",
        alternatives=["Pinecone", "Weaviate"],
        importance=0.9,
    )
    assert stored["namespace"] == "acme-api"
    found = ms.recall_decisions("pgvector", k=5)
    assert found["namespace"] == "acme-api"
    assert found["total"] >= 1


def test_mcp_package_importable():
    from omem.integrations.mcp_server import _HAS_MCP, mcp, remember, recall

    assert callable(remember)
    assert callable(recall)
    # mcp extra may or may not be installed in CI — both paths valid
    assert mcp is not None
    assert isinstance(_HAS_MCP, bool)
