"""Namespace clear must delete from SQLite so a new process stays empty."""

from __future__ import annotations

from pathlib import Path

from omem.api import OMem


def test_clear_namespace_survives_reload(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OMEM_DISABLE_WRITE_BUFFER_WAL", "1")
    db = str(tmp_path / "brain.db")

    a = OMem(backend="sqlite", db_path=db, embedding_provider="local")
    a.add("keep me", namespace="keep", importance=0.9)
    a.add("drop me", namespace="drop", importance=0.9)
    a.brain.write_buffer.flush()
    a.clear(namespace="drop")
    assert a.namespace_stats("drop")["total"] == 0
    assert a.namespace_stats("keep")["total"] == 1

    # Simulate next CLI invocation
    b = OMem(backend="sqlite", db_path=db, embedding_provider="local")
    assert b.namespace_stats("drop")["total"] == 0
    assert "drop" not in b.namespaces() or b.namespace_stats("drop")["total"] == 0
    assert b.namespace_stats("keep")["total"] == 1
