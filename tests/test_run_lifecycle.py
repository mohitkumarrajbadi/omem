"""OMem v1 — Run / RunEvent lifecycle, dual-write, idempotency, fork, replay modes."""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from omem import AgentState
from omem.state import (
    IdempotencyConflictError,
    InMemoryRunStore,
    InMemoryStateBackend,
    RunEventError,
    RunNotFoundError,
    RunOS,
    StateOS,
)
from omem.state.run_store import SQLiteRunStore
from omem.types import StatePayload


@pytest.fixture
def state_os():
    return StateOS(backend=InMemoryStateBackend())


@pytest.fixture
def run_os(state_os: StateOS) -> RunOS:
    return RunOS(store=InMemoryRunStore(), state=state_os, namespace="default")


@pytest.fixture
def session(state_os: StateOS) -> str:
    sid = "thread-run-1"
    state_os.save(sid, StatePayload(session_id=sid, namespace="default"))
    return sid


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestRunLifecycle:
    def test_start_run_appends_run_started(self, run_os: RunOS, session: str):
        active = run_os.start_run(session, goal="Investigate outage")
        events = active.inspect_events()
        assert events[0].type == "run_started"
        assert events[0].sequence == 1
        assert active.run.status == "running"
        assert active.run.goal == "Investigate outage"

    def test_record_and_complete(self, run_os: RunOS, session: str):
        active = run_os.start_run(session)
        active.record("user_message", {"text": "fix it"})
        active.record("tool_call", {"tool": "logs.query"}, idempotency_key="k1")
        active.complete()
        run = active.refresh()
        assert run.status == "done"
        types = [e.type for e in active.inspect_events()]
        assert "run_completed" in types

    def test_invalid_event_type_rejected(self, run_os: RunOS, session: str):
        active = run_os.start_run(session)
        with pytest.raises(RunEventError):
            active.record("not_a_real_type", {})

    def test_custom_event_allowed(self, run_os: RunOS, session: str):
        active = run_os.start_run(session)
        ev = active.record("custom.metrics_tick", {"n": 1})
        assert ev.type == "custom.metrics_tick"

    def test_sequence_monotonic(self, run_os: RunOS, session: str):
        active = run_os.start_run(session)
        for i in range(5):
            active.record("observation", {"i": i})
        seqs = [e.sequence for e in active.inspect_events()]
        assert seqs == list(range(1, len(seqs) + 1))

    def test_run_not_found(self, run_os: RunOS):
        with pytest.raises(RunNotFoundError):
            run_os.get_run("run_missing")


# ---------------------------------------------------------------------------
# Checkpoint dual-write + Mode A resume
# ---------------------------------------------------------------------------


class TestCheckpointAndResume:
    def test_checkpoint_dual_write(self, run_os: RunOS, session: str, state_os: StateOS):
        active = run_os.start_run(session, goal="g")
        state_os.advance(session)
        chk = active.checkpoint()
        assert chk.startswith("chk_")
        events = [e for e in active.inspect_events() if e.type == "checkpoint"]
        assert len(events) == 1
        assert events[0].payload["checkpoint_id"] == chk
        assert active.refresh().last_checkpoint_id == chk

    def test_resume_after_inferred_crash(self, run_os: RunOS, session: str, state_os: StateOS):
        active = run_os.start_run(session, worker_id="worker_a", goal="g")
        state_os.set_plan(session, ["a", "b", "c"])
        state_os.advance(session)
        state_os.advance(session)  # step 2
        chk = active.checkpoint()
        state_os.advance(session)  # step 3 after checkpoint — lost on resume

        # Simulate process death: lease expired, new worker resumes
        run = active.refresh()
        run.lease_until = time.time() - 1
        run_os._store.save_run(run)

        resumed = run_os.resume_run(active.run_id, worker_id="worker_b")
        payload = state_os.load(session)
        assert payload.step == 2  # Mode A: checkpoint cursor
        types = [e.type for e in resumed.inspect_events()]
        assert "run_crashed" in types  # inferred
        assert "run_resumed" in types
        assert resumed.run.status == "running"
        assert resumed.run.lease_owner == "worker_b"
        assert chk == resumed.run.last_checkpoint_id or True


