"""Tests for StateOS core CRUD and snapshot/rollback operations.

All tests use InMemoryStateBackend — zero I/O, fully deterministic.
"""

import time

import pytest

from omem.state import (
    InMemoryStateBackend,
    StateOS,
    StatePayload,
    ToolResult,
)
from omem.state.exceptions import (
    SessionNotFoundError,
    SnapshotNotFoundError,
)


@pytest.fixture
def state():
    """Fresh, isolated StateOS backed by in-memory storage."""
    return StateOS(backend=InMemoryStateBackend())


@pytest.fixture
def session(state: StateOS) -> str:
    """A session created in the state engine, returns session_id."""
    sid = "test-session-1"
    state.save(sid, StatePayload(session_id=sid))
    return sid


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


class TestSessionCRUD:
    def test_save_and_load(self, state: StateOS):
        payload = StatePayload(session_id="s1", goal="Do something")
        state.save("s1", payload)
        loaded = state.load("s1")
        assert loaded.session_id == "s1"
        assert loaded.goal == "Do something"

    def test_load_nonexistent_raises(self, state: StateOS):
        with pytest.raises(SessionNotFoundError) as exc_info:
            state.load("ghost-session")
        assert "ghost-session" in str(exc_info.value)

    def test_get_or_create_creates_new(self, state: StateOS):
        payload = state.get_or_create("fresh-session")
        assert payload.session_id == "fresh-session"
        assert payload.status == "idle"

    def test_get_or_create_returns_existing(self, state: StateOS, session: str):
        state.set_goal(session, "Existing goal")
        payload = state.get_or_create(session)
        assert payload.goal == "Existing goal"

    def test_session_exists_true(self, state: StateOS, session: str):
        assert state.session_exists(session) is True

    def test_session_exists_false(self, state: StateOS):
        assert state.session_exists("no-such-session") is False

    def test_list_sessions(self, state: StateOS):
        state.save("a", StatePayload(session_id="a", namespace="ns1"))
        state.save("b", StatePayload(session_id="b", namespace="ns2"))
        all_sessions = state.list_sessions()
        assert "a" in all_sessions
        assert "b" in all_sessions

    def test_list_sessions_by_namespace(self, state: StateOS):
        state.save("a", StatePayload(session_id="a", namespace="ns1"))
        state.save("b", StatePayload(session_id="b", namespace="ns2"))
        ns1 = state.list_sessions(namespace="ns1")
        assert "a" in ns1
        assert "b" not in ns1

    def test_update_increments_version(self, state: StateOS, session: str):
        p1 = state.load(session)
        state.update(session, status="running")
        p2 = state.load(session)
        assert p2.version == p1.version + 1

    def test_update_rejects_unknown_fields(self, state: StateOS, session: str):
        with pytest.raises(ValueError, match="unknown fields"):
            state.update(session, nonexistent_field="boom")

    def test_update_nonexistent_session_raises(self, state: StateOS):
        with pytest.raises(SessionNotFoundError):
            state.update("ghost", status="running")

    def test_save_force_syncs_session_id(self, state: StateOS):
        """session_id in the payload is authoritative; argument must match."""
        payload = StatePayload(session_id="different-id")
        state.save("authoritative-id", payload)
        loaded = state.load("authoritative-id")
        assert loaded.session_id == "authoritative-id"


# ---------------------------------------------------------------------------
# Semantic helpers
# ---------------------------------------------------------------------------


class TestSemanticHelpers:
    def test_set_goal(self, state: StateOS, session: str):
        state.set_goal(session, "Fix the authentication bug")
        p = state.load(session)
        assert p.goal == "Fix the authentication bug"
        assert p.status == "running"

    def test_set_plan(self, state: StateOS, session: str):
        state.set_plan(session, ["Step A", "Step B", "Step C"])
        p = state.load(session)
        assert p.plan == ["Step A", "Step B", "Step C"]
        assert p.step == 0

    def test_advance_increments_step(self, state: StateOS, session: str):
        state.set_plan(session, ["A", "B", "C"])
        state.advance(session)
        assert state.load(session).step == 1

    def test_advance_to_done(self, state: StateOS, session: str):
        state.set_plan(session, ["A"])
        state.advance(session)
        p = state.load(session)
        assert p.status == "done"

    def test_record_tool_appends(self, state: StateOS, session: str):
        r = ToolResult(tool="web_search", input={"q": "Python"}, output={"results": []})
        state.record_tool(session, r)
        p = state.load(session)
        assert len(p.tool_outputs) == 1
        assert p.tool_outputs[0].tool == "web_search"

    def test_record_multiple_tools(self, state: StateOS, session: str):
        for i in range(3):
            state.record_tool(
                session,
                ToolResult(tool=f"tool_{i}", input={}, output=f"result_{i}"),
            )
        p = state.load(session)
        assert len(p.tool_outputs) == 3

    def test_set_workflow_key(self, state: StateOS, session: str):
        state.set_workflow(session, "api_response", {"status": 200})
        p = state.load(session)
        assert p.workflow_state["api_response"] == {"status": 200}

    def test_mark_done(self, state: StateOS, session: str):
        state.mark_done(session)
        assert state.load(session).status == "done"

    def test_mark_failed_with_reason(self, state: StateOS, session: str):
        state.mark_failed(session, reason="Timeout after 30s")
        p = state.load(session)
        assert p.status == "failed"
        assert p.workflow_state["_failure_reason"] == "Timeout after 30s"


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


