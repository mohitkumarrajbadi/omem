"""Tests for StateOS checkpoint and crash-recovery semantics.

Checkpoints are the lightweight cousins of snapshots — agents write
them frequently (after every tool call) for cheap crash recovery.
"""

import pytest

from omem.state import InMemoryStateBackend, StateOS, StatePayload, ToolResult
from omem.state.exceptions import CheckpointNotFoundError, SessionNotFoundError


@pytest.fixture
def state():
    return StateOS(backend=InMemoryStateBackend())


@pytest.fixture
def session(state: StateOS) -> str:
    sid = "crash-test-session"
    state.save(sid, StatePayload(session_id=sid))
    state.set_goal(sid, "Process dataset")
    state.set_plan(sid, ["Load data", "Clean data", "Train model", "Evaluate"])
    return sid


# ---------------------------------------------------------------------------
# Checkpoint creation
# ---------------------------------------------------------------------------


class TestCheckpointCreation:
    def test_checkpoint_returns_id(self, state: StateOS, session: str):
        chk_id = state.checkpoint(session)
        assert chk_id.startswith("chk_")

    def test_checkpoint_stores_payload(self, state: StateOS, session: str):
        state.advance(session)  # step 1
        chk_id = state.checkpoint(session)
        chk = state._backend.get_checkpoint(chk_id)
        assert chk is not None
        assert chk.payload.step == 1

    def test_checkpoint_has_hash(self, state: StateOS, session: str):
        chk_id = state.checkpoint(session)
        chk = state._backend.get_checkpoint(chk_id)
        assert len(chk.payload_hash) == 16

    def test_different_payloads_have_different_hashes(self, state: StateOS, session: str):
        chk1_id = state.checkpoint(session)
        state.advance(session)
        chk2_id = state.checkpoint(session)
        chk1 = state._backend.get_checkpoint(chk1_id)
        chk2 = state._backend.get_checkpoint(chk2_id)
        assert chk1.payload_hash != chk2.payload_hash

    def test_checkpoint_nonexistent_session_raises(self, state: StateOS):
        with pytest.raises(SessionNotFoundError):
            state.checkpoint("ghost-session")

    def test_multiple_checkpoints_accumulate(self, state: StateOS, session: str):
        for _ in range(5):
            state.checkpoint(session)
        chks = state.list_checkpoints(session)
        assert len(chks) == 5


# ---------------------------------------------------------------------------
# Resume from checkpoint
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_restores_step(self, state: StateOS, session: str):
        state.advance(session)
        state.advance(session)  # step 2
        chk_id = state.checkpoint(session)
        state.advance(session)  # step 3 — "work done after checkpoint"
        recovered = state.resume(chk_id)
        assert recovered.step == 2

    def test_resume_updates_live_session(self, state: StateOS, session: str):
        chk_id = state.checkpoint(session)
        state.set_goal(session, "Changed after checkpoint")
        state.resume(chk_id)
        live = state.load(session)
        assert live.goal == "Process dataset"

    def test_resume_bumps_version(self, state: StateOS, session: str):
        chk_id = state.checkpoint(session)
        v_before = state.load(session).version
        recovered = state.resume(chk_id)
        assert recovered.version > v_before

    def test_resume_nonexistent_checkpoint_raises(self, state: StateOS):
        with pytest.raises(CheckpointNotFoundError) as exc_info:
            state.resume("chk_does_not_exist")
        assert "chk_does_not_exist" in str(exc_info.value)

    def test_resume_latest_selects_most_recent(self, state: StateOS, session: str):
        state.advance(session)  # step 1
        state.checkpoint(session)
        state.advance(session)  # step 2
        state.checkpoint(session)
        state.advance(session)  # step 3
        # crash — resume from most recent (step 2)
        recovered = state.resume_latest(session)
        assert recovered.step == 2

    def test_resume_latest_no_checkpoints_raises(self, state: StateOS, session: str):
        with pytest.raises(CheckpointNotFoundError):
            state.resume_latest(session)

    def test_resume_preserves_tool_outputs(self, state: StateOS, session: str):
        state.record_tool(session, ToolResult(tool="load", input={}, output={"rows": 100}))
        chk_id = state.checkpoint(session)
        # "crash": mutate the session past the checkpoint
        state.record_tool(session, ToolResult(tool="clean", input={}, output={}))
        recovered = state.resume(chk_id)
        # Should have only the tool recorded before the checkpoint
        assert len(recovered.tool_outputs) == 1
        assert recovered.tool_outputs[0].tool == "load"


# ---------------------------------------------------------------------------
# Crash simulation
# ---------------------------------------------------------------------------


class TestCrashSimulation:
    def test_full_crash_recovery_cycle(self, state: StateOS, session: str):
        """Simulate a multi-step agent that checkpoints and recovers after crash."""
        # Step 1: Load data
        state.advance(session)
        state.record_tool(session, ToolResult(tool="read_csv", input={}, output={"rows": 500}))
        state.checkpoint(session)

        # Step 2: Clean data
        state.advance(session)
        state.record_tool(session, ToolResult(tool="clean", input={}, output={"dropped": 10}))
        state.checkpoint(session)

        # Step 3 starts but crashes — simulate by NOT checkpointing
        state.advance(session)
        # "Crash" — use a brand-new StateOS with the same backend to simulate restart
        backend = state._backend
        fresh_state = StateOS(backend=backend)

        # Recover from last checkpoint
        recovered = fresh_state.resume_latest(session)
        assert recovered.step == 2  # back to step 2 (after clean)
        assert len(recovered.tool_outputs) == 2

    def test_checkpoint_after_each_tool_call_pattern(self, state: StateOS, session: str):
        """Each tool call is immediately checkpointed — the recommended agent pattern."""
        tools = ["fetch", "parse", "summarize", "store"]
        for tool in tools:
            state.record_tool(session, ToolResult(tool=tool, input={}, output="ok"))
            state.checkpoint(session)

        chks = state.list_checkpoints(session)
        assert len(chks) == 4
        # Latest checkpoint has all 4 tool outputs
        latest = max(chks, key=lambda c: c.created_at)
        assert len(latest.payload.tool_outputs) == 4
