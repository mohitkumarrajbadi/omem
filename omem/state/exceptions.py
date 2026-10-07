"""Exceptions for the state layer (Phase 2)."""


class StateError(Exception):
    """Base exception for all state layer errors."""


class SessionNotFoundError(StateError):
    """Raised when a session_id does not exist in storage."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id!r}")


class SessionNamespaceConflictError(StateError):
    """Raised when a session_id exists under a different namespace (cross-tenant)."""

    def __init__(
        self,
        session_id: str,
        existing_namespace: str,
        requested_namespace: str,
    ) -> None:
        self.session_id = session_id
        self.existing_namespace = existing_namespace
        self.requested_namespace = requested_namespace
        super().__init__(
            f"Session {session_id!r} belongs to namespace "
            f"{existing_namespace!r}, not {requested_namespace!r}"
        )


class SnapshotNotFoundError(StateError):
    """Raised when a snapshot_id does not exist in storage."""

    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        super().__init__(f"Snapshot not found: {snapshot_id!r}")


class CheckpointNotFoundError(StateError):
    """Raised when a checkpoint_id does not exist in storage."""

    def __init__(self, checkpoint_id: str) -> None:
        self.checkpoint_id = checkpoint_id
        super().__init__(f"Checkpoint not found: {checkpoint_id!r}")


class MergeError(StateError):
    """Raised when a merge operation cannot be completed."""


class ForkError(StateError):
    """Raised when a fork operation cannot be completed."""


class RunNotFoundError(StateError):
    """Raised when a run_id does not exist."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Run not found: {run_id!r}")


class RunEventError(StateError):
    """Raised when a run event cannot be appended or validated."""


class IdempotencyConflictError(RunEventError):
    """Raised when the same idempotency key is reused with a different payload."""

    def __init__(self, run_id: str, idempotency_key: str) -> None:
        self.run_id = run_id
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Idempotency key {idempotency_key!r} already used on run {run_id!r} "
            f"with a different payload"
        )