class TestSnapshots:
    def test_snapshot_creates_record(self, state: StateOS, session: str):
        snap = state.snapshot(session, label="v1")
        assert snap.session_id == session
        assert snap.label == "v1"
        assert snap.id.startswith("snap_")

    def test_snapshot_is_immutable_copy(self, state: StateOS, session: str):
        state.set_goal(session, "original goal")
        snap = state.snapshot(session, label="before")
        state.set_goal(session, "mutated goal")
        snap_loaded = state.get_snapshot(snap.id)
        assert snap_loaded.payload.goal == "original goal"

    def test_multiple_snapshots(self, state: StateOS, session: str):
        state.snapshot(session, label="v1")
        state.snapshot(session, label="v2")
        state.snapshot(session, label="v3")
        snaps = state.list_snapshots(session)
        assert len(snaps) == 3
        labels = [s.label for s in snaps]
        assert "v1" in labels and "v3" in labels

    def test_list_snapshots_oldest_first(self, state: StateOS, session: str):
        for i in range(5):
            time.sleep(0.001)  # ensure distinct timestamps
            state.snapshot(session, label=f"v{i}")
        snaps = state.list_snapshots(session)
        created_ats = [s.created_at for s in snaps]
        assert created_ats == sorted(created_ats)

    def test_get_snapshot_nonexistent_raises(self, state: StateOS):
        with pytest.raises(SnapshotNotFoundError) as exc_info:
            state.get_snapshot("snap_does_not_exist")
        assert "snap_does_not_exist" in str(exc_info.value)

    def test_snapshot_nonexistent_session_raises(self, state: StateOS):
        with pytest.raises(SessionNotFoundError):
            state.snapshot("ghost-session")

    def test_snapshot_captures_tool_outputs(self, state: StateOS, session: str):
        state.record_tool(
            session, ToolResult(tool="read_file", input={}, output="content")
        )
        snap = state.snapshot(session)
        assert len(snap.payload.tool_outputs) == 1
        assert snap.payload.tool_outputs[0].tool == "read_file"


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


class TestRollback:
    def test_rollback_restores_payload(self, state: StateOS, session: str):
        state.set_goal(session, "original")
        snap = state.snapshot(session, label="before-change")
        state.set_goal(session, "mutated")
        assert state.load(session).goal == "mutated"

        state.rollback(snap.id)
        assert state.load(session).goal == "original"

    def test_rollback_bumps_version(self, state: StateOS, session: str):
        snap = state.snapshot(session)
        v_before = state.load(session).version
        state.rollback(snap.id)
        v_after = state.load(session).version
        assert v_after > v_before

    def test_rollback_does_not_delete_intermediate_snapshots(
        self, state: StateOS, session: str
    ):
        snap1 = state.snapshot(session, label="v1")
        state.set_goal(session, "mutated")
        snap2 = state.snapshot(session, label="v2")
        state.rollback(snap1.id)
        # snap2 should still exist
        assert state.get_snapshot(snap2.id) is not None

    def test_rollback_nonexistent_snapshot_raises(self, state: StateOS):
        with pytest.raises(SnapshotNotFoundError):
            state.rollback("snap_fake_id")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_fields(self, state: StateOS, session: str):
        state.set_goal(session, "Test goal")
        state.set_plan(session, ["A", "B"])
        state.snapshot(session, label="s1")
        state.checkpoint(session)

        info = state.summary(session)
        assert info["goal"] == "Test goal"
        assert info["plan_length"] == 2
        assert info["snapshots"] == 1
        assert info["checkpoints"] == 1
        assert info["forked_from"] is None

    def test_summary_nonexistent_raises(self, state: StateOS):
        with pytest.raises(SessionNotFoundError):
            state.summary("ghost")
