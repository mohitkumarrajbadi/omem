"""V2 state layer — Phase 2 of the implementation plan.

Full implementation — all methods are production-ready.

    from omem.state import StateOS
    from omem.types import StatePayload, StateSnapshot, StateCheckpoint, ToolResult

Quickstart::

    state = StateOS()                            # in-memory (default)
    state = StateOS(db_path="~/.omem/brain.db")  # SQLite (production)

    state.save("my-agent", StatePayload(session_id="my-agent"))
    state.set_goal("my-agent", "Refactor auth module")
    state.set_plan("my-agent", ["Audit endpoints", "Add OAuth2", "Migrate sessions"])

    snap = state.snapshot("my-agent", label="before-oauth")
    branch = state.fork(snap.id)       # plan B

    chk = state.checkpoint("my-agent") # before risky tool call
    state.resume(chk)                  # recover if crash

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 2
"""

from ..types import StateCheckpoint, StatePayload, StateSnapshot, ToolResult
from .backend import InMemoryStateBackend, SQLiteStateBackend, StateBackend
from .exceptions import (
    CheckpointNotFoundError,
    ForkError,
    MergeError,
    SessionNamespaceConflictError,
    SessionNotFoundError,
    SnapshotNotFoundError,
    StateError,
)
from .layer import StateOS

__all__ = [
    # Core API
    "StateOS",
    # Data types
    "StatePayload",
    "StateSnapshot",
    "StateCheckpoint",
    "ToolResult",
    # Backends
    "StateBackend",
    "InMemoryStateBackend",
    "SQLiteStateBackend",
    # Exceptions
    "StateError",
    "SessionNotFoundError",
    "SessionNamespaceConflictError",
    "SnapshotNotFoundError",
    "CheckpointNotFoundError",
    "ForkError",
    "MergeError",
]
