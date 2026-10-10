"""Lean recall pack — short snippets, low token bulk."""

from __future__ import annotations

from types import SimpleNamespace

from omem.memory.lean import (
    approx_tokens,
    build_lean_context,
    lean_memory_dicts,
    snippet,
)


def _mem(content: str, ns: str = "trading"):
    return SimpleNamespace(
        id="abc123def456",
        content=content,
        type=SimpleNamespace(name="DECISION"),
        namespace=ns,
        importance=1.0,
        score=0.9,
        timestamp=0,
    )


def test_snippet_truncates():
    assert snippet("x" * 200, 50).endswith("...")
    assert len(snippet("x" * 200, 50)) == 50


def test_lean_context_budget():
    mems = [_mem("short fact one"), _mem("short fact two"), _mem("x" * 500)]
    ctx = build_lean_context(mems, max_chars=200, snippet_chars=40)
    assert "ns=trading" in ctx
    assert approx_tokens(ctx) <= approx_tokens("x" * 200) + 5
    assert len(ctx) <= 200


def test_lean_dicts_default_not_full():
    mems = [_mem("A" * 300)]
    rows = lean_memory_dicts(mems, query="test", full=False)
    assert len(rows[0]["content"]) < 300
    full_rows = lean_memory_dicts(mems, query="test", full=True)
    assert len(full_rows[0]["content"]) == 300
