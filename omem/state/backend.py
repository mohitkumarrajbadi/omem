"""State storage backend — abstract interface + concrete implementations.

Two backends ship with Phase 2:
    InMemoryStateBackend — zero-config, for tests and fast local dev
    SQLiteStateBackend   — production default, same DB file as memories

The Postgres backend will be added in Cloud Phase C2 when the managed
service needs multi-tenant isolation.

Design rules:
    - All writes are atomic (single SQLite transaction or dict update)
    - All reads return copies (no mutable references to internal storage)
    - Backends are thread-safe via an internal lock
    - Retry logic mirrors the pattern in omem/backends/sqlite.py
"""

import copy
import json
import logging
import sqlite3
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from ..core.utils.retry import retry_with_backoff
from ..types import StateCheckpoint, StatePayload, StateSnapshot

logger = logging.getLogger(__name__)


class StateBackend(ABC):
    """Abstract persistence interface for the state layer."""

    # Sessions

    @abstractmethod
    def save_session(self, payload: StatePayload) -> None:
        """Upsert a session (create or replace)."""

    @abstractmethod
    def load_session(self, session_id: str) -> Optional[StatePayload]:
        """Return the live StatePayload for a session, or None."""

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """Delete session record. Returns True if it existed."""

    @abstractmethod
    def list_sessions(self, namespace: Optional[str] = None) -> List[str]:
        """Return all session IDs, optionally filtered by namespace."""

    # Snapshots

    @abstractmethod
    def save_snapshot(self, snapshot: StateSnapshot) -> None:
        """Append a snapshot (snapshots are immutable; never overwrite)."""

    @abstractmethod
    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        """Return a snapshot by ID, or None."""

    @abstractmethod
    def list_snapshots(self, session_id: str) -> List[StateSnapshot]:
        """Return all snapshots for a session, oldest first."""

    # Checkpoints

    @abstractmethod
    def save_checkpoint(self, checkpoint: StateCheckpoint) -> None:
        """Store a crash-recovery checkpoint."""

    @abstractmethod
    def get_checkpoint(self, checkpoint_id: str) -> Optional[StateCheckpoint]:
        """Return a checkpoint by ID, or None."""

    @abstractmethod
    def list_checkpoints(self, session_id: str) -> List[StateCheckpoint]:
        """Return all checkpoints for a session, oldest first."""

    # Fork lineage

    @abstractmethod
    def save_fork(
        self,
        child_session_id: str,
        parent_snapshot_id: str,
        forked_at: float,
    ) -> None:
        """Record a fork relationship."""

    @abstractmethod
    def mark_merged(self, child_session_id: str, merged_at: float) -> None:
        """Mark a forked session as merged."""

    @abstractmethod
    def get_fork_parent(self, child_session_id: str) -> Optional[str]:
        """Return the parent snapshot ID for a forked session, or None."""


# ---------------------------------------------------------------------------
# In-memory backend (tests + fast local dev)
# ---------------------------------------------------------------------------