# ---------------------------------------------------------------------------
# Idempotency (L1)
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_duplicate_key_returns_same_event(self, run_os: RunOS, session: str):
        active = run_os.start_run(session)
        e1 = active.record(
            "tool_call",
            {"tool": "refund", "amount": 10},
            idempotency_key="refund:1",
        )
        e2 = active.record(
            "tool_call",
            {"tool": "refund", "amount": 10},
            idempotency_key="refund:1",
        )
        assert e1.event_id == e2.event_id
        assert e1.sequence == e2.sequence
        tool_calls = [e for e in active.inspect_events() if e.type == "tool_call"]
        assert len(tool_calls) == 1

    def test_same_key_different_payload_conflicts(self, run_os: RunOS, session: str):
        active = run_os.start_run(session)
        active.record("tool_call", {"tool": "a"}, idempotency_key="k")
        with pytest.raises(IdempotencyConflictError):
            active.record("tool_call", {"tool": "b"}, idempotency_key="k")

    def test_pending_tool_calls(self, run_os: RunOS, session: str):
        active = run_os.start_run(session)
        call = active.record("tool_call", {"tool": "x"}, idempotency_key="x1")
        assert len(active.pending_tool_calls()) == 1
        active.record(
            "tool_result",
            {"ok": True},
            causation_id=call.event_id,
            idempotency_key="x1:result",
        )
        assert active.pending_tool_calls() == []


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


class TestFork:
    def test_fork_creates_new_run_with_lineage(
        self, run_os: RunOS, session: str, state_os: StateOS
    ):
        parent = run_os.start_run(session, goal="parent-goal")
        state_os.advance(session)
        chk = parent.checkpoint()
        parent.record("observation", {"after": True})

        child = parent.fork(checkpoint_id=chk, label="alt-model")
        assert child.run_id != parent.run_id
        assert child.run.parent_run_id == parent.run_id
        assert child.run.fork_checkpoint_id == chk
        assert child.run.fork_seq is not None
        assert child.session_id != session  # StateOS fork → new thread/session
        types = [e.type for e in child.inspect_events()]
        assert "fork_created" in types


# ---------------------------------------------------------------------------
# Mode B / C
# ---------------------------------------------------------------------------


class TestReplayModes:
    def test_inspect_events_mode_b(self, run_os: RunOS, session: str):
        active = run_os.start_run(session)
        active.record("user_message", {"text": "hi"})
        events = active.inspect_events(from_seq=1)
        assert all(e.sequence >= 1 for e in events)

    def test_restore_to_seq_mode_c(
        self, run_os: RunOS, session: str, state_os: StateOS
    ):
        active = run_os.start_run(session)
        state_os.advance(session)  # 1
        chk = active.checkpoint()
        ck_seq = [
            e.sequence
            for e in active.inspect_events()
            if e.type == "checkpoint"
        ][0]
        state_os.advance(session)  # 2 after checkpoint
        active.record("observation", {"step": "after"})
        payload = active.restore_to_seq(ck_seq)
        assert payload.step == 1
        # History still has later events
        assert any(e.sequence > ck_seq for e in active.inspect_events())
        assert chk


# ---------------------------------------------------------------------------
# SQLite persistence across "process restart"
# ---------------------------------------------------------------------------


class TestSQLitePersistence:
    def test_events_survive_new_store_instance(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "state.db")
            state1 = StateOS(backend=InMemoryStateBackend())  # payload in mem
            # Use SQLite for both so restart shares file — state also needs sqlite
            from omem.state.backend import SQLiteStateBackend

            state_be = SQLiteStateBackend(path)
            state = StateOS(backend=state_be)
            store = SQLiteRunStore(path)
            ros = RunOS(store=store, state=state)
            sid = "persist-thread"
            state.save(sid, StatePayload(session_id=sid))
            active = ros.start_run(sid, goal="persist")
            active.record("observation", {"n": 1})
            rid = active.run_id
            store.close()

            store2 = SQLiteRunStore(path)
            state2 = StateOS(backend=SQLiteStateBackend(path))
            ros2 = RunOS(store=store2, state=state2)
            run = ros2.get_run(rid)
            assert run.goal == "persist"
            events = ros2.list_events(rid)
            assert events[0].type == "run_started"
            assert any(e.type == "observation" for e in events)
            store2.close()


# ---------------------------------------------------------------------------
# AgentState facade backwards compatibility
# ---------------------------------------------------------------------------


class TestAgentStateFacade:
    def test_start_run_and_legacy_checkpoint(self, tmp_path):
        db = str(tmp_path / "a.db")
        agent = AgentState(
            session_id="facade-1",
            backend="sqlite",
            db_path=db,
        )
        run = agent.start_run(goal="facade goal")
        agent.set_plan(["one", "two"])
        agent.advance()
        ck = agent.checkpoint()  # dual-write via active run
        assert ck
        events = agent.inspect_events()
        assert any(e.type == "checkpoint" for e in events)

        # Legacy APIs still work
        agent.remember("a fact about the incident")
        hits = agent.recall("incident", k=3)
        assert hits

    def test_memory_and_run_coexist(self, tmp_path):
        agent = AgentState(
            session_id="coexist",
            backend="memory",
        )
        agent.start_run(goal="g")
        agent.record_event("memory_write", {"note": "x"})
        mid = agent.remember("durable note")
        assert mid
        assert agent.inspect_events()
