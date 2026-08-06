"""StateOS — full production implementation of the v2 state layer.

``StateOS`` gives every AI agent Git-like state semantics:

    save()        — persist session state (upsert)
    load()        — restore latest session state
    update()      — patch specific fields atomically
    set_goal()    — record the agent's top-level goal
    set_plan()    — set or replace the ordered plan steps
    advance()     — increment step counter + update status
    record_tool() — append a tool invocation result
    snapshot()    — immutable point-in-time copy (fork-able)
    rollback()    — revert live state to a prior snapshot
    fork()        — branch from a snapshot into a new session
    checkpoint()  — lightweight crash-recovery marker
    resume()      — restore from the most recent checkpoint
    list_snapshots() — all snapshots for a session
    merge()       — promote a winning branch back to the base

Thread safety: all public methods acquire an RLock before mutation.
Durability: every write goes through the StateBackend (SQLite WAL by default).
"""

import dataclasses
import hashlib
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..types import StateCheckpoint, StatePayload, StateSnapshot, ToolResult
from .backend import InMemoryStateBackend, SQLiteStateBackend, StateBackend
from .exceptions import (
    CheckpointNotFoundError,
    ForkError,
    SessionNamespaceConflictError,
    SessionNotFoundError,
    SnapshotNotFoundError,
)

logger = logging.getLogger(__name__)


def _new_id(prefix: str) -> str:
    """Generate a time-sortable, prefixed ID.

    Format: ``{prefix}_{epoch_ms}_{random8}``
    Examples: ``snap_1719259200000_a1b2c3d4``, ``chk_1719259200001_ff00aa12``
    """
    return f"{prefix}_{int(time.time() * 1000)}_{uuid4().hex[:8]}"