class InMemoryStateBackend(StateBackend):
    """Thread-safe in-memory state backend.

    All data is lost when the process exits. Ideal for unit tests and
    interactive exploration — no I/O, no setup required.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, StatePayload] = {}
        self._snapshots: Dict[str, StateSnapshot] = {}
        self._checkpoints: Dict[str, StateCheckpoint] = {}
        # session_id → list of snapshot IDs (append-only)
        self._session_snapshots: Dict[str, List[str]] = {}
        # session_id → list of checkpoint IDs
        self._session_checkpoints: Dict[str, List[str]] = {}
        # child_session_id → (parent_snapshot_id, forked_at, merged_at | None)
        self._fork_lineage: Dict[str, Dict] = {}

    # Sessions

    def save_session(self, payload: StatePayload) -> None:
        with self._lock:
            self._sessions[payload.session_id] = copy.deepcopy(payload)

    def load_session(self, session_id: str) -> Optional[StatePayload]:
        with self._lock:
            p = self._sessions.get(session_id)
            return copy.deepcopy(p) if p is not None else None

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def list_sessions(self, namespace: Optional[str] = None) -> List[str]:
        with self._lock:
            if namespace is None:
                return list(self._sessions.keys())
            return [
                sid for sid, p in self._sessions.items()
                if p.namespace == namespace
            ]

    # Snapshots

    def save_snapshot(self, snapshot: StateSnapshot) -> None:
        with self._lock:
            self._snapshots[snapshot.id] = copy.deepcopy(snapshot)
            self._session_snapshots.setdefault(snapshot.session_id, [])
            if snapshot.id not in self._session_snapshots[snapshot.session_id]:
                self._session_snapshots[snapshot.session_id].append(snapshot.id)

    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        with self._lock:
            s = self._snapshots.get(snapshot_id)
            return copy.deepcopy(s) if s is not None else None

    def list_snapshots(self, session_id: str) -> List[StateSnapshot]:
        with self._lock:
            ids = self._session_snapshots.get(session_id, [])
            return [
                copy.deepcopy(self._snapshots[i])
                for i in ids
                if i in self._snapshots
            ]

    # Checkpoints

    def save_checkpoint(self, checkpoint: StateCheckpoint) -> None:
        with self._lock:
            self._checkpoints[checkpoint.id] = copy.deepcopy(checkpoint)
            self._session_checkpoints.setdefault(checkpoint.session_id, [])
            self._session_checkpoints[checkpoint.session_id].append(checkpoint.id)

    def get_checkpoint(self, checkpoint_id: str) -> Optional[StateCheckpoint]:
        with self._lock:
            c = self._checkpoints.get(checkpoint_id)
            return copy.deepcopy(c) if c is not None else None

    def list_checkpoints(self, session_id: str) -> List[StateCheckpoint]:
        with self._lock:
            ids = self._session_checkpoints.get(session_id, [])
            return [
                copy.deepcopy(self._checkpoints[i])
                for i in ids
                if i in self._checkpoints
            ]

    # Fork lineage

    def save_fork(
        self,
        child_session_id: str,
        parent_snapshot_id: str,
        forked_at: float,
    ) -> None:
        with self._lock:
            self._fork_lineage[child_session_id] = {
                "parent_snapshot_id": parent_snapshot_id,
                "forked_at": forked_at,
                "merged_at": None,
                "status": "active",
            }

    def mark_merged(self, child_session_id: str, merged_at: float) -> None:
        with self._lock:
            if child_session_id in self._fork_lineage:
                self._fork_lineage[child_session_id]["merged_at"] = merged_at
                self._fork_lineage[child_session_id]["status"] = "merged"

    def get_fork_parent(self, child_session_id: str) -> Optional[str]:
        with self._lock:
            entry = self._fork_lineage.get(child_session_id)
            return entry["parent_snapshot_id"] if entry else None


# ---------------------------------------------------------------------------
# SQLite backend (production default)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS state_sessions (
    session_id   TEXT    PRIMARY KEY,
    namespace    TEXT    NOT NULL DEFAULT 'default',
    payload_json TEXT    NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    updated_at   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS state_snapshots (
    id           TEXT    PRIMARY KEY,
    session_id   TEXT    NOT NULL,
    parent_id    TEXT,
    label        TEXT,
    payload_json TEXT    NOT NULL,
    memory_ref   TEXT,
    created_at   REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_session ON state_snapshots(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_snap_parent  ON state_snapshots(parent_id);

CREATE TABLE IF NOT EXISTS state_checkpoints (
    id           TEXT    PRIMARY KEY,
    session_id   TEXT    NOT NULL,
    payload_hash TEXT    NOT NULL,
    payload_json TEXT    NOT NULL,
    created_at   REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chk_session ON state_checkpoints(session_id, created_at);

CREATE TABLE IF NOT EXISTS state_fork_lineage (
    child_session_id   TEXT    PRIMARY KEY,
    parent_snapshot_id TEXT    NOT NULL,
    forked_at          REAL    NOT NULL,
    merged_at          REAL,
    status             TEXT    NOT NULL DEFAULT 'active'
);
"""


