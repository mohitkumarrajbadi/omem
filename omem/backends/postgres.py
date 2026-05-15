"""PostgreSQL storage backend for scalable deployments."""

import json
import logging
from typing import List, Optional

import numpy as np

from .base import Backend
from ..types import Memory, MemoryType, MemoryStatus
from ..core.utils.circuit_breaker import CircuitBreaker
from ..core.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

_PSYCOPG2_MISSING = (
    "psycopg2 is not installed. "
    "Install the PostgreSQL extra with: pip install omem-os[postgres]"
)


class PostgresBackend(Backend):
    """Stores memories in a PostgreSQL database.

    Args:
        connection_string: Standard Postgres DSN or URL.
        pool_min: Minimum number of connections in the pool.
        pool_max: Maximum number of connections in the pool.
    """

    def __init__(
        self,
        connection_string: str,
        pool_min: int = 1,
        pool_max: int = 10,
        encryptor=None,
    ):
        try:
            import psycopg2
            import psycopg2.pool
            from psycopg2.extras import DictCursor, execute_values
        except ImportError as exc:
            raise ImportError(_PSYCOPG2_MISSING) from exc

        # Store as instance attributes so methods can reference them without
        # a module-level import (psycopg2 is an optional dependency).
        self._psycopg2 = psycopg2
        self._DictCursor = DictCursor
        self._execute_values = execute_values
        self._enc = encryptor

        self.connection_string = connection_string
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                pool_min, pool_max, dsn=connection_string
            )
            self._circuit = CircuitBreaker(
                name=f"postgres:{connection_string[:40]}",
                failure_threshold=5,
                recovery_timeout=30.0,
            )
            self._create_table()
            logger.info("PostgresBackend initialized successfully.")
        except Exception as e:
            logger.error("Failed to initialize PostgresBackend: %s", e)
            raise

    def _get_conn(self):
        return self._pool.getconn()

    def _put_conn(self, conn):
        self._pool.putconn(conn)

    def _create_table(self) -> None:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id              TEXT PRIMARY KEY,
                        type            INTEGER NOT NULL,
                        content         TEXT    NOT NULL,
                        vector          BYTEA,
                        timestamp       DOUBLE PRECISION NOT NULL,
                        importance      DOUBLE PRECISION DEFAULT 0.5,
                        utility_score   DOUBLE PRECISION DEFAULT 0.0,
                        access_count    INTEGER DEFAULT 0,
                        last_accessed   DOUBLE PRECISION DEFAULT 0.0,
                        namespace       TEXT    DEFAULT 'default',
                        source          TEXT    DEFAULT '',
                        active          INTEGER DEFAULT 1,
                        status          INTEGER DEFAULT 0,
                        consensus_score DOUBLE PRECISION DEFAULT 0.0,
                        logical_hash    TEXT    DEFAULT '',
                        metadata        TEXT    DEFAULT '{}',
                        score           DOUBLE PRECISION DEFAULT 0.0
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(type)")
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mem_ns ON memories(namespace)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mem_hash ON memories(logical_hash)"
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, memory: Memory) -> None:
        content = self._enc.encrypt(memory.content) if self._enc else memory.content
        meta = self._enc.encrypt(json.dumps(memory.metadata)) if self._enc else json.dumps(memory.metadata)

        def _do():
            import psycopg2
            conn = self._get_conn()
            try:
                def _inner():
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO memories
                               (id, type, content, vector, timestamp, importance, utility_score, access_count,
                                last_accessed, namespace, source, active, status, consensus_score, logical_hash, metadata, score)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (id) DO UPDATE SET
                               type = EXCLUDED.type, content = EXCLUDED.content,
                               vector = EXCLUDED.vector, timestamp = EXCLUDED.timestamp,
                               importance = EXCLUDED.importance, utility_score = EXCLUDED.utility_score,
                               access_count = EXCLUDED.access_count, last_accessed = EXCLUDED.last_accessed,
                               namespace = EXCLUDED.namespace, source = EXCLUDED.source,
                               active = EXCLUDED.active, status = EXCLUDED.status,
                               consensus_score = EXCLUDED.consensus_score, logical_hash = EXCLUDED.logical_hash,
                               metadata = EXCLUDED.metadata, score = EXCLUDED.score""",
                            (
                                memory.id, memory.type.value, content,
                                memory.vector.tobytes() if memory.vector is not None else None,
                                memory.timestamp, memory.importance, memory.utility_score,
                                memory.access_count, memory.last_accessed, memory.namespace,
                                memory.source, 1 if memory.active else 0, memory.status.value,
                                memory.consensus_score, memory.logical_hash, meta, memory.score,
                            ),
                        )
                    conn.commit()

                retry_with_backoff(
                    _inner,
                    retryable_exceptions=(psycopg2.OperationalError, psycopg2.InterfaceError),
                    operation_name="postgres.save",
                )
            finally:
                self._put_conn(conn)

        self._circuit.call(_do)

    def save_batch(self, memories: List[Memory]) -> None:
        if not memories:
            return

        data = [
            (
                m.id, m.type.value,
                self._enc.encrypt(m.content) if self._enc else m.content,
                m.vector.tobytes() if m.vector is not None else None,
                m.timestamp, m.importance, m.utility_score, m.access_count,
                m.last_accessed, m.namespace, m.source,
                1 if m.active else 0, m.status.value, m.consensus_score,
                m.logical_hash,
                self._enc.encrypt(json.dumps(m.metadata)) if self._enc else json.dumps(m.metadata),
                m.score,
            )
            for m in memories
        ]

        def _do():
            import psycopg2
            conn = self._get_conn()
            try:
                def _inner():
                    with conn.cursor() as cur:
                        query = """INSERT INTO memories
                               (id, type, content, vector, timestamp, importance, utility_score, access_count,
                                last_accessed, namespace, source, active, status, consensus_score, logical_hash, metadata, score)
                               VALUES %s
                               ON CONFLICT (id) DO UPDATE SET
                               type = EXCLUDED.type, content = EXCLUDED.content,
                               vector = EXCLUDED.vector, timestamp = EXCLUDED.timestamp,
                               importance = EXCLUDED.importance, utility_score = EXCLUDED.utility_score,
                               access_count = EXCLUDED.access_count, last_accessed = EXCLUDED.last_accessed,
                               namespace = EXCLUDED.namespace, source = EXCLUDED.source,
                               active = EXCLUDED.active, status = EXCLUDED.status,
                               consensus_score = EXCLUDED.consensus_score, logical_hash = EXCLUDED.logical_hash,
                               metadata = EXCLUDED.metadata, score = EXCLUDED.score"""
                        self._execute_values(cur, query, data)
                    conn.commit()

                retry_with_backoff(
                    _inner,
                    retryable_exceptions=(psycopg2.OperationalError, psycopg2.InterfaceError),
                    operation_name="postgres.save_batch",
                )
            finally:
                self._put_conn(conn)

        self._circuit.call(_do)

    def load(self, memory_id: str) -> Optional[Memory]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._DictCursor) as cur:
                cur.execute("SELECT * FROM memories WHERE id = %s", (memory_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                return self._row_to_memory(row)
        finally:
            self._put_conn(conn)

    def search(self, query: str, limit: int = 10) -> List[Memory]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM memories WHERE content ILIKE %s LIMIT %s",
                    (f"%{query}%", limit),
                )
                rows = cur.fetchall()
                return [self._row_to_memory(r) for r in rows]
        finally:
            self._put_conn(conn)

    def all(self) -> List[Memory]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._DictCursor) as cur:
                cur.execute("SELECT * FROM memories")
                rows = cur.fetchall()
                return [self._row_to_memory(r) for r in rows]
        finally:
            self._put_conn(conn)

    def delete(self, memory_id: str) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self._put_conn(conn)

    def clear(self) -> None:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM memories")
            conn.commit()
        finally:
            self._put_conn(conn)

    def count(self) -> int:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM memories")
                return cur.fetchone()[0]
        finally:
            self._put_conn(conn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_memory(self, row) -> Memory:
        vec_bytes = row["vector"]
        vector = (
            np.frombuffer(vec_bytes, dtype=np.float32).copy()
            if vec_bytes
            else np.zeros(384, dtype=np.float32)
        )
        content = row["content"]
        metadata_raw = row["metadata"]
        if self._enc:
            content = self._enc.decrypt(content)
            metadata_raw = self._enc.decrypt(metadata_raw) if metadata_raw else metadata_raw
        return Memory(
            id=row["id"],
            type=MemoryType(row["type"]),
            content=content,
            vector=vector,
            timestamp=row["timestamp"],
            importance=row["importance"],
            utility_score=row["utility_score"],
            access_count=row["access_count"],
            last_accessed=row["last_accessed"],
            namespace=row["namespace"],
            source=row["source"],
            active=bool(row["active"]),
            status=MemoryStatus(row["status"]),
            consensus_score=row["consensus_score"],
            logical_hash=row["logical_hash"],
            metadata=json.loads(metadata_raw) if metadata_raw else {},
            score=row["score"],
        )

    def close(self) -> None:
        if self._pool:
            self._pool.closeall()
