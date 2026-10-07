"""SQLite storage backend — the default, zero-config backend."""

import json
import sqlite3
import threading
from typing import List, Optional

import numpy as np

from ..core.utils.retry import retry_with_backoff
from ..types import Memory, MemoryType
from .base import Backend


class CorruptMemoryError(ValueError):
    """A stored row cannot be decoded. Callers must not treat it as a memory."""


def _decode_metadata(memory_id: str, meta_json: Optional[str]) -> dict:
    if not meta_json:
        return {}
    try:
        parsed = json.loads(meta_json)
    except json.JSONDecodeError as exc:
        raise CorruptMemoryError(memory_id) from exc
    if not isinstance(parsed, dict):
        raise CorruptMemoryError(memory_id)
    return parsed


class SQLiteBackend(Backend):
    """Stores memories in a local SQLite database.

    Args:
        db_path: Filesystem path for the ``.db`` file, or ``":memory:"``
                 for a purely in-memory database (default).
    """

    def __init__(self, db_path: str = ":memory:", encryptor=None):
        self.db_path = db_path
        self._enc = encryptor
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        # ── SQLite Turbo Mode (v0.5.0) ──
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA cache_size=-128000")  # 128MB cache
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
        if db_path == ":memory:":
            self._conn.execute("PRAGMA synchronous=OFF")
        else:
            self._conn.execute("PRAGMA synchronous=NORMAL")  # safe + fast with WAL
        self._create_table()

    def _txn(self, fn):
        """Serialize all use of the shared sqlite3 connection (check_same_thread=False)."""
        with self._lock:
            return fn(self._conn)

    def _create_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id              TEXT PRIMARY KEY,
                type            INTEGER NOT NULL,
                content         TEXT    NOT NULL,
                vector          BLOB,
                timestamp       REAL    NOT NULL,
                importance      REAL    DEFAULT 0.5,
                utility_score   REAL    DEFAULT 0.0,
                access_count    INTEGER DEFAULT 0,
                last_accessed   REAL    DEFAULT 0.0,
                namespace       TEXT    DEFAULT 'default',
                source          TEXT    DEFAULT '',
                active          INTEGER DEFAULT 1,
                status          INTEGER DEFAULT 0,
                consensus_score REAL    DEFAULT 0.0,
                logical_hash    TEXT    DEFAULT '',
                metadata        TEXT    DEFAULT '{}',
                score           REAL    DEFAULT 0.0
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(type)")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_ns ON memories(namespace)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_hash ON memories(logical_hash)"
        )
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_edges (
                id              TEXT PRIMARY KEY,
                namespace       TEXT NOT NULL DEFAULT 'default',
                source_id       TEXT NOT NULL,
                target_id       TEXT NOT NULL,
                relation_type   TEXT NOT NULL DEFAULT 'related',
                confidence      REAL DEFAULT 1.0,
                memory_id       TEXT DEFAULT '',
                valid_from      REAL,
                valid_to        REAL,
                active          INTEGER DEFAULT 1,
                created_at      REAL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_ns ON memory_edges(namespace)"
        )
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS provenance_events (
                id            TEXT PRIMARY KEY,
                entity_id     TEXT NOT NULL,
                entity_type   TEXT NOT NULL DEFAULT 'memory',
                operation     TEXT NOT NULL,
                source        TEXT NOT NULL DEFAULT 'agent',
                timestamp     REAL NOT NULL,
                session_id    TEXT DEFAULT '',
                namespace     TEXT DEFAULT 'default',
                confidence    REAL DEFAULT 1.0,
                related_ids   TEXT DEFAULT '[]',
                metadata      TEXT DEFAULT '{}'
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_prov_entity ON provenance_events(entity_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_prov_ns ON provenance_events(namespace, timestamp)"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, memory: Memory) -> None:
        persist_meta = (
            memory.metadata_for_persist()
            if hasattr(memory, "metadata_for_persist")
            else memory.metadata
        )
        content = self._enc.encrypt(memory.content) if self._enc else memory.content
        meta = self._enc.encrypt(json.dumps(persist_meta)) if self._enc else json.dumps(persist_meta)

        def _do():
            def inner(conn):
                conn.execute(
                    """INSERT OR REPLACE INTO memories
                   (id, type, content, vector, timestamp, importance, utility_score, access_count,
                    last_accessed, namespace, source, active, status, consensus_score, logical_hash, metadata, score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        memory.id,
                        memory.type.value,
                        content,
                        memory.vector.tobytes() if memory.vector is not None else None,
                        memory.timestamp,
                        memory.importance,
                        memory.utility_score,
                        memory.access_count,
                        memory.last_accessed,
                        memory.namespace,
                        memory.source,
                        1 if memory.active else 0,
                        memory.status.value,
                        memory.consensus_score,
                        memory.logical_hash,
                        meta,
                        memory.score,
                    ),
                )
                conn.commit()

            self._txn(inner)

        retry_with_backoff(
            _do,
            retryable_exceptions=(sqlite3.OperationalError, sqlite3.ProgrammingError),
            operation_name="sqlite.save",
        )

    def save_batch(self, memories: List[Memory]) -> None:
        if not memories:
            return
        data = [
            (
                m.id,
                m.type.value,
                self._enc.encrypt(m.content) if self._enc else m.content,
                m.vector.tobytes() if m.vector is not None else None,
                m.timestamp,
                m.importance,
                m.utility_score,
                m.access_count,
                m.last_accessed,
                m.namespace,
                m.source,
                1 if m.active else 0,
                m.status.value,
                m.consensus_score,
                m.logical_hash,
                self._enc.encrypt(json.dumps(
                    m.metadata_for_persist() if hasattr(m, "metadata_for_persist") else m.metadata
                )) if self._enc else json.dumps(
                    m.metadata_for_persist() if hasattr(m, "metadata_for_persist") else m.metadata
                ),
                m.score,
            )
            for m in memories
        ]

        def _do():
            def inner(conn):
                conn.executemany(
                    """INSERT OR REPLACE INTO memories
                   (id, type, content, vector, timestamp, importance, utility_score, access_count,
                    last_accessed, namespace, source, active, status, consensus_score, logical_hash, metadata, score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    data,
                )
                conn.commit()

            self._txn(inner)

        retry_with_backoff(
            _do,
            retryable_exceptions=(sqlite3.OperationalError, sqlite3.ProgrammingError),
            operation_name="sqlite.save_batch",
        )

    def load(self, memory_id: str) -> Optional[Memory]:
        row = self._txn(
            lambda c: c.execute(
                "SELECT * FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        )
        if row is None:
            return None
        return self._row_to_memory(row)  # raises CorruptMemoryError; do not return the row

    def search(self, query: str, limit: int = 10) -> List[Memory]:
        # Encrypted content cannot be matched via SQL LIKE — decrypt then filter.
        if self._enc:
            needle = query.lower()
            hits: List[Memory] = []
            rows = self._txn(lambda c: c.execute("SELECT * FROM memories").fetchall())
            for row in rows:
                try:
                    mem = self._row_to_memory(row)
                except CorruptMemoryError:
                    continue
                if needle in mem.content.lower():
                    hits.append(mem)
                    if len(hits) >= limit:
                        break
            return hits
        rows = self._txn(
            lambda c: c.execute(
                "SELECT * FROM memories WHERE content LIKE ? LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        )
        loaded: List[Memory] = []
        for row in rows:
            try:
                loaded.append(self._row_to_memory(row))
            except CorruptMemoryError:
                continue
        return loaded

    def all(self) -> List[Memory]:
        rows = self._txn(lambda c: c.execute("SELECT * FROM memories").fetchall())
        loaded: List[Memory] = []
        for row in rows:
            try:
                loaded.append(self._row_to_memory(row))
            except CorruptMemoryError:
                continue
        return loaded

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_memory(self, row: tuple) -> Memory:
        # Columns: id, type, content, vector, timestamp, importance, utility_score,
        #          access_count, last_accessed, namespace, source, active, status,
        #          consensus_score, logical_hash, metadata, score
        from ..types import MemoryStatus

        (
            mid, mtype, content, vec_bytes, ts, imp, util, count, last,
            ns, src, active, status, consensus, lhash, meta_json, score,
        ) = row

        if self._enc:
            content = self._enc.decrypt(content)
            meta_json = self._enc.decrypt(meta_json)

        vector = (
            np.frombuffer(vec_bytes, dtype=np.float32).copy()
            if vec_bytes
            else np.zeros(384, dtype=np.float32)
        )
        mem = Memory(
            id=mid,
            type=MemoryType(mtype),
            content=content,
            vector=vector,
            timestamp=ts,
            importance=imp,
            utility_score=util,
            access_count=count,
            last_accessed=last,
            namespace=ns,
            source=src,
            active=bool(active),
            status=MemoryStatus(status),
            consensus_score=consensus,
            logical_hash=lhash,
            metadata=_decode_metadata(mid, meta_json),
            score=score,
        )
        return mem.hydrate_runtime_fields()

    def delete(self, memory_id: str) -> bool:
        def inner(conn):
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

        return self._txn(inner)

    def clear(self) -> None:
        def inner(conn):
            conn.execute("DELETE FROM memories")
            conn.execute("DELETE FROM memory_edges")
            conn.execute("DELETE FROM provenance_events")
            conn.commit()

        self._txn(inner)

    # ------------------------------------------------------------------
    # Knowledge graph edges
    # ------------------------------------------------------------------

    def save_edge(
        self,
        namespace: str,
        source_id: str,
        target_id: str,
        relation_type: str = "related",
        confidence: float = 1.0,
        edge_id: Optional[str] = None,
        memory_id: str = "",
        valid_from: Optional[float] = None,
        valid_to: Optional[float] = None,
    ) -> str:
        import time as _time
        import uuid as _uuid

        eid = edge_id or _uuid.uuid4().hex[:32]

        def _do():
            def inner(conn):
                conn.execute(
                    """INSERT OR REPLACE INTO memory_edges
                   (id, namespace, source_id, target_id, relation_type, confidence,
                    memory_id, valid_from, valid_to, active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                    (
                        eid,
                        namespace or "default",
                        source_id,
                        target_id,
                        relation_type,
                        float(confidence),
                        memory_id or "",
                        valid_from,
                        valid_to,
                        _time.time(),
                    ),
                )
                conn.commit()

            self._txn(inner)

        retry_with_backoff(
            _do,
            retryable_exceptions=(sqlite3.OperationalError, sqlite3.ProgrammingError),
            operation_name="sqlite.save_edge",
        )
        return eid

    def load_edges(self, namespace: Optional[str] = None) -> List[dict]:
        if namespace:
            rows = self._txn(
                lambda c: c.execute(
                    "SELECT * FROM memory_edges WHERE active = 1 AND namespace = ?",
                    (namespace,),
                ).fetchall()
            )
        else:
            rows = self._txn(
                lambda c: c.execute(
                    "SELECT * FROM memory_edges WHERE active = 1"
                ).fetchall()
            )
        cols = [
            "id", "namespace", "source_id", "target_id", "relation_type",
            "confidence", "memory_id", "valid_from", "valid_to", "active",
            "created_at",
        ]
        out = []
        for row in rows:
            rec = dict(zip(cols, row))
            rec["active"] = bool(rec["active"])
            out.append(rec)
        return out

    # ------------------------------------------------------------------
    # Provenance WAL
    # ------------------------------------------------------------------

    def save_provenance_event(self, event: dict) -> None:
        def _do():
            def inner(conn):
                conn.execute(
                    """INSERT OR REPLACE INTO provenance_events
                   (id, entity_id, entity_type, operation, source, timestamp,
                    session_id, namespace, confidence, related_ids, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.get("id", ""),
                        event.get("entity_id", ""),
                        event.get("entity_type", "memory"),
                        event.get("operation", "create"),
                        event.get("source", "agent"),
                        float(event.get("timestamp") or 0.0),
                        event.get("session_id", ""),
                        event.get("namespace", "default"),
                        float(event.get("confidence") or 1.0),
                        json.dumps(event.get("related_ids") or []),
                        json.dumps(event.get("metadata") or {}),
                    ),
                )
                conn.commit()

            self._txn(inner)

        retry_with_backoff(
            _do,
            retryable_exceptions=(sqlite3.OperationalError, sqlite3.ProgrammingError),
            operation_name="sqlite.save_provenance_event",
        )

    def load_provenance_events(
        self,
        entity_id: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 10000,
    ) -> List[dict]:
        sql = "SELECT * FROM provenance_events"
        params: list = []
        clauses = []
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if namespace:
            clauses.append("namespace = ?")
            params.append(namespace)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)
        rows = self._txn(lambda c: c.execute(sql, params).fetchall())
        cols = [
            "id", "entity_id", "entity_type", "operation", "source", "timestamp",
            "session_id", "namespace", "confidence", "related_ids", "metadata",
        ]
        out = []
        for row in rows:
            rec = dict(zip(cols, row))
            rec["related_ids"] = json.loads(rec["related_ids"] or "[]")
            rec["metadata"] = json.loads(rec["metadata"] or "{}")
            out.append(rec)
        return out

    def count(self) -> int:
        return self._txn(lambda c: c.execute("SELECT COUNT(*) FROM memories").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
