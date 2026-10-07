"""Durable Run / RunEvent storage — OMem v1 history SoT.

Lives alongside StateOS tables (same SQLite file when using SQLiteRunStore).
Does **not** replace StatePayload / checkpoints (live SoT for Mode A resume).

See: yc-w27-materials/OMEM_V1_ENGINEERING_SPEC.md §0A.1, §8
"""

from __future__ import annotations

import copy
import json
import logging
import sqlite3
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from ..core.utils.retry import retry_with_backoff
from ..types import Run, RunEvent

logger = logging.getLogger(__name__)

_RUNS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT    PRIMARY KEY,
    session_id          TEXT    NOT NULL,
    namespace           TEXT    NOT NULL DEFAULT 'default',
    agent_id            TEXT,
    status              TEXT    NOT NULL DEFAULT 'running',
    parent_run_id       TEXT,
    fork_checkpoint_id  TEXT,
    fork_seq            INTEGER,
    label               TEXT,
    goal                TEXT,
    lease_owner         TEXT,
    lease_until         REAL,
    heartbeat_ms        INTEGER NOT NULL DEFAULT 30000,
    needs_reconcile     INTEGER NOT NULL DEFAULT 0,
    last_checkpoint_id  TEXT,
    last_event_seq      INTEGER NOT NULL DEFAULT 0,
    created_at          REAL    NOT NULL,
    updated_at          REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created_at);