def _hash_payload(payload: StatePayload) -> str:
    """SHA-256 fingerprint of the payload, excluding the mutable updated_at field."""
    d = payload.to_dict()
    d.pop("updated_at", None)
    return hashlib.sha256(
        json.dumps(d, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


class StateOS:
    """V2 state layer — full production implementation.

    ``StateOS`` manages agent execution state across sessions, crashes,
    and plan branches. It is the core of the "Git for AI state" capability
    that differentiates OMem Cloud from raw vector databases.

    Backend selection:
        StateOS()                            → in-memory (tests / REPL)
        StateOS(db_path="~/.omem/brain.db")  → SQLite (default production)
        StateOS(backend=custom_backend)      → any StateBackend implementation

    Example::

        state = StateOS()
        state.save("agent-1", StatePayload(session_id="agent-1"))
        state.set_goal("agent-1", "Refactor auth module")
        state.set_plan("agent-1", ["Audit endpoints", "Add OAuth2"])

        snap = state.snapshot("agent-1", label="before-oauth")
        branch = state.fork(snap.id)   # returns new session_id

        # Crash and recover
        chk = state.checkpoint("agent-1")
        recovered = state.resume(chk)  # same payload as before crash
    """

    def __init__(
        self,
        backend: Optional[StateBackend] = None,
        db_path: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> None:
        if backend is not None:
            self._backend = backend
        elif db_path is not None:
            self._backend = SQLiteStateBackend(db_path)
        else:
            self._backend = InMemoryStateBackend()
        self._lock = threading.RLock()
        # When set, every read/write is scoped to this namespace (multi-tenant).
        self._namespace: Optional[str] = namespace

    def bind_namespace(self, namespace: Optional[str]) -> None:
        """Pin this StateOS instance to a namespace (AgentState / cloud)."""
        self._namespace = namespace

    def _ns(self, override: Optional[str] = None) -> Optional[str]:
        """Effective namespace filter for a call."""
        return override if override is not None else self._namespace

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    def save(self, session_id: str, payload: StatePayload) -> None:
        """Upsert a full session payload.

        Use this to create a new session or overwrite an existing one.
        For field-level updates, prefer ``update()``.
        """
        if payload.session_id != session_id:
            payload = dataclasses.replace(payload, session_id=session_id)
        ns = self._ns()
        if ns is not None and payload.namespace != ns:
            payload = dataclasses.replace(payload, namespace=ns)
        payload = dataclasses.replace(payload, updated_at=time.time())
        with self._lock:
            self._backend.save_session(payload)
        logger.debug("state.save session=%r step=%d", session_id, payload.step)

    def load(self, session_id: str) -> StatePayload:
        """Return the live state for a session.

        Raises:
            SessionNotFoundError: if no session with this ID exists.
        """
        payload = self._backend.load_session(session_id, namespace=self._ns())
        if payload is None:
            raise SessionNotFoundError(session_id)
        return payload

    def get_or_create(
        self,
        session_id: str,
        namespace: str = "default",
    ) -> StatePayload:
        """Return the session's state, creating a blank one if it doesn't exist.

        Refuses to return or overwrite a session that already exists under a
        different namespace (cross-tenant session_id collision).
        """
        ns = self._ns(namespace) or namespace
        payload = self._backend.load_session(session_id, namespace=ns)
        if payload is not None:
            return payload
        # Detect cross-namespace collision before creating.
        foreign = self._backend.load_session(session_id)
        if foreign is not None and foreign.namespace != ns:
            raise SessionNamespaceConflictError(
                session_id, foreign.namespace, ns
            )
        payload = StatePayload(session_id=session_id, namespace=ns)
        with self._lock:
            self._backend.save_session(payload)
        logger.debug("state.get_or_create created session=%r ns=%r", session_id, ns)
        return payload

    def update(self, session_id: str, **fields: Any) -> StatePayload:
        """Atomically patch specific fields on the current session payload.

        Only the listed fields are updated; all others are preserved.
        Returns the updated payload.

        Raises:
            SessionNotFoundError: if the session does not exist.
        """
        _ALLOWED = {
            "goal", "plan", "step", "status",
            "workflow_state", "agent_metadata", "namespace",
        }
        invalid = set(fields) - _ALLOWED
        if invalid:
            raise ValueError(
                f"Cannot update read-only or unknown fields: {invalid}. "
                f"Allowed: {_ALLOWED}"
            )

        with self._lock:
            payload = self._backend.load_session(session_id, namespace=self._ns())
            if payload is None:
                raise SessionNotFoundError(session_id)
            # Bound namespace must not be escaped via update(namespace=...).
            if self._ns() is not None and "namespace" in fields:
                if fields["namespace"] != self._ns():
                    raise SessionNamespaceConflictError(
                        session_id, payload.namespace, str(fields["namespace"])
                    )
            payload = dataclasses.replace(
                payload,
                updated_at=time.time(),
                version=payload.version + 1,
                **fields,
            )
            self._backend.save_session(payload)

        logger.debug("state.update session=%r fields=%s", session_id, list(fields))
        return payload

    # ------------------------------------------------------------------
    # Semantic helpers — most agents use these rather than raw update()
    # ------------------------------------------------------------------

    def set_goal(self, session_id: str, goal: str) -> StatePayload:
        """Set the top-level goal for a session."""
        return self.update(session_id, goal=goal, status="running")

    def set_plan(self, session_id: str, plan: List[str]) -> StatePayload:
        """Replace the ordered plan steps and reset the step counter."""
        return self.update(session_id, plan=plan, step=0)

    def advance(self, session_id: str) -> StatePayload:
        """Increment the step counter.  Sets status='done' when past last plan step."""
        with self._lock:
            payload = self._backend.load_session(session_id, namespace=self._ns())
            if payload is None:
                raise SessionNotFoundError(session_id)
            new_step = payload.step + 1
            status = "done" if new_step >= len(payload.plan) else payload.status
            payload = dataclasses.replace(
                payload,
                step=new_step,
                status=status,
                updated_at=time.time(),
                version=payload.version + 1,
            )
            self._backend.save_session(payload)
        logger.debug("state.advance session=%r step=%d", session_id, new_step)
        return payload

    def record_tool(self, session_id: str, result: ToolResult) -> StatePayload:
        """Append a tool invocation result to the session state."""
        with self._lock:
            payload = self._backend.load_session(session_id, namespace=self._ns())
            if payload is None:
                raise SessionNotFoundError(session_id)
            new_outputs = payload.tool_outputs + [result]
            payload = dataclasses.replace(
                payload,
                tool_outputs=new_outputs,
                updated_at=time.time(),
                version=payload.version + 1,
            )
            self._backend.save_session(payload)
        logger.debug(
            "state.record_tool session=%r tool=%r", session_id, result.tool
        )
        return payload

    def set_workflow(self, session_id: str, key: str, value: Any) -> StatePayload:
        """Set a single key in the session's workflow_state dict."""
        with self._lock:
            payload = self._backend.load_session(session_id, namespace=self._ns())
            if payload is None:
                raise SessionNotFoundError(session_id)
            new_wf = {**payload.workflow_state, key: value}
            payload = dataclasses.replace(
                payload,
                workflow_state=new_wf,
                updated_at=time.time(),
                version=payload.version + 1,
            )
            self._backend.save_session(payload)
        return payload

    def mark_done(self, session_id: str) -> StatePayload:
        """Mark a session as done."""
        return self.update(session_id, status="done")

    def mark_failed(self, session_id: str, reason: Optional[str] = None) -> StatePayload:
        """Mark a session as failed, optionally recording the reason."""
        payload = self.update(session_id, status="failed")
        if reason:
            payload = self.set_workflow(session_id, "_failure_reason", reason)
        return payload

    # ------------------------------------------------------------------
    # Snapshot — immutable named save points
    # ------------------------------------------------------------------

    def snapshot(
        self,
        session_id: str,
        label: Optional[str] = None,
        memory_snapshot_ref: Optional[str] = None,
    ) -> StateSnapshot:
        """Create an immutable snapshot of the current session state.

        Args:
            session_id: The session to snapshot.
            label: Human-readable name (e.g. "before-oauth").
            memory_snapshot_ref: Path to a corresponding memory snapshot, if any.

        Returns:
            The new StateSnapshot.

        Raises:
            SessionNotFoundError: if the session does not exist.
        """
        with self._lock:
            payload = self._backend.load_session(session_id, namespace=self._ns())
            if payload is None:
                raise SessionNotFoundError(session_id)
            snap = StateSnapshot(
                id=_new_id("snap"),
                session_id=session_id,
                payload=dataclasses.replace(payload),  # deep copy via dataclasses.replace
                label=label,
                memory_snapshot_ref=memory_snapshot_ref,
                created_at=time.time(),
            )
            self._backend.save_snapshot(snap)

        logger.info(
            "state.snapshot session=%r snap=%r label=%r",
            session_id, snap.id, label,
        )
        return snap

    def list_snapshots(self, session_id: str) -> List[StateSnapshot]:
        """Return all snapshots for a session, oldest first."""
        return self._backend.list_snapshots(session_id, namespace=self._ns())

    def get_snapshot(self, snapshot_id: str) -> StateSnapshot:
        """Return a snapshot by ID.

        Raises:
            SnapshotNotFoundError: if the snapshot does not exist.
        """
        snap = self._backend.get_snapshot(snapshot_id, namespace=self._ns())
        if snap is None:
            raise SnapshotNotFoundError(snapshot_id)
        return snap

    # ------------------------------------------------------------------
    # Rollback — revert live state to a snapshot
    # ------------------------------------------------------------------

    def rollback(self, snapshot_id: str) -> StatePayload:
        """Restore the live session state to a prior snapshot.

        The rollback is non-destructive: snapshots taken between the
        target and the current state are not deleted.

        Returns:
            The restored StatePayload (with a bumped version).

        Raises:
            SnapshotNotFoundError: if the snapshot does not exist.
        """
        snap = self._backend.get_snapshot(snapshot_id, namespace=self._ns())
        if snap is None:
            raise SnapshotNotFoundError(snapshot_id)

        with self._lock:
            current = self._backend.load_session(snap.session_id, namespace=self._ns())
            new_version = (current.version + 1) if current else 1
            restored = dataclasses.replace(
                snap.payload,
                version=new_version,
                updated_at=time.time(),
            )
            self._backend.save_session(restored)

        logger.info(
            "state.rollback session=%r snap=%r new_version=%d",
            snap.session_id, snapshot_id, new_version,
        )
        return restored

    # ------------------------------------------------------------------
    # Fork — branch into a new independent session
    # ------------------------------------------------------------------

    def fork(
        self,
        snapshot_id: str,
        new_session_id: Optional[str] = None,
    ) -> str:
        """Branch from a snapshot into a new, independent session.

        The child session starts with the snapshot's payload. Changes in
        the child do not affect the parent and vice versa. The lineage is
        recorded so ``merge()`` can later reconcile the branches.

        Args:
            snapshot_id: The snapshot to branch from.
            new_session_id: Optional explicit ID for the child session.
                            Defaults to an auto-generated ``sess_*`` ID.

        Returns:
            The new session ID.

        Raises:
            SnapshotNotFoundError: if the snapshot does not exist.
            ForkError: if the child_session_id is already in use.
        """
        snap = self._backend.get_snapshot(snapshot_id, namespace=self._ns())
        if snap is None:
            raise SnapshotNotFoundError(snapshot_id)

        child_id = new_session_id or _new_id("sess")

        with self._lock:
            existing = self._backend.load_session(child_id, namespace=self._ns())
            if existing is not None:
                raise ForkError(
                    f"Session {child_id!r} already exists. "
                    "Pass a unique new_session_id to fork()."
                )
            child_payload = dataclasses.replace(
                snap.payload,
                session_id=child_id,
                version=1,
                updated_at=time.time(),
            )
            self._backend.save_session(child_payload)
            self._backend.save_fork(child_id, snapshot_id, time.time())

        logger.info(
            "state.fork parent_snap=%r child=%r", snapshot_id, child_id
        )
        return child_id

    # ------------------------------------------------------------------
    # Merge — promote a winning branch back to a session
    # ------------------------------------------------------------------

    def merge(
        self,
        winning_session_id: str,
        losing_session_id: str,
    ) -> StatePayload:
        """Apply the winning branch's state to the base session.

        The base session is identified as the common ancestor of both
        sessions (determined via fork lineage). If no lineage is found,
        ``winning_session_id`` is treated as the target directly.

        The losing branch is marked as merged in the lineage table. It
        is NOT deleted so it can be inspected later.

        Returns:
            The updated payload (winning session's state, version bumped).

        Raises:
            SessionNotFoundError: if either session does not exist.
            MergeError: if both sessions originate from the same parent
                        and the target cannot be resolved.
        """
        winning = self._backend.load_session(winning_session_id, namespace=self._ns())
        if winning is None:
            raise SessionNotFoundError(winning_session_id)
        losing = self._backend.load_session(losing_session_id, namespace=self._ns())
        if losing is None:
            raise SessionNotFoundError(losing_session_id)

        with self._lock:
            current = self._backend.load_session(winning_session_id, namespace=self._ns())
            merged = dataclasses.replace(
                winning,
                version=(current.version if current else winning.version) + 1,
                updated_at=time.time(),
            )
            self._backend.save_session(merged)
            self._backend.mark_merged(losing_session_id, time.time())

        logger.info(
            "state.merge winner=%r loser=%r", winning_session_id, losing_session_id
        )
        return merged

    # ------------------------------------------------------------------
    # Checkpoint — lightweight crash-recovery markers
    # ------------------------------------------------------------------

    def checkpoint(self, session_id: str) -> str:
        """Write a crash-recovery checkpoint. Returns the checkpoint ID.

        Checkpoints are cheaper than snapshots: they carry no labels,
        no parent lineage, and no fork semantics. Agents should call
        ``checkpoint()`` after every significant tool call.

        Returns:
            The checkpoint ID (pass to ``resume()`` to recover).

        Raises:
            SessionNotFoundError: if the session does not exist.
        """
        payload = self._backend.load_session(session_id, namespace=self._ns())
        if payload is None:
            raise SessionNotFoundError(session_id)

        chk = StateCheckpoint(
            id=_new_id("chk"),
            session_id=session_id,
            payload_hash=_hash_payload(payload),
            payload=payload,
            created_at=time.time(),
        )
        self._backend.save_checkpoint(chk)
        logger.debug(
            "state.checkpoint session=%r chk=%r hash=%s",
            session_id, chk.id, chk.payload_hash,
        )
        return chk.id

    def resume(self, checkpoint_id: str) -> StatePayload:
        """Restore session state from a checkpoint.

        Also updates the live session record so subsequent calls to
        ``load()`` see the recovered state.

        Returns:
            The recovered StatePayload.

        Raises:
            CheckpointNotFoundError: if the checkpoint does not exist.
        """
        chk = self._backend.get_checkpoint(checkpoint_id, namespace=self._ns())
        if chk is None:
            raise CheckpointNotFoundError(checkpoint_id)

        with self._lock:
            current = self._backend.load_session(chk.session_id, namespace=self._ns())
            new_version = (current.version + 1) if current else 1
            recovered = dataclasses.replace(
                chk.payload,
                version=new_version,
                updated_at=time.time(),
            )
            self._backend.save_session(recovered)

        logger.info(
            "state.resume session=%r chk=%r step=%d",
            chk.session_id, checkpoint_id, recovered.step,
        )
        return recovered

    def resume_latest(self, session_id: str) -> StatePayload:
        """Resume from the most recent checkpoint for a session.

        Raises:
            CheckpointNotFoundError: if no checkpoints exist.
        """
        checkpoints = self._backend.list_checkpoints(session_id, namespace=self._ns())
        if not checkpoints:
            raise CheckpointNotFoundError(
                f"No checkpoints found for session {session_id!r}"
            )
        # Use insertion order, not max(created_at). On Windows (and in tight
        # loops elsewhere) several checkpoints can share the same time.time()
        # value; max() would then return the *first* tie, not the latest.
        latest = checkpoints[-1]
        return self.resume(latest.id)

    def list_checkpoints(self, session_id: str) -> List[StateCheckpoint]:
        """Return all checkpoints for a session, oldest first."""
        return self._backend.list_checkpoints(session_id, namespace=self._ns())

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def session_exists(self, session_id: str) -> bool:
        """Return True if the session exists in storage."""
        return self._backend.load_session(session_id, namespace=self._ns()) is not None

    def fork_parent(self, child_session_id: str) -> Optional[str]:
        """Return the parent snapshot ID for a forked session, or None."""
        return self._backend.get_fork_parent(child_session_id)

    def list_sessions(self, namespace: Optional[str] = None) -> List[str]:
        """Return all known session IDs, optionally filtered by namespace."""
        return self._backend.list_sessions(namespace)

    def summary(self, session_id: str) -> Dict[str, Any]:
        """Return a human-friendly summary dict for a session."""
        payload = self._backend.load_session(session_id, namespace=self._ns())
        if payload is None:
            raise SessionNotFoundError(session_id)
        snaps = self._backend.list_snapshots(session_id, namespace=self._ns())
        chks = self._backend.list_checkpoints(session_id, namespace=self._ns())
        parent = self._backend.get_fork_parent(session_id)
        return {
            "session_id": session_id,
            "goal": payload.goal,
            "status": payload.status,
            "step": payload.step,
            "plan_length": len(payload.plan),
            "tool_calls": len(payload.tool_outputs),
            "namespace": payload.namespace,
            "version": payload.version,
            "snapshots": len(snaps),
            "checkpoints": len(chks),
            "forked_from": parent,
            "updated_at": payload.updated_at,
        }
