"""SQLite storage backend — the default, zero-config backend."""

import json
import sqlite3
from typing import List, Optional

import numpy as np

from ..types import Memory, MemoryType
from .base import Backend


class SQLiteBackend(Backend):
    """Stores memories in a local SQLite database.

    Args:
        db_path: Filesystem path for the ``.db`` file, or ``":memory:"``
                 for a purely in-memory database (default).
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
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
        self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, memory: Memory) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO memories
               (id, type, content, vector, timestamp, importance, utility_score, access_count,
                last_accessed, namespace, source, active, status, consensus_score, logical_hash, metadata, score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                memory.id,
                memory.type.value,
                memory.content,
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
                json.dumps(memory.metadata),
                memory.score,
            ),
        )
        self._conn.commit()

    def save_batch(self, memories: List[Memory]) -> None:
        if not memories:
            return
        data = [
            (
                m.id,
                m.type.value,
                m.content,
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
                json.dumps(m.metadata),
                m.score,
            )
            for m in memories
        ]
        self._conn.executemany(
            """INSERT OR REPLACE INTO memories
               (id, type, content, vector, timestamp, importance, utility_score, access_count,
                last_accessed, namespace, source, active, status, consensus_score, logical_hash, metadata, score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            data,
        )
        self._conn.commit()

    def load(self, memory_id: str) -> Optional[Memory]:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def search(self, query: str, limit: int = 10) -> List[Memory]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def all(self) -> List[Memory]:
        rows = self._conn.execute("SELECT * FROM memories").fetchall()
        return [self._row_to_memory(r) for r in rows]

    def delete(self, memory_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def clear(self) -> None:
        self._conn.execute("DELETE FROM memories")
        self._conn.commit()

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_memory(row: tuple) -> Memory:
        # Columns in order: id, type, content, vector, timestamp, importance, utility_score, access_count, last_accessed, namespace, source, active, status, consensus_score, logical_hash, metadata, score
        from ..types import MemoryStatus

        (
            mid,
            mtype,
            content,
            vec_bytes,
            ts,
            imp,
            util,
            count,
            last,
            ns,
            src,
            active,
            status,
            consensus,
            lhash,
            meta_json,
            score,
        ) = row
        vector = (
            np.frombuffer(vec_bytes, dtype=np.float32).copy()
            if vec_bytes
            else np.zeros(384, dtype=np.float32)
        )
        return Memory(
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
            metadata=json.loads(meta_json) if meta_json else {},
            score=score,
        )

    def close(self) -> None:
        self._conn.close()