CREATE TABLE IF NOT EXISTS run_events (
    event_id         TEXT    PRIMARY KEY,
    run_id           TEXT    NOT NULL,
    sequence         INTEGER NOT NULL,
    type             TEXT    NOT NULL,
    actor            TEXT    NOT NULL DEFAULT 'agent',
    timestamp        REAL    NOT NULL,
    causation_id     TEXT,
    correlation_id   TEXT,
    idempotency_key  TEXT,
    payload_json     TEXT    NOT NULL,
    payload_ref      TEXT,
    schema_version   INTEGER NOT NULL DEFAULT 1,
    UNIQUE(run_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, sequence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_run_events_idem
    ON run_events(run_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
"""


class RunStore(ABC):
    """Abstract persistence for runs and append-only run_events."""

    @abstractmethod
    def save_run(self, run: Run) -> None:
        ...

    @abstractmethod
    def get_run(self, run_id: str) -> Optional[Run]:
        ...

    @abstractmethod
    def list_runs(self, session_id: str, namespace: Optional[str] = None) -> List[Run]:
        ...

    @abstractmethod
    def append_event(self, event: RunEvent) -> RunEvent:
        """Insert event. On idempotency hit, return the existing event.

        Raises IdempotencyConflictError if key reused with different payload.
        """

    @abstractmethod
    def get_event_by_idempotency(
        self, run_id: str, idempotency_key: str
    ) -> Optional[RunEvent]:
        ...

    @abstractmethod
    def list_events(
        self,
        run_id: str,
        *,
        from_seq: Optional[int] = None,
        to_seq: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[RunEvent]:
        ...

    @abstractmethod
    def next_sequence(self, run_id: str) -> int:
        """Return the next sequence number (max+1, or 1 if empty)."""


class InMemoryRunStore(RunStore):
    """Thread-safe in-memory run store (tests / ephemeral)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: Dict[str, Run] = {}
        self._events: Dict[str, List[RunEvent]] = {}  # run_id → ordered
        self._idem: Dict[Tuple[str, str], str] = {}  # (run_id, key) → event_id

    def save_run(self, run: Run) -> None:
        with self._lock:
            self._runs[run.run_id] = copy.deepcopy(run)

    def get_run(self, run_id: str) -> Optional[Run]:
        with self._lock:
            r = self._runs.get(run_id)
            return copy.deepcopy(r) if r else None

    def list_runs(self, session_id: str, namespace: Optional[str] = None) -> List[Run]:
        with self._lock:
            out = []
            for r in self._runs.values():
                if r.session_id != session_id:
                    continue
                if namespace is not None and r.namespace != namespace:
                    continue
                out.append(copy.deepcopy(r))
            out.sort(key=lambda x: x.created_at)
            return out

    def next_sequence(self, run_id: str) -> int:
        with self._lock:
            evs = self._events.get(run_id, [])
            if not evs:
                return 1
            return max(e.sequence for e in evs) + 1

    def get_event_by_idempotency(
        self, run_id: str, idempotency_key: str
    ) -> Optional[RunEvent]:
        with self._lock:
            eid = self._idem.get((run_id, idempotency_key))
            if not eid:
                return None
            for e in self._events.get(run_id, []):
                if e.event_id == eid:
                    return copy.deepcopy(e)
            return None

    def append_event(self, event: RunEvent) -> RunEvent:
        from .exceptions import IdempotencyConflictError

        with self._lock:
            if event.idempotency_key:
                eid = self._idem.get((event.run_id, event.idempotency_key))
                if eid:
                    for e in self._events.get(event.run_id, []):
                        if e.event_id == eid:
                            if e.type != event.type or e.payload != event.payload:
                                raise IdempotencyConflictError(
                                    event.run_id, event.idempotency_key
                                )
                            return copy.deepcopy(e)

            self._events.setdefault(event.run_id, [])
            for e in self._events[event.run_id]:
                if e.sequence == event.sequence:
                    raise ValueError(
                        f"Duplicate sequence {event.sequence} on run {event.run_id}"
                    )
            stored = copy.deepcopy(event)
            self._events[event.run_id].append(stored)
            self._events[event.run_id].sort(key=lambda x: x.sequence)
            if event.idempotency_key:
                self._idem[(event.run_id, event.idempotency_key)] = event.event_id
            return copy.deepcopy(stored)

    def list_events(
        self,
        run_id: str,
        *,
        from_seq: Optional[int] = None,
        to_seq: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[RunEvent]:
        with self._lock:
            evs = list(self._events.get(run_id, []))
            if from_seq is not None:
                evs = [e for e in evs if e.sequence >= from_seq]
            if to_seq is not None:
                evs = [e for e in evs if e.sequence <= to_seq]
            if limit is not None:
                evs = evs[:limit]
            return [copy.deepcopy(e) for e in evs]


class SQLiteRunStore(RunStore):
    """File-backed run store (same DB as StateOS when paths match)."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self._conn.executescript(_RUNS_SCHEMA_SQL)
            self._conn.commit()

    def _exec(self, sql: str, params: tuple = (), operation: str = "sql") -> sqlite3.Cursor:
        def _do():
            with self._lock:
                cur = self._conn.execute(sql, params)
                self._conn.commit()
                return cur

        return retry_with_backoff(
            _do,
            retryable_exceptions=(sqlite3.OperationalError,),
            operation_name=f"run_store.{operation}",
        )

    def _query(self, sql: str, params: tuple = ()) -> list:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def save_run(self, run: Run) -> None:
        self._exec(
            """INSERT INTO runs (
                   run_id, session_id, namespace, agent_id, status,
                   parent_run_id, fork_checkpoint_id, fork_seq, label, goal,
                   lease_owner, lease_until, heartbeat_ms, needs_reconcile,
                   last_checkpoint_id, last_event_seq, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(run_id) DO UPDATE SET
                   session_id = excluded.session_id,
                   namespace = excluded.namespace,
                   agent_id = excluded.agent_id,
                   status = excluded.status,
                   parent_run_id = excluded.parent_run_id,
                   fork_checkpoint_id = excluded.fork_checkpoint_id,
                   fork_seq = excluded.fork_seq,
                   label = excluded.label,
                   goal = excluded.goal,
                   lease_owner = excluded.lease_owner,
                   lease_until = excluded.lease_until,
                   heartbeat_ms = excluded.heartbeat_ms,
                   needs_reconcile = excluded.needs_reconcile,
                   last_checkpoint_id = excluded.last_checkpoint_id,
                   last_event_seq = excluded.last_event_seq,
                   updated_at = excluded.updated_at
            """,
            (
                run.run_id,
                run.session_id,
                run.namespace,
                run.agent_id,
                run.status,
                run.parent_run_id,
                run.fork_checkpoint_id,
                run.fork_seq,
                run.label,
                run.goal,
                run.lease_owner,
                run.lease_until,
                run.heartbeat_ms,
                1 if run.needs_reconcile else 0,
                run.last_checkpoint_id,
                run.last_event_seq,
                run.created_at,
                run.updated_at,
            ),
            "save_run",
        )

    def get_run(self, run_id: str) -> Optional[Run]:
        rows = self._query("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        if not rows:
            return None
        return self._row_to_run(rows[0])

    def list_runs(self, session_id: str, namespace: Optional[str] = None) -> List[Run]:
        if namespace is None:
            rows = self._query(
                "SELECT * FROM runs WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
        else:
            rows = self._query(
                "SELECT * FROM runs WHERE session_id = ? AND namespace = ? "
                "ORDER BY created_at ASC",
                (session_id, namespace),
            )
        return [self._row_to_run(r) for r in rows]

    def _row_to_run(self, row: sqlite3.Row) -> Run:
        d = dict(row)
        return Run(
            run_id=d["run_id"],
            session_id=d["session_id"],
            namespace=d.get("namespace") or "default",
            agent_id=d.get("agent_id"),
            status=d.get("status") or "running",
            parent_run_id=d.get("parent_run_id"),
            fork_checkpoint_id=d.get("fork_checkpoint_id"),
            fork_seq=d.get("fork_seq"),
            label=d.get("label"),
            goal=d.get("goal"),
            lease_owner=d.get("lease_owner"),
            lease_until=d.get("lease_until"),
            heartbeat_ms=int(d.get("heartbeat_ms") or 30000),
            needs_reconcile=bool(d.get("needs_reconcile")),
            last_checkpoint_id=d.get("last_checkpoint_id"),
            last_event_seq=int(d.get("last_event_seq") or 0),
            created_at=float(d["created_at"]),
            updated_at=float(d["updated_at"]),
        )

    def next_sequence(self, run_id: str) -> int:
        rows = self._query(
            "SELECT COALESCE(MAX(sequence), 0) FROM run_events WHERE run_id = ?",
            (run_id,),
        )
        return int(rows[0][0]) + 1

    def get_event_by_idempotency(
        self, run_id: str, idempotency_key: str
    ) -> Optional[RunEvent]:
        rows = self._query(
            "SELECT * FROM run_events WHERE run_id = ? AND idempotency_key = ?",
            (run_id, idempotency_key),
        )
        if not rows:
            return None
        return self._row_to_event(rows[0])

    def append_event(self, event: RunEvent) -> RunEvent:
        from .exceptions import IdempotencyConflictError

        if event.idempotency_key:
            existing = self.get_event_by_idempotency(event.run_id, event.idempotency_key)
            if existing is not None:
                if existing.type != event.type or existing.payload != event.payload:
                    raise IdempotencyConflictError(event.run_id, event.idempotency_key)
                return existing

        payload_json = json.dumps(event.payload, default=str)
        try:
            self._exec(
                """INSERT INTO run_events (
                       event_id, run_id, sequence, type, actor, timestamp,
                       causation_id, correlation_id, idempotency_key,
                       payload_json, payload_ref, schema_version
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.run_id,
                    event.sequence,
                    event.type,
                    event.actor,
                    event.timestamp,
                    event.causation_id,
                    event.correlation_id,
                    event.idempotency_key,
                    payload_json,
                    event.payload_ref,
                    event.schema_version,
                ),
                "append_event",
            )
        except sqlite3.IntegrityError:
            # Race on idempotency unique index
            if event.idempotency_key:
                existing = self.get_event_by_idempotency(
                    event.run_id, event.idempotency_key
                )
                if existing is not None:
                    if existing.type != event.type or existing.payload != event.payload:
                        raise IdempotencyConflictError(
                            event.run_id, event.idempotency_key
                        )
                    return existing
            raise
        return event

    def list_events(
        self,
        run_id: str,
        *,
        from_seq: Optional[int] = None,
        to_seq: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[RunEvent]:
        sql = "SELECT * FROM run_events WHERE run_id = ?"
        params: list = [run_id]
        if from_seq is not None:
            sql += " AND sequence >= ?"
            params.append(from_seq)
        if to_seq is not None:
            sql += " AND sequence <= ?"
            params.append(to_seq)
        sql += " ORDER BY sequence ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._query(sql, tuple(params))
        return [self._row_to_event(r) for r in rows]

    def _row_to_event(self, row: sqlite3.Row) -> RunEvent:
        d = dict(row)
        return RunEvent(
            event_id=d["event_id"],
            run_id=d["run_id"],
            sequence=int(d["sequence"]),
            type=d["type"],
            actor=d.get("actor") or "agent",
            timestamp=float(d["timestamp"]),
            causation_id=d.get("causation_id"),
            correlation_id=d.get("correlation_id"),
            idempotency_key=d.get("idempotency_key"),
            payload=json.loads(d["payload_json"] or "{}"),
            payload_ref=d.get("payload_ref"),
            schema_version=int(d.get("schema_version") or 1),
        )

    def close(self) -> None:
        self._conn.close()
