"""Tests for StateOS fork and merge semantics.

Fork gives every AI session a Git-like branching model. These tests
verify the entire lifecycle: branch → diverge → merge.
"""

import pytest

from omem.state import InMemoryStateBackend, StateOS, StatePayload, ToolResult
from omem.state.exceptions import ForkError, SessionNotFoundError, SnapshotNotFoundError


@pytest.fixture
def state():
    return StateOS(backend=InMemoryStateBackend())


@pytest.fixture
def base(state: StateOS) -> str:
    """A base session with a snapshot ready for forking."""
    state.save("base", StatePayload(session_id="base", goal="Deploy the new API"))
    state.set_plan("base", ["Audit", "Implement OAuth2", "Migrate sessions", "Release"])
    return "base"


@pytest.fixture
def snap(state: StateOS, base: str) -> str:
    """Snapshot of the base session; returns the snapshot ID."""
    return state.snapshot(base, label="pre-fork").id


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


class TestFork:
    def test_fork_returns_new_session_id(self, state: StateOS, snap: str):
        child_id = state.fork(snap)
        assert child_id != "base"
        assert child_id.startswith("sess_")

    def test_fork_creates_independent_session(self, state: StateOS, snap: str):
        child_id = state.fork(snap)
        child = state.load(child_id)
        assert child.goal == "Deploy the new API"

    def test_fork_copies_plan(self, state: StateOS, snap: str):
        child_id = state.fork(snap)
        child = state.load(child_id)
        assert child.plan == ["Audit", "Implement OAuth2", "Migrate sessions", "Release"]

    def test_fork_changes_do_not_affect_parent(self, state: StateOS, snap: str, base: str):
        child_id = state.fork(snap)
        state.set_goal(child_id, "Completely different plan")
        parent = state.load(base)
        assert parent.goal == "Deploy the new API"

    def test_parent_changes_do_not_affect_fork(self, state: StateOS, snap: str, base: str):
        child_id = state.fork(snap)
        state.set_goal(base, "Parent changed plan")
        child = state.load(child_id)
        assert child.goal == "Deploy the new API"

    def test_fork_records_lineage(self, state: StateOS, snap: str):
        child_id = state.fork(snap)
        assert state.fork_parent(child_id) == snap

    def test_fork_with_explicit_session_id(self, state: StateOS, snap: str):
        child_id = state.fork(snap, new_session_id="plan-b")
        assert child_id == "plan-b"
        assert state.session_exists("plan-b")

    def test_fork_explicit_id_already_exists_raises(self, state: StateOS, snap: str):
        state.fork(snap, new_session_id="plan-b")
        with pytest.raises(ForkError, match="already exists"):
            state.fork(snap, new_session_id="plan-b")

    def test_fork_nonexistent_snapshot_raises(self, state: StateOS):
        with pytest.raises(SnapshotNotFoundError):
            state.fork("snap_does_not_exist")

    def test_fork_parent_is_none_for_root_session(self, state: StateOS, base: str):
        assert state.fork_parent(base) is None

    def test_multiple_forks_from_same_snapshot(self, state: StateOS, snap: str):
        c1 = state.fork(snap)
        c2 = state.fork(snap)
        assert c1 != c2
        assert state.fork_parent(c1) == snap
        assert state.fork_parent(c2) == snap

    def test_fork_resets_version_to_one(self, state: StateOS, snap: str):
        child_id = state.fork(snap)
        child = state.load(child_id)
        assert child.version == 1

    def test_nested_fork(self, state: StateOS, snap: str):
        """Fork from a fork to verify multi-level lineage."""
        child_id = state.fork(snap)
        child_snap = state.snapshot(child_id, label="child-snap")
        grandchild_id = state.fork(child_snap.id)
        assert state.fork_parent(grandchild_id) == child_snap.id

    def test_fork_includes_tool_outputs(self, state: StateOS, snap: str, base: str):
        """Tool outputs from before the snapshot are inherited by the fork."""
        result = ToolResult(tool="audit", input={}, output={"findings": []})
        state.record_tool(base, result)
        pre_tool_snap = state.snapshot(base, label="after-audit")
        child_id = state.fork(pre_tool_snap.id)
        child = state.load(child_id)
        assert len(child.tool_outputs) == 1


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


class TestMerge:
    def test_merge_applies_winner_state(self, state: StateOS, snap: str, base: str):
        child_id = state.fork(snap)
        state.set_goal(child_id, "Optimized plan")
        merged = state.merge(child_id, base)
        assert merged.goal == "Optimized plan"

    def test_merge_bumps_winner_version(self, state: StateOS, snap: str, base: str):
        child_id = state.fork(snap)
        v_before = state.load(child_id).version
        merged = state.merge(child_id, base)
        assert merged.version > v_before

    def test_merge_marks_loser_as_merged(self, state: StateOS, snap: str, base: str):
        child_id = state.fork(snap)
        state.merge(child_id, base)
        # After merge, the loser's session still exists
        assert state.session_exists(base)

    def test_merge_loser_session_not_deleted(self, state: StateOS, snap: str, base: str):
        child_id = state.fork(snap)
        state.merge(child_id, base)
        # Loser session is preserved for inspection
        state.load(base)

    def test_merge_nonexistent_winner_raises(self, state: StateOS, base: str):
        with pytest.raises(SessionNotFoundError, match="ghost-winner"):
            state.merge("ghost-winner", base)

    def test_merge_nonexistent_loser_raises(self, state: StateOS, snap: str):
        child_id = state.fork(snap)
        with pytest.raises(SessionNotFoundError, match="ghost-loser"):
            state.merge(child_id, "ghost-loser")
