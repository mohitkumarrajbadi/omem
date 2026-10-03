"""Concurrent same-namespace write contention + non-demo fork/merge.

Correctness-focused (not throughput benches): concurrent writers into one shared
in-memory store must all persist; a second fork/merge scenario must work without
the Akamai demo MERGE DECISION inject path.
"""

from __future__ import annotations

import os
import threading
import uuid

import pytest

# Keep WAL/audit off shared home paths in sandbox/CI.
os.environ.setdefault("OMEM_DISABLE_WRITE_BUFFER_WAL", "1")
os.environ.setdefault("OMEM_AUDIT_DB_PATH", ":memory:")

from omem import OMem
from omem.state import InMemoryStateBackend, StateOS, StatePayload


@pytest.fixture
def shared_ns() -> str:
    return f"contention-{uuid.uuid4().hex[:12]}"


def test_concurrent_same_namespace_writes_are_durable(shared_ns: str):
    store = OMem(backend="memory")
    n_writers = 4
    writes_each = 12
    barrier = threading.Barrier(n_writers)
    errors: list[str] = []
    lock = threading.Lock()

    def writer(wid: int) -> None:
        try:
            barrier.wait(timeout=5)
            for i in range(writes_each):
                # Shared store — Brain WriteContext serializes mutating ops.
                mid = store.add(
                    f"WRITER-{wid}-ITEM-{i} shared-ns={shared_ns}",
                    namespace=shared_ns,
                    importance=0.8,
                    force=True,
                )
                if not mid:
                    raise RuntimeError(f"add returned empty id for writer {wid} item {i}")
        except Exception as exc:  # noqa: BLE001 — collect for assertion
            with lock:
                errors.append(f"writer-{wid}: {exc}")

    threads = [
        threading.Thread(target=writer, args=(i,), daemon=True)
        for i in range(n_writers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive(), "writer thread hung"

    assert errors == [], f"concurrent write errors: {errors}"

    all_mems = store.brain.all_memories(namespace=shared_ns)
    contents = [getattr(m, "content", "") or "" for m in all_mems]
    assert len(contents) >= n_writers * writes_each
    for wid in range(n_writers):
        for i in range(writes_each):
            marker = f"WRITER-{wid}-ITEM-{i}"
            assert any(marker in c for c in contents), f"missing durable write {marker}"


def test_fork_merge_pricing_experiment_not_plan_ab():
    """Second fork/merge scenario (pricing A/B) — independent of demo Plan A/B."""
    state = StateOS(backend=InMemoryStateBackend())
    state.save(
        "pricing-root",
        StatePayload(session_id="pricing-root", goal="Pick pricing experiment"),
    )
    state.set_plan("pricing-root", ["baseline", "ship variant"])
    snap = state.snapshot("pricing-root", label="pre-fork")

    a = state.fork(snap.id, new_session_id="pricing-a")
    b = state.fork(snap.id, new_session_id="pricing-b")
    state.set_goal(a, "Variant A: annual discount 20%")
    state.set_goal(b, "Variant B: monthly free tier")

    merged = state.merge(a, "pricing-root")
    assert "annual discount 20%" in merged.goal
    assert state.session_exists(b)
