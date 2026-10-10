"""Focus → personal → widen recall cascade."""

from __future__ import annotations

from pathlib import Path

import pytest

from omem.api import OMem
from omem.memory.cascade import cascade_recall


@pytest.fixture
def brain(tmp_path: Path, monkeypatch):
    for var in ("OMEM_NS", "OMEM_NAMESPACE", "OMEM_PROJECT_ROOT"):
        monkeypatch.delenv(var, raising=False)
    db = tmp_path / "brain.db"
    return OMem(backend="sqlite", db_path=str(db), embedding_provider="local")


def test_focus_excludes_other_project_when_strong(brain):
    brain.add(
        "Trading project rules: NSE BSE arb Zerodha MIS charges only",
        namespace="trading",
        importance=1.0,
    )
    brain.add(
        "PROJECT SUMMARY — neteng-app FastAPI TACACS admin rewrite",
        namespace="neteng-app",
        importance=1.0,
    )

    pack = cascade_recall(
        brain,
        "trading project rules NSE BSE arb Zerodha MIS charges",
        k=5,
        namespace="trading",
        scope_mode="focus",
    )
    memories = pack["memories"]
    assert memories, pack
    namespaces = {m.namespace for m in memories}
    assert "trading" in namespaces
    # Strong focus hit must not dump neteng into default cascade
    assert "neteng-app" not in namespaces
    assert pack["stats"]["widened"] is False


def test_bridge_personal_included(brain):
    brain.add("prefer dark mode in every editor", namespace="personal", importance=0.9)
    brain.add("use MIS for arb examples", namespace="trading", importance=0.9)

    pack = cascade_recall(
        brain,
        "dark mode editor preference",
        k=5,
        namespace="trading",
        scope_mode="focus",
    )
    contents = " ".join(m.content for m in pack["memories"])
    assert "dark mode" in contents


def test_strict_skips_bridge(brain):
    brain.add("prefer dark mode everywhere", namespace="personal", importance=1.0)
    pack = cascade_recall(
        brain,
        "dark mode",
        k=5,
        namespace="trading",
        scope_mode="strict",
    )
    assert pack["memories"] == [] or all(m.namespace == "trading" for m in pack["memories"])


def test_widen_when_focus_empty(brain):
    brain.add(
        "unique-widen-token neteng vault policy binding",
        namespace="neteng-app",
        importance=1.0,
    )
    pack = cascade_recall(
        brain,
        "unique-widen-token vault policy",
        k=5,
        namespace="trading",
        scope_mode="focus",
    )
    assert pack["stats"]["widened"] is True
    assert any(m.namespace == "neteng-app" for m in pack["memories"])


def test_all_mode_searches_labeled(brain):
    brain.add("alpha fact in trading", namespace="trading", importance=0.8)
    brain.add("alpha fact in neteng", namespace="neteng-app", importance=0.8)
    pack = cascade_recall(brain, "alpha fact", k=10, namespace="trading", scope_mode="all")
    ns = {m.namespace for m in pack["memories"]}
    assert "trading" in ns or "neteng-app" in ns
