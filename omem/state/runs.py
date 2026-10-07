"""Run lifecycle — OMem v1 dual-write (RunEvent history + StatePayload live cursor).

Crash semantics (§0A.3): a dead process cannot append ``run_crashed``.
``resume_run`` infers crash from stale lease / ``running`` status and appends
``run_resumed`` after marking ``crashed`` when appropriate.

Replay (§0A.2):
  - ``inspect_events`` = Mode B (timeline)
  - ``resume_run`` = Mode A (checkpoint-assisted)
  - ``restore_to_seq`` = Mode C (nearest checkpoint ≤ seq)

Idempotency (§0A.4): L1 record dedupe only — does not guarantee external effects.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..types import (
    Run,
    RunEvent,
    StatePayload,
    is_valid_run_event_type,
)
from .exceptions import (
    CheckpointNotFoundError,
    RunEventError,
    RunNotFoundError,
    SessionNotFoundError,
)
from .run_store import InMemoryRunStore, RunStore, SQLiteRunStore

if TYPE_CHECKING:
    from .layer import StateOS

logger = logging.getLogger(__name__)

_ACTIVE_RUN_KEY = "omem_active_run_id"


def _new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:16]}"


def _new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:16]}"


def _new_worker_id() -> str:
    return f"worker_{uuid.uuid4().hex[:12]}"


class ActiveRun:
    """Handle for one run — record / checkpoint / heartbeat / fork / inspect."""

    def __init__(self, os: "RunOS", run: Run) -> None:
        self._os = os
        self.run_id = run.run_id
        self.session_id = run.session_id

    # -- reads --------------------------------------------------------------

    def refresh(self) -> Run:
        return self._os.get_run(self.run_id)

    @property
    def run(self) -> Run:
        return self.refresh()

    def inspect_events(
        self,
        *,
        from_seq: Optional[int] = None,
        to_seq: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[RunEvent]:
        """Mode B — read-only durable timeline (not tool re-execution)."""
        return self._os.list_events(
            self.run_id, from_seq=from_seq, to_seq=to_seq, limit=limit
        )

    def pending_tool_calls(self) -> List[RunEvent]:
        """``tool_call`` events without a later ``tool_result`` with same causation."""
        events = self.inspect_events()
        results_for: set = set()
        for e in events:
            if e.type == "tool_result" and e.causation_id:
                results_for.add(e.causation_id)
        return [
            e
            for e in events
            if e.type == "tool_call" and e.event_id not in results_for
        ]

    # -- writes -------------------------------------------------------------

    def record(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        actor: str = "agent",
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        payload_ref: Optional[str] = None,
    ) -> RunEvent:
        return self._os.record_event(
            self.run_id,
            event_type,
            payload or {},
            actor=actor,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            payload_ref=payload_ref,
        )

    def checkpoint(self) -> str:
        """Dual-write: StateOS checkpoint (live SoT) + ``checkpoint`` event."""
        return self._os.checkpoint_run(self.run_id)

    def heartbeat(self, worker_id: Optional[str] = None) -> Run:
        return self._os.heartbeat(self.run_id, worker_id=worker_id)

    def complete(self, payload: Optional[Dict[str, Any]] = None) -> Run:
        return self._os.complete_run(self.run_id, payload=payload)

    def fail(self, reason: str = "") -> Run:
        return self._os.fail_run(self.run_id, reason=reason)

    def crash(self, reason: str = "") -> Run:
        """Explicit host-declared crash (process still alive enough to call this)."""
        return self._os.declare_crash(self.run_id, reason=reason)

    def pause(self) -> Run:
        return self._os.pause_run(self.run_id)

    def restore_to_seq(self, seq: int) -> StatePayload:
        """Mode C — restore nearest checkpoint at or before ``seq``; return payload.

        Does **not** re-execute tools/models. Subsequent events after the
        checkpoint remain in history for inspect.
        """
        return self._os.restore_to_seq(self.run_id, seq)

    def fork(
        self,
        checkpoint_id: Optional[str] = None,
        *,
        label: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> "ActiveRun":
        return self._os.fork_run(
            self.run_id,
            checkpoint_id=checkpoint_id,
            label=label,
            worker_id=worker_id,
        )


class RunOS:
    """Run lifecycle manager — dual-writes events + StatePayload via StateOS."""

    def __init__(
        self,
        store: Optional[RunStore] = None,
        state: Optional["StateOS"] = None,
        *,
        namespace: str = "default",
        db_path: Optional[str] = None,
    ) -> None:
        if store is not None:
            self._store = store
        elif db_path is not None:
            self._store = SQLiteRunStore(db_path)
        else:
            self._store = InMemoryRunStore()
        self._state = state
        self.namespace = namespace
        self._lock = threading.RLock()

    # -- factory helpers ----------------------------------------------------

    def start_run(
        self,
        session_id: str,
        *,
        goal: Optional[str] = None,
        agent_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        heartbeat_ms: int = 30000,
        label: Optional[str] = None,
    ) -> ActiveRun:
        """Create a run, acquire lease, ensure session exists, append ``run_started``."""
        now = time.time()
        worker = worker_id or _new_worker_id()
        run = Run(
            run_id=_new_run_id(),
            session_id=session_id,
            namespace=self.namespace,
            agent_id=agent_id,
            status="running",
            goal=goal,
            label=label,
            lease_owner=worker,
            lease_until=now + (heartbeat_ms / 1000.0),
            heartbeat_ms=heartbeat_ms,
            created_at=now,
            updated_at=now,
        )
        self._store.save_run(run)

        if self._state is not None:
            try:
                payload = self._state.get_or_create(session_id, namespace=self.namespace)
            except Exception:
                payload = StatePayload(session_id=session_id, namespace=self.namespace)
                self._state.save(session_id, payload)
                payload = self._state.load(session_id)
            if goal and not payload.goal:
                self._state.set_goal(session_id, goal)
            # Mark active run on live cursor (compatibility projection)
            self._state.set_workflow(session_id, _ACTIVE_RUN_KEY, run.run_id)
            if payload.status == "idle":
                self._state.update(session_id, status="running")

        self.record_event(
            run.run_id,
            "run_started",
            {"goal": goal, "agent_id": agent_id, "label": label},
            actor="system",
            correlation_id=correlation_id,
        )
        return ActiveRun(self, self.get_run(run.run_id))

    def get_run(self, run_id: str) -> Run:
        run = self._store.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        return run

    def list_runs(self, session_id: str) -> List[Run]:
        return self._store.list_runs(session_id, namespace=self.namespace)

    def get_active_run(self, session_id: str) -> Optional[ActiveRun]:
        if self._state is None:
            runs = self.list_runs(session_id)
            active = [r for r in runs if r.status == "running"]
            return ActiveRun(self, active[-1]) if active else None
        try:
            payload = self._state.load(session_id)
        except SessionNotFoundError:
            return None
        rid = (payload.workflow_state or {}).get(_ACTIVE_RUN_KEY)
        if not rid:
            return None
        try:
            return ActiveRun(self, self.get_run(rid))
        except RunNotFoundError:
            return None

    def resume_run(
        self,
        run_id: str,
        *,
        worker_id: Optional[str] = None,
    ) -> ActiveRun:
        """Mode A resume: load latest checkpoint into live StatePayload; renew lease.

        If status is ``running`` with expired/missing lease, mark ``crashed`` then
        ``run_resumed`` (dead process cannot write ``run_crashed`` itself).
        """
        run = self.get_run(run_id)
        now = time.time()
        worker = worker_id or _new_worker_id()
        inferred_crash = False

        if run.status == "running":
            lease_stale = run.lease_until is None or run.lease_until < now
            # New worker reclaiming a still-marked-running run ⇒ inferred crash
            reclaiming = run.lease_owner is not None and run.lease_owner != worker
            if lease_stale or reclaiming:
                inferred_crash = True
                prev_owner = run.lease_owner
                prev_until = run.lease_until
                run.status = "crashed"
                run.updated_at = now
                self._store.save_run(run)
                self.record_event(
                    run_id,
                    "run_crashed",
                    {
                        "reason": "inferred_on_resume",
                        "previous_lease_owner": prev_owner,
                        "lease_until": prev_until,
                    },
                    actor="system",
                )

        # Restore live cursor from latest checkpoint when available
        if self._state is not None:
            chks = self._state.list_checkpoints(run.session_id)
            if chks:
                latest = chks[-1]
                self._state.resume(latest.id)
                # Reconcile hint: events ahead of checkpoint?
                run = self.get_run(run_id)
                if run.last_event_seq > 0:
                    # Find checkpoint event seq if any
                    ck_events = [
                        e
                        for e in self._store.list_events(run_id)
                        if e.type == "checkpoint"
                        and e.payload.get("checkpoint_id") == latest.id
                    ]
                    if ck_events:
                        ck_seq = ck_events[-1].sequence
                        if run.last_event_seq > ck_seq:
                            run.needs_reconcile = True

        run = self.get_run(run_id)
        run.status = "running"
        run.lease_owner = worker
        run.lease_until = now + (run.heartbeat_ms / 1000.0)
        run.updated_at = now
        self._store.save_run(run)

        if self._state is not None:
            try:
                self._state.set_workflow(run.session_id, _ACTIVE_RUN_KEY, run_id)
                self._state.update(run.session_id, status="running")
            except SessionNotFoundError:
                pass

        self.record_event(
            run_id,
            "run_resumed",
            {
                "inferred_crash": inferred_crash,
                "worker_id": worker,
                "needs_reconcile": run.needs_reconcile,
            },
            actor="system",
        )
        return ActiveRun(self, self.get_run(run_id))

    # -- events -------------------------------------------------------------

    def record_event(
        self,
        run_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        actor: str = "agent",
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        payload_ref: Optional[str] = None,
    ) -> RunEvent:
        if not is_valid_run_event_type(event_type):
            raise RunEventError(f"Invalid event type: {event_type!r}")

        with self._lock:
            run = self.get_run(run_id)
            # Idempotent short-circuit under lock (avoids seq gaps on dup keys)
            payload_dict = dict(payload or {})
            if idempotency_key:
                from .exceptions import IdempotencyConflictError

                existing = self._store.get_event_by_idempotency(
                    run_id, idempotency_key
                )
                if existing is not None:
                    if existing.type != event_type or existing.payload != payload_dict:
                        raise IdempotencyConflictError(run_id, idempotency_key)
                    return existing
            seq = self._store.next_sequence(run_id)
            event = RunEvent(
                event_id=_new_event_id(),
                run_id=run_id,
                sequence=seq,
                type=event_type,
                actor=actor,
                timestamp=time.time(),
                causation_id=causation_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload=payload_dict,
                payload_ref=payload_ref,
                schema_version=1,
            )
            stored = self._store.append_event(event)

            run = self.get_run(run_id)
            if stored.sequence >= run.last_event_seq:
                run.last_event_seq = stored.sequence
                run.updated_at = time.time()
                self._store.save_run(run)

        # Optional live projection for state_mutation (outside seq lock)
        if (
            stored.type == "state_mutation"
            and self._state is not None
            and stored.event_id == event.event_id
        ):
            path = (stored.payload or {}).get("path")
            value = (stored.payload or {}).get("value")
            if path == "step" and isinstance(value, int):
                try:
                    self._state.update(run.session_id, step=value)
                except SessionNotFoundError:
                    pass
            elif path == "status" and isinstance(value, str):
                try:
                    self._state.update(run.session_id, status=value)
                except SessionNotFoundError:
                    pass

        return stored

    def list_events(
        self,
        run_id: str,
        *,
        from_seq: Optional[int] = None,
        to_seq: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[RunEvent]:
        self.get_run(run_id)  # existence check
        return self._store.list_events(
            run_id, from_seq=from_seq, to_seq=to_seq, limit=limit
        )

    # -- checkpoint dual-write ----------------------------------------------

    def checkpoint_run(self, run_id: str) -> str:
        if self._state is None:
            raise RunEventError("checkpoint_run requires a StateOS instance")
        run = self.get_run(run_id)
        chk_id = self._state.checkpoint(run.session_id)
        self.record_event(
            run_id,
            "checkpoint",
            {"checkpoint_id": chk_id},
            actor="system",
        )
        run = self.get_run(run_id)
        run.last_checkpoint_id = chk_id
        run.updated_at = time.time()
        self._store.save_run(run)
        return chk_id

    def heartbeat(self, run_id: str, worker_id: Optional[str] = None) -> Run:
        run = self.get_run(run_id)
        now = time.time()
        if worker_id and run.lease_owner and worker_id != run.lease_owner:
            raise RunEventError(
                f"Lease held by {run.lease_owner!r}, not {worker_id!r}"
            )
        run.lease_until = now + (run.heartbeat_ms / 1000.0)
        if worker_id:
            run.lease_owner = worker_id
        run.updated_at = now
        self._store.save_run(run)
        return run

    def complete_run(
        self, run_id: str, payload: Optional[Dict[str, Any]] = None
    ) -> Run:
        self.record_event(
            run_id, "run_completed", payload or {}, actor="system"
        )
        run = self.get_run(run_id)
        run.status = "done"
        run.lease_until = None
        run.updated_at = time.time()
        self._store.save_run(run)
        if self._state is not None:
            try:
                self._state.mark_done(run.session_id)
            except SessionNotFoundError:
                pass
        return run

    def fail_run(self, run_id: str, reason: str = "") -> Run:
        self.record_event(
            run_id,
            "observation",
            {"kind": "run_failed", "reason": reason},
            actor="system",
        )
        run = self.get_run(run_id)
        run.status = "failed"
        run.lease_until = None
        run.updated_at = time.time()
        self._store.save_run(run)
        if self._state is not None:
            try:
                self._state.mark_failed(run.session_id)
            except SessionNotFoundError:
                pass
        return run

    def declare_crash(self, run_id: str, reason: str = "") -> Run:
        self.record_event(
            run_id, "run_crashed", {"reason": reason, "kind": "declared"}, actor="system"
        )
        run = self.get_run(run_id)
        run.status = "crashed"
        run.lease_until = None
        run.updated_at = time.time()
        self._store.save_run(run)
        return run

    def pause_run(self, run_id: str) -> Run:
        run = self.get_run(run_id)
        run.status = "paused"
        run.updated_at = time.time()
        self._store.save_run(run)
        if self._state is not None:
            try:
                self._state.update(run.session_id, status="paused")
            except SessionNotFoundError:
                pass
        return run

    # -- Mode C restore -----------------------------------------------------

    def restore_to_seq(self, run_id: str, seq: int) -> StatePayload:
        if self._state is None:
            raise RunEventError("restore_to_seq requires a StateOS instance")
        run = self.get_run(run_id)
        events = self._store.list_events(run_id, to_seq=seq)
        # Find latest checkpoint event at or before seq
        ck_id: Optional[str] = None
        for e in reversed(events):
            if e.type == "checkpoint":
                ck_id = (e.payload or {}).get("checkpoint_id")
                break
        if ck_id is None:
            # Fall back to latest StateOS checkpoint for the session
            chks = self._state.list_checkpoints(run.session_id)
            if not chks:
                raise CheckpointNotFoundError(
                    f"no checkpoint at or before seq {seq} for run {run_id}"
                )
            ck_id = chks[-1].id
        return self._state.resume(ck_id)

    # -- fork ---------------------------------------------------------------

    def fork_run(
        self,
        parent_run_id: str,
        *,
        checkpoint_id: Optional[str] = None,
        label: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> ActiveRun:
        parent = self.get_run(parent_run_id)
        if self._state is None:
            raise RunEventError("fork_run requires a StateOS instance")

        if checkpoint_id is None:
            checkpoint_id = parent.last_checkpoint_id
            if checkpoint_id is None:
                chks = self._state.list_checkpoints(parent.session_id)
                if not chks:
                    raise CheckpointNotFoundError(
                        "no checkpoint available to fork from"
                    )
                checkpoint_id = chks[-1].id

        chk = self._state._backend.get_checkpoint(checkpoint_id)
        if chk is None:
            raise CheckpointNotFoundError(checkpoint_id)

        # Fork sequence = sequence of matching checkpoint event, else last_event_seq
        fork_seq = parent.last_event_seq
        for e in self._store.list_events(parent_run_id):
            if (
                e.type == "checkpoint"
                and (e.payload or {}).get("checkpoint_id") == checkpoint_id
            ):
                fork_seq = e.sequence

        # Restore parent session to checkpoint, then fork session via StateOS snapshot
        self._state.resume(checkpoint_id)
        snap = self._state.snapshot(
            parent.session_id, label=label or f"fork-from-{checkpoint_id}"
        )
        child_session = self._state.fork(snap.id)

        now = time.time()
        worker = worker_id or _new_worker_id()
        child = Run(
            run_id=_new_run_id(),
            session_id=child_session,
            namespace=parent.namespace,
            agent_id=parent.agent_id,
            status="running",
            parent_run_id=parent.run_id,
            fork_checkpoint_id=checkpoint_id,
            fork_seq=fork_seq,
            label=label,
            goal=parent.goal,
            lease_owner=worker,
            lease_until=now + (parent.heartbeat_ms / 1000.0),
            heartbeat_ms=parent.heartbeat_ms,
            last_checkpoint_id=checkpoint_id,
            created_at=now,
            updated_at=now,
        )
        self._store.save_run(child)

        child_payload = StatePayload.from_dict(chk.payload.to_dict())
        child_payload.session_id = child_session
        child_payload.workflow_state = {
            **(chk.payload.workflow_state or {}),
            _ACTIVE_RUN_KEY: child.run_id,
        }
        child_payload.updated_at = now
        self._state.save(child_session, child_payload)

        self.record_event(
            child.run_id,
            "fork_created",
            {
                "parent_run_id": parent.run_id,
                "fork_checkpoint_id": checkpoint_id,
                "fork_seq": fork_seq,
                "label": label,
            },
            actor="system",
        )
        self.record_event(
            parent.run_id,
            "observation",
            {
                "kind": "fork_spawned",
                "child_run_id": child.run_id,
                "fork_checkpoint_id": checkpoint_id,
            },
            actor="system",
        )
        return ActiveRun(self, self.get_run(child.run_id))
