"""Tests for the rag()/reload_from_backend() deadlock fix in BrainTrace.rag.

Bug: rag() acquired the RWLock's read lock (ReadContext) and, while still
holding it, called self.reload_from_backend() when the in-memory KV was
empty. reload_from_backend() itself acquires the *write* lock
(WriteContext). RWLock is not reentrant, so a thread holding the read
lock blocks forever waiting to acquire the write lock — a guaranteed
self-deadlock on any cold-start / post-restart recall against a
persistent backend.

Fix: check kv.size and call reload_from_backend() *before* entering the
read-lock context, so the write lock it needs internally is never
requested while a read lock is held by the same thread.
"""

import threading

import pytest

from omem.backends.sqlite import SQLiteBackend
from omem.core.engine.base import BrainTrace
from omem.core.utils.write_buffer import WriteBuffer


@pytest.fixture
def backend(tmp_path):
    return SQLiteBackend(str(tmp_path / "test.db"))


def _new_engine(backend, tmp_path, suffix=""):
    """Build a BrainTrace with its own isolated WAL file.

    BrainTrace's default WriteBuffer path is a single shared file under
    ~/.omem/, so engines built in the same test run/process can observe
    each other's un-flushed WAL entries. Point each engine at a private
    WAL under tmp_path so tests stay hermetic.
    """
    engine = BrainTrace(backend=backend)
    engine.write_buffer.stop()
    engine.write_buffer = WriteBuffer(
        backend=backend, wal_path=str(tmp_path / f"write_buffer{suffix}.wal")
    )
    engine.write_buffer.start()
    return engine


def _seed_backend_only(backend, tmp_path):
    """Persist memories directly to the backend without going through an
    engine's in-memory KV, simulating a fresh/pooled engine that hasn't
    warmed its cache yet (kv.size == 0) but whose backend already has data
    — e.g. right after an API process restart.
    """
    seeder = _new_engine(backend, tmp_path, suffix="-seed")
    seeder.add("Python is my favourite language", source="test")
    seeder.add("I prefer dark mode in my editor", source="test")
    seeder.add("I work at a fintech startup", source="test")
    seeder.write_buffer.flush()


# ── Test 1: cold engine reload — must complete, not hang ─────────────────────
def test_rag_cold_start_reload_no_deadlock(backend, tmp_path):
    _seed_backend_only(backend, tmp_path)

    # Fresh engine bound to the same backend, but constructed so its KV
    # starts empty (mirrors a pooled engine warmed before writes landed).
    engine = _new_engine(backend, tmp_path)
    engine.kv.clear()
    engine._id_order.clear()
    assert engine.kv.size == 0

    result = {}
    exc_box = []

    def run():
        try:
            result["out"] = engine.rag("Python", top_k=3)
        except Exception as e:
            exc_box.append(e)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=5)

    assert not t.is_alive(), "rag() deadlocked on cold-start reload — thread still running after 5s"
    assert not exc_box, f"rag() raised: {exc_box[0]}"
    assert isinstance(result.get("out"), list)


# ── Test 2: reload actually repopulates the KV / vector index ────────────────
def test_rag_cold_start_reload_repopulates(backend, tmp_path):
    _seed_backend_only(backend, tmp_path)

    engine = _new_engine(backend, tmp_path)
    engine.kv.clear()
    engine._id_order.clear()

    results = engine.rag("fintech startup", top_k=3)

    assert engine.kv.size == 3
    assert any("fintech" in m.content for m in results)


# ── Test 3: concurrent cold-start rag() calls don't deadlock each other ──────
def test_rag_concurrent_cold_start_no_deadlock(backend, tmp_path):
    _seed_backend_only(backend, tmp_path)

    engine = _new_engine(backend, tmp_path)
    engine.kv.clear()
    engine._id_order.clear()

    errors = []

    def do_rag():
        try:
            engine.rag("Python", top_k=3)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=do_rag, daemon=True) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    hung = [t for t in threads if t.is_alive()]
    assert not hung, f"{len(hung)} thread(s) still hung after 10s"
    assert not errors, f"Errors in threads: {errors}"


# ── Test 4: warm engine (kv already populated) is unaffected by the fix ─────
def test_rag_warm_engine_still_works(tmp_path):
    engine = _new_engine(backend=None, tmp_path=tmp_path)
    engine.add("Python is my favourite language", source="test")
    assert engine.kv.size > 0

    results = engine.rag("Python", top_k=3)
    assert isinstance(results, list)
    assert len(results) >= 1