class SQLiteStateBackend(StateBackend):
    """Durable state backend backed by SQLite.

    Uses the same database file as ``SQLiteBackend`` for memory, so
    state + memory live together. WAL mode allows concurrent reads
    from the memory engine without blocking state writes.

    Args:
        db_path: Path to the ``.db`` file, or ``":memory:"`` for tests.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-32000")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._migrate()

    def _migrate(self) -> None:
        """Create tables if they don't exist (idempotent)."""
        with self._lock:
            for stmt in _SCHEMA_SQL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    self._conn.execute(stmt)
            self._conn.commit()

    def _exec(self, sql: str, params: tuple = (), operation: str = "sql") -> sqlite3.Cursor:
        """Execute with retry on transient lock contention."""
        def _do():
            with self._lock:
                cur = self._conn.execute(sql, params)
                self._conn.commit()
                return cur
        return retry_with_backoff(
            _do,
            retryable_exceptions=(sqlite3.OperationalError,),
            operation_name=f"state.{operation}",
        )

    def _query(self, sql: str, params: tuple = ()) -> list:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # Sessions

    def save_session(self, payload: StatePayload) -> None:
        j = json.dumps(payload.to_dict(), default=str)
        self._exec(
            """INSERT INTO state_sessions (session_id, namespace, payload_json, version, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   namespace    = excluded.namespace,
                   payload_json = excluded.payload_json,
                   version      = state_sessions.version + 1,
                   updated_at   = excluded.updated_at""",
            (payload.session_id, payload.namespace, j, payload.version, payload.updated_at),
            "save_session",
        )

    def load_session(self, session_id: str) -> Optional[StatePayload]:
        rows = self._query(
            "SELECT payload_json FROM state_sessions WHERE session_id = ?",
            (session_id,),
        )
        if not rows:
            return None
        return StatePayload.from_dict(json.loads(rows[0][0]))

    def delete_session(self, session_id: str) -> bool:
        cur = self._exec(
            "DELETE FROM state_sessions WHERE session_id = ?",
            (session_id,),
            "delete_session",
        )
        return cur.rowcount > 0

    def list_sessions(self, namespace: Optional[str] = None) -> List[str]:
        if namespace:
            rows = self._query(
                "SELECT session_id FROM state_sessions WHERE namespace = ?",
                (namespace,),
            )
        else:
            rows = self._query("SELECT session_id FROM state_sessions")
        return [r[0] for r in rows]

    # Snapshots

    def save_snapshot(self, snapshot: StateSnapshot) -> None:
        j = json.dumps(snapshot.payload.to_dict(), default=str)
        self._exec(
            """INSERT OR IGNORE INTO state_snapshots
               (id, session_id, parent_id, label, payload_json, memory_ref, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.id, snapshot.session_id, snapshot.parent_id,
                snapshot.label, j, snapshot.memory_snapshot_ref, snapshot.created_at,
            ),
            "save_snapshot",
        )

    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        rows = self._query(
            "SELECT id, session_id, parent_id, label, payload_json, memory_ref, created_at "
            "FROM state_snapshots WHERE id = ?",
            (snapshot_id,),
        )
        if not rows:
            return None
        return self._row_to_snapshot(rows[0])

    def list_snapshots(self, session_id: str) -> List[StateSnapshot]:
        rows = self._query(
            "SELECT id, session_id, parent_id, label, payload_json, memory_ref, created_at "
            "FROM state_snapshots WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        return [self._row_to_snapshot(r) for r in rows]

    def _row_to_snapshot(self, row: tuple) -> StateSnapshot:
        sid, session_id, parent_id, label, payload_json, memory_ref, created_at = row
        return StateSnapshot(
            id=sid,
            session_id=session_id,
            payload=StatePayload.from_dict(json.loads(payload_json)),
            label=label,
            parent_id=parent_id,
            memory_snapshot_ref=memory_ref,
            created_at=created_at,
        )

    # Checkpoints

    def save_checkpoint(self, checkpoint: StateCheckpoint) -> None:
        j = json.dumps(checkpoint.payload.to_dict(), default=str)
        self._exec(
            """INSERT OR IGNORE INTO state_checkpoints
               (id, session_id, payload_hash, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                checkpoint.id, checkpoint.session_id,
                checkpoint.payload_hash, j, checkpoint.created_at,
            ),
            "save_checkpoint",
        )

    def get_checkpoint(self, checkpoint_id: str) -> Optional[StateCheckpoint]:
        rows = self._query(
            "SELECT id, session_id, payload_hash, payload_json, created_at "
            "FROM state_checkpoints WHERE id = ?",
            (checkpoint_id,),
        )
        if not rows:
            return None
        return self._row_to_checkpoint(rows[0])

    def list_checkpoints(self, session_id: str) -> List[StateCheckpoint]:
        rows = self._query(
            "SELECT id, session_id, payload_hash, payload_json, created_at "
            "FROM state_checkpoints WHERE session_id = ? ORDER BY rowid ASC",
            (session_id,),
        )
        return [self._row_to_checkpoint(r) for r in rows]

    def _row_to_checkpoint(self, row: tuple) -> StateCheckpoint:
        cid, session_id, payload_hash, payload_json, created_at = row
        return StateCheckpoint(
            id=cid,
            session_id=session_id,
            payload_hash=payload_hash,
            payload=StatePayload.from_dict(json.loads(payload_json)),
            created_at=created_at,
        )

    # Fork lineage

    def save_fork(
        self,
        child_session_id: str,
        parent_snapshot_id: str,
        forked_at: float,
    ) -> None:
        self._exec(
            """INSERT OR IGNORE INTO state_fork_lineage
               (child_session_id, parent_snapshot_id, forked_at, status)
               VALUES (?, ?, ?, 'active')""",
            (child_session_id, parent_snapshot_id, forked_at),
            "save_fork",
        )

    def mark_merged(self, child_session_id: str, merged_at: float) -> None:
        self._exec(
            """UPDATE state_fork_lineage
               SET merged_at = ?, status = 'merged'
               WHERE child_session_id = ?""",
            (merged_at, child_session_id),
            "mark_merged",
        )

    def get_fork_parent(self, child_session_id: str) -> Optional[str]:
        rows = self._query(
            "SELECT parent_snapshot_id FROM state_fork_lineage WHERE child_session_id = ?",
            (child_session_id,),
        )
        return rows[0][0] if rows else None

    def close(self) -> None:
        self._conn.close()
