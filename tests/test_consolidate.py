"""Tests for the consolidate() deadlock fix in BrainTrace.base."""

import threading

import pytest

from omem.core.engine.base import BrainTrace


@pytest.fixture
def engine():
    e = BrainTrace()
    e.add("Python is my favourite language", source="test")
    e.add("I prefer dark mode in my editor", source="test")
    e.add("I work at a fintech startup", source="test")
    return e


# ── Test 1: Basic return shape ────────────────────────────────────────────────
def test_consolidate_returns_dict(engine):
    result = engine.consolidate()
    assert isinstance(result, dict)
    assert "conflicts_resolved" in result
    assert "new_insights" in result


# ── Test 2: Counts are non-negative integers ──────────────────────────────────
def test_consolidate_counts_non_negative(engine):
    result = engine.consolidate()
    assert result["conflicts_resolved"] >= 0
    assert result["new_insights"] >= 0


# ── Test 3: No deadlock — must complete within 5 seconds ─────────────────────
def test_consolidate_no_deadlock(engine):
    result = {}
    exc_box = []

    def run():
        try:
            result["out"] = engine.consolidate()
        except Exception as e:
            exc_box.append(e)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=5)

    assert not t.is_alive(), "consolidate() deadlocked — thread still running after 5s"
    assert not exc_box, f"consolidate() raised: {exc_box[0]}"


# ── Test 4: Concurrent add() while consolidate() runs ────────────────────────
def test_consolidate_concurrent_with_add():
    engine = BrainTrace()
    for i in range(5):
        engine.add(f"fact number {i}", source="seed")

    errors = []
    results = {}

    def do_consolidate():
        try:
            results["consolidate"] = engine.consolidate()
        except Exception as e:
            errors.append(("consolidate", e))

    def do_add():
        try:
            results["add"] = engine.add("concurrent memory", source="thread")
        except Exception as e:
            errors.append(("add", e))

    def do_recall():
        try:
            results["recall"] = engine.rag("fact")
        except Exception as e:
            errors.append(("recall", e))

    threads = [
        threading.Thread(target=do_consolidate, daemon=True),
        threading.Thread(target=do_add, daemon=True),
        threading.Thread(target=do_recall, daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    hung = [t for t in threads if t.is_alive()]
    assert not hung, f"{len(hung)} thread(s) still hung after 10s"
    assert not errors, f"Errors in threads: {errors}"


# ── Test 5: Empty engine — no crash ──────────────────────────────────────────
def test_consolidate_empty_engine():
    engine = BrainTrace()
    result = engine.consolidate()
    assert result["conflicts_resolved"] == 0
    assert result["new_insights"] == 0


# ── Test 6: Vector index still usable after consolidate ──────────────────────
def test_consolidate_vector_index_intact(engine):
    engine.consolidate()
    results = engine.rag("Python language", top_k=3)
    assert isinstance(results, list)
    assert len(results) >= 1


# ── Test 7: Memories still present after consolidate ─────────────────────────
def test_consolidate_preserves_memories(engine):
    before = len(list(engine.kv.all()))
    engine.consolidate()
    after = len(list(engine.kv.all()))
    # consolidate may ADD insights, never removes active memories
    assert after >= before


# ── Test 8: consolidate() can be called multiple times safely ────────────────
def test_consolidate_idempotent(engine):
    r1 = engine.consolidate()
    r2 = engine.consolidate()
    assert isinstance(r1, dict)
    assert isinstance(r2, dict)
