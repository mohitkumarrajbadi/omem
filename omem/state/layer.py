"""State layer facade — Phase 2 of the v2 implementation plan.

``StateOS`` is the v2 state engine. It stores agent execution state
(goals, plans, tool outputs, workflow progress) separately from memory,
and provides Git-like snapshot/rollback/fork semantics.

Implementation target: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md Phase 2.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data contracts (Phase 2 — add to omem/types.py when implementing)
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """A single tool invocation result recorded in session state."""

    tool: str
    input: Dict[str, Any]
    output: Any
    timestamp: float
    error: Optional[str] = None


@dataclass
class StatePayload:
    """Full execution state of an agent session."""

    session_id: str
    goal: Optional[str] = None
    plan: List[str] = field(default_factory=list)
    step: int = 0
    status: str = "idle"  # idle | running | paused | failed | done
    workflow_state: Dict[str, Any] = field(default_factory=dict)
    tool_outputs: List[ToolResult] = field(default_factory=list)
    agent_metadata: Dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"
    updated_at: float = 0.0


@dataclass
class StateSnapshot:
    """Immutable point-in-time copy of a session's state."""

    id: str
    session_id: str
    label: Optional[str] = None
    parent_id: Optional[str] = None  # populated when forked
    memory_snapshot_ref: Optional[str] = None
    created_at: float = 0.0
    payload: Optional[StatePayload] = None


@dataclass
class StateCheckpoint:
    """Lightweight crash-recovery marker."""

    id: str
    session_id: str
    payload_hash: str
    created_at: float = 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class StateOS:
    """V2 state layer.

    ``StateOS`` gives agents Git-like state semantics: save progress, take
    immutable snapshots, roll back to any prior snapshot, fork into parallel
    plan branches, and resume after a crash via checkpoints.

    This class is a typed stub. All methods raise ``NotImplementedError``
    until Phase 2 is implemented. The data model above is the Phase 2 contract.

    Example (after Phase 2)::

        state = StateOS()
        state.save("agent-1", StatePayload(session_id="agent-1", goal="Refactor auth"))
        snap = state.snapshot("agent-1", label="before-oauth")

        branch = state.fork(snap.id)
        # ... run plan B on branch ...
        state.rollback(snap.id)   # discard branch, back to snapshot
    """

    def save(self, session_id: str, payload: StatePayload) -> None:
        """Persist session state."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def load(self, session_id: str) -> StatePayload:
        """Restore the latest state for a session."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def update(self, session_id: str, **fields: Any) -> StatePayload:
        """Patch specific fields on the current session state."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def set_goal(self, session_id: str, goal: str) -> None:
        """Set the top-level goal for a session."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def set_plan(self, session_id: str, plan: List[str]) -> None:
        """Replace the ordered plan steps for a session."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def record_tool(self, session_id: str, result: ToolResult) -> None:
        """Append a tool invocation result to session state."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def snapshot(
        self,
        session_id: str,
        label: Optional[str] = None,
    ) -> StateSnapshot:
        """Create an immutable point-in-time snapshot of session state."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def rollback(self, snapshot_id: str) -> StatePayload:
        """Restore session state to a prior snapshot."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def fork(
        self,
        snapshot_id: str,
        new_session_id: Optional[str] = None,
    ) -> str:
        """Create a new independent session branched from a snapshot.

        Returns the new session ID.
        """
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def checkpoint(self, session_id: str) -> str:
        """Write a lightweight crash-recovery marker. Returns checkpoint ID."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def resume(self, checkpoint_id: str) -> StatePayload:
        """Restore session state from the nearest checkpoint."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def list_snapshots(self, session_id: str) -> List[StateSnapshot]:
        """Return all snapshots for a session in chronological order."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def merge(
        self,
        winning_session_id: str,
        losing_session_id: str,
    ) -> StatePayload:
        """Merge the winning branch back into the base and discard the loser."""
        raise NotImplementedError("Phase 2 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")
