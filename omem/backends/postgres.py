"""PostgreSQL storage backend for scalable deployments."""

import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.utils.circuit_breaker import CircuitBreaker
from ..core.utils.retry import retry_with_backoff
from ..types import Memory, MemoryStatus, MemoryType
from .base import Backend
from .pg_session import apply_pg_session, resolve_pg_session, resolve_pg_session_for_write

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
            self._pgvector_enabled = False
            self._embedding_model = os.environ.get("OMEM_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            self._embedding_version = os.environ.get("OMEM_EMBEDDING_VERSION", "v1")
            self._create_table()
            self._migrate_layers()
            logger.info(
                "PostgresBackend initialized (pgvector=%s).",
                self._pgvector_enabled,
            )
        except Exception as e:
            logger.error("Failed to initialize PostgresBackend: %s", e)
            raise

    def _get_conn(self):
        return self._pool.getconn()

    def _put_conn(self, conn):
        self._pool.putconn(conn)

    def _apply_read_session(self, cur, *, namespace: Optional[str] = None) -> None:
        apply_pg_session(cur, resolve_pg_session(fallback_namespace=namespace or "default"))

    def _apply_write_session(self, cur, memory: Memory) -> None:
        apply_pg_session(cur, resolve_pg_session_for_write(memory))

    def _apply_namespace_session(self, cur, namespace: str) -> None:
        apply_pg_session(cur, resolve_pg_session(fallback_namespace=namespace))

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

    def _migrate_layers(self) -> None:
        """Add pgvector, embedding versioning, and projection tables."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    self._pgvector_enabled = True
                except Exception as exc:
                    logger.debug("pgvector extension unavailable: %s", exc)
                    self._pgvector_enabled = False

                for col, col_type in (
                    ("embedding", "vector(384)"),
                    ("embedding_model", "TEXT DEFAULT ''"),
                    ("embedding_version", "TEXT DEFAULT ''"),
                    ("embedding_dim", "INTEGER DEFAULT 384"),
                    ("lifecycle_state", "TEXT DEFAULT 'active'"),
                ):
                    cur.execute(
                        """
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'memories' AND column_name = %s
                        """,
                        (col,),
                    )
                    if cur.fetchone() is None:
                        cur.execute(
                            f"ALTER TABLE memories ADD COLUMN {col} {col_type}"
                        )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_edges (
                        id TEXT PRIMARY KEY,
                        namespace TEXT NOT NULL DEFAULT 'default',
                        source_id TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        relation_type TEXT NOT NULL DEFAULT 'related',
                        confidence DOUBLE PRECISION DEFAULT 1.0,
                        metadata JSONB DEFAULT '{}',
                        active INTEGER DEFAULT 1,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_events (
                        id BIGSERIAL PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        memory_id TEXT,
                        namespace TEXT NOT NULL DEFAULT 'default',
                        payload JSONB DEFAULT '{}',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        processed_at TIMESTAMPTZ,
                        attempts INTEGER DEFAULT 0
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_events_unprocessed
                    ON memory_events(created_at) WHERE processed_at IS NULL
                    """
                )
            conn.commit()
        finally:
            self._put_conn(conn)

        if self._pgvector_enabled:
            try:
                n = self.backfill_embeddings()
                if n:
                    logger.info("Backfilled pgvector embeddings for %d memories", n)
            except Exception as exc:
                logger.warning("Embedding backfill skipped: %s", exc)

    @staticmethod
    def _vec_to_pg(vector: np.ndarray) -> str:
        return "[" + ",".join(f"{float(x):.8f}" for x in vector.tolist()) + "]"

    def backfill_embeddings(self, *, limit: int = 5000) -> int:
        """Copy ``vector`` bytea into ``embedding`` for rows missing pgvector data.

        The async write-buffer historically called ``save_batch`` which persisted
        ``vector`` but not ``embedding``, breaking strong (pgvector) recall.
        """
        if not self._pgvector_enabled:
            return 0

        def _do() -> int:
            import psycopg2

            conn = self._get_conn()
            updated = 0
            try:
                with conn.cursor(cursor_factory=self._DictCursor) as cur:
                    # Forced RLS — allow migration to see all namespaces.
                    try:
                        cur.execute("SET LOCAL row_security = off")
                    except Exception:
                        pass
                    cur.execute(
                        """
                        SELECT id, vector, namespace
                        FROM memories
                        WHERE embedding IS NULL
                          AND vector IS NOT NULL
                          AND active = 1
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    rows = cur.fetchall() or []
                    for row in rows:
                        vec_bytes = row["vector"]
                        if not vec_bytes:
                            continue
                        vector = np.frombuffer(vec_bytes, dtype=np.float32).copy()
                        if vector.size == 0:
                            continue
                        emb_pg = self._vec_to_pg(vector)
                        cur.execute(
                            """
                            UPDATE memories
                            SET embedding = %s::vector,
                                embedding_model = CASE
                                    WHEN embedding_model IS NULL OR embedding_model = ''
                                    THEN %s ELSE embedding_model END,
                                embedding_version = CASE
                                    WHEN embedding_version IS NULL OR embedding_version = ''
                                    THEN %s ELSE embedding_version END,
                                embedding_dim = %s,
                                lifecycle_state = COALESCE(NULLIF(lifecycle_state, ''), 'active')
                            WHERE id = %s
                            """,
                            (
                                emb_pg,
                                self._embedding_model,
                                self._embedding_version,
                                int(vector.shape[0]),
                                row["id"],
                            ),
                        )
                        updated += cur.rowcount
                conn.commit()
                return updated
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                self._put_conn(conn)

        return self._circuit.call(_do)

    def emit_event(
        self,
        event_type: str,
        *,
        memory_id: Optional[str] = None,
        namespace: str = "default",
        payload: Optional[Dict[str, Any]] = None,
        conn=None,
    ) -> int:
        """Write a projection outbox event."""
        own_conn = conn is None
        if own_conn:
            conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                self._apply_namespace_session(cur, namespace)
                cur.execute(
                    """
                    INSERT INTO memory_events (event_type, memory_id, namespace, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    RETURNING id
                    """,
                    (
                        event_type,
                        memory_id,
                        namespace,
                        json.dumps(payload or {}),
                    ),
                )
                event_id = int(cur.fetchone()[0])
            if own_conn:
                conn.commit()
            return event_id
        finally:
            if own_conn:
                self._put_conn(conn)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(
        self,
        memory: Memory,
        *,
        embedding_model: str = "",
        embedding_version: str = "",
    ) -> None:
        if self._pgvector_enabled and memory.vector is not None:
            content = self._enc.encrypt(memory.content) if self._enc else memory.content
            meta = self._enc.encrypt(json.dumps(memory.metadata)) if self._enc else json.dumps(memory.metadata)
            emb_model = embedding_model or self._embedding_model
            emb_version = embedding_version or self._embedding_version
            emb_dim = int(memory.vector.shape[0]) if memory.vector is not None else 384
            emb_pg = self._vec_to_pg(memory.vector)
            self._save_one(memory, content, meta, emb_pg, emb_model, emb_version, emb_dim, pgvector=True)
            return

        content = self._enc.encrypt(memory.content) if self._enc else memory.content
        meta = self._enc.encrypt(json.dumps(memory.metadata)) if self._enc else json.dumps(memory.metadata)
        self._save_one(memory, content, meta, None, "", "", 384, pgvector=False)

    def _save_one(
        self,
        memory: Memory,
        content: str,
        meta: str,
        emb_pg: Optional[str],
        emb_model: str,
        emb_version: str,
        emb_dim: int,
        *,
        pgvector: bool,
    ) -> None:
        def _do():
            import psycopg2

            def _attempt():
                conn = self._get_conn()
                try:
                    with conn.cursor() as cur:
                        self._apply_write_session(cur, memory)
                        if pgvector and emb_pg:
                            cur.execute(
                                """INSERT INTO memories
                                   (id, type, content, vector, embedding, embedding_model,
                                    embedding_version, embedding_dim, lifecycle_state,
                                    timestamp, importance, utility_score, access_count,
                                    last_accessed, namespace, source, active, status,
                                    consensus_score, logical_hash, metadata, score)
                                   VALUES (%s,%s,%s,%s,%s::vector,%s,%s,%s,'active',
                                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                   ON CONFLICT (id) DO UPDATE SET
                                   type=EXCLUDED.type, content=EXCLUDED.content,
                                   vector=EXCLUDED.vector, embedding=EXCLUDED.embedding,
                                   embedding_model=EXCLUDED.embedding_model,
                                   embedding_version=EXCLUDED.embedding_version,
                                   embedding_dim=EXCLUDED.embedding_dim,
                                   lifecycle_state='active',
                                   timestamp=EXCLUDED.timestamp,
                                   importance=EXCLUDED.importance,
                                   utility_score=EXCLUDED.utility_score,
                                   access_count=EXCLUDED.access_count,
                                   last_accessed=EXCLUDED.last_accessed,
                                   namespace=EXCLUDED.namespace, source=EXCLUDED.source,
                                   active=EXCLUDED.active, status=EXCLUDED.status,
                                   consensus_score=EXCLUDED.consensus_score,
                                   logical_hash=EXCLUDED.logical_hash,
                                   metadata=EXCLUDED.metadata, score=EXCLUDED.score""",
                                (
                                    memory.id, memory.type.value, content,
                                    memory.vector.tobytes() if memory.vector is not None else None,
                                    emb_pg, emb_model, emb_version, emb_dim,
                                    memory.timestamp, memory.importance, memory.utility_score,
                                    memory.access_count, memory.last_accessed, memory.namespace,
                                    memory.source, 1 if memory.active else 0, memory.status.value,
                                    memory.consensus_score, memory.logical_hash, meta, memory.score,
                                ),
                            )
                        else:
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
                        cur.execute(
                            """
                            INSERT INTO memory_events (event_type, memory_id, namespace, payload)
                            VALUES ('memory.created', %s, %s, '{}'::jsonb)
                            """,
                            (memory.id, memory.namespace),
                        )
                    conn.commit()
                    self._put_conn(conn)
                except (psycopg2.OperationalError, psycopg2.InterfaceError):
                    try:
                        self._pool.putconn(conn, close=True)
                    except Exception:
                        pass
                    raise
                except Exception:
                    self._put_conn(conn)
                    raise

            retry_with_backoff(
                _attempt,
                retryable_exceptions=(psycopg2.OperationalError, psycopg2.InterfaceError),
                operation_name="postgres.save",
            )

        self._circuit.call(_do)

    def save_batch(self, memories: List[Memory]) -> None:
        if not memories:
            return

        namespaces = {m.namespace for m in memories}
        if len(namespaces) > 1:
            for mem in memories:
                self.save(mem)
            return

        # Prefer the single-row path when pgvector is on so embedding + vector
        # stay in sync (batch VALUES historically omitted the embedding column).
        if self._pgvector_enabled:
            data = []
            for m in memories:
                content = self._enc.encrypt(m.content) if self._enc else m.content
                meta = (
                    self._enc.encrypt(json.dumps(m.metadata))
                    if self._enc
                    else json.dumps(m.metadata)
                )
                if m.vector is None:
                    # Fall back to non-vector insert shape via save()
                    self.save(m)
                    continue
                emb_pg = self._vec_to_pg(m.vector)
                emb_dim = int(m.vector.shape[0])
                data.append(
                    (
                        m.id,
                        m.type.value,
                        content,
                        m.vector.tobytes(),
                        emb_pg,
                        self._embedding_model,
                        self._embedding_version,
                        emb_dim,
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
                        meta,
                        m.score,
                    )
                )
            if not data:
                return

            def _do_pg():
                import psycopg2

                def _attempt():
                    conn = self._get_conn()
                    try:
                        with conn.cursor() as cur:
                            self._apply_write_session(cur, memories[0])
                            query = """INSERT INTO memories
                                   (id, type, content, vector, embedding, embedding_model,
                                    embedding_version, embedding_dim, lifecycle_state,
                                    timestamp, importance, utility_score, access_count,
                                    last_accessed, namespace, source, active, status,
                                    consensus_score, logical_hash, metadata, score)
                                   VALUES %s
                                   ON CONFLICT (id) DO UPDATE SET
                                   type=EXCLUDED.type, content=EXCLUDED.content,
                                   vector=EXCLUDED.vector, embedding=EXCLUDED.embedding,
                                   embedding_model=EXCLUDED.embedding_model,
                                   embedding_version=EXCLUDED.embedding_version,
                                   embedding_dim=EXCLUDED.embedding_dim,
                                   lifecycle_state='active',
                                   timestamp=EXCLUDED.timestamp,
                                   importance=EXCLUDED.importance,
                                   utility_score=EXCLUDED.utility_score,
                                   access_count=EXCLUDED.access_count,
                                   last_accessed=EXCLUDED.last_accessed,
                                   namespace=EXCLUDED.namespace, source=EXCLUDED.source,
                                   active=EXCLUDED.active, status=EXCLUDED.status,
                                   consensus_score=EXCLUDED.consensus_score,
                                   logical_hash=EXCLUDED.logical_hash,
                                   metadata=EXCLUDED.metadata, score=EXCLUDED.score"""
                            # execute_values needs templates for ::vector cast on embedding
                            self._execute_values(
                                cur,
                                query,
                                data,
                                template=(
                                    "(%s,%s,%s,%s,%s::vector,%s,%s,%s,'active',"
                                    "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                                ),
                            )
                            for m in memories:
                                if m.vector is None:
                                    continue
                                cur.execute(
                                    """
                                    INSERT INTO memory_events (event_type, memory_id, namespace, payload)
                                    VALUES ('memory.created', %s, %s, '{}'::jsonb)
                                    """,
                                    (m.id, m.namespace),
                                )
                        conn.commit()
                        self._put_conn(conn)
                    except (psycopg2.OperationalError, psycopg2.InterfaceError):
                        try:
                            self._pool.putconn(conn, close=True)
                        except Exception:
                            pass
                        raise
                    except Exception:
                        self._put_conn(conn)
                        raise

                retry_with_backoff(
                    _attempt,
                    retryable_exceptions=(psycopg2.OperationalError, psycopg2.InterfaceError),
                    operation_name="postgres.save_batch",
                )

            self._circuit.call(_do_pg)
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

            def _attempt():
                conn = self._get_conn()
                try:
                    with conn.cursor() as cur:
                        self._apply_write_session(cur, memories[0])
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
                    self._put_conn(conn)
                except (psycopg2.OperationalError, psycopg2.InterfaceError):
                    try:
                        self._pool.putconn(conn, close=True)
                    except Exception:
                        pass
                    raise
                except Exception:
                    self._put_conn(conn)
                    raise

            retry_with_backoff(
                _attempt,
                retryable_exceptions=(psycopg2.OperationalError, psycopg2.InterfaceError),
                operation_name="postgres.save_batch",
            )

        self._circuit.call(_do)

    def load(self, memory_id: str) -> Optional[Memory]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._DictCursor) as cur:
                self._apply_read_session(cur)
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
                self._apply_read_session(cur)
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
                self._apply_read_session(cur)
                cur.execute("SELECT * FROM memories")
                rows = cur.fetchall()
                return [self._row_to_memory(r) for r in rows]
        finally:
            self._put_conn(conn)

    def delete(self, memory_id: str, namespace: Optional[str] = None) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                ns = namespace
                if ns is None:
                    self._apply_read_session(cur)
                    cur.execute(
                        "SELECT namespace FROM memories WHERE id = %s", (memory_id,)
                    )
                    row = cur.fetchone()
                    ns = row[0] if row else resolve_pg_session().namespace
                self._apply_namespace_session(cur, ns)
                cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
                deleted = cur.rowcount > 0
                if deleted:
                    cur.execute(
                        """
                        INSERT INTO memory_events (event_type, memory_id, namespace, payload)
                        VALUES ('memory.deleted', %s, %s, '{}'::jsonb)
                        """,
                        (memory_id, ns),
                    )
            conn.commit()
            return deleted
        finally:
            self._put_conn(conn)

    def vector_search(
        self,
        query_vector: np.ndarray,
        *,
        namespace: Optional[str] = None,
        top_k: int = 10,
        embedding_model: Optional[str] = None,
    ) -> List[Tuple[Memory, float]]:
        """ANN search via pgvector. Returns (memory, cosine_similarity) pairs."""
        if not self._pgvector_enabled:
            return []

        vec_str = self._vec_to_pg(query_vector)
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._DictCursor) as cur:
                self._apply_read_session(cur, namespace=namespace)
                clauses = ["active = 1", "embedding IS NOT NULL"]
                params: List[Any] = []
                if namespace:
                    clauses.append("namespace = %s")
                    params.append(namespace)
                if embedding_model:
                    clauses.append("embedding_model = %s")
                    params.append(embedding_model)
                where = " AND ".join(clauses)
                sql = f"""
                    SELECT *, 1 - (embedding <=> %s::vector) AS similarity
                    FROM memories
                    WHERE {where}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """
                cur.execute(sql, [vec_str] + params + [vec_str, top_k])
                rows = cur.fetchall()
                # Older rows may have empty embedding_model; retry without model filter.
                if not rows and embedding_model:
                    clauses = ["active = 1", "embedding IS NOT NULL"]
                    params = []
                    if namespace:
                        clauses.append("namespace = %s")
                        params.append(namespace)
                    where = " AND ".join(clauses)
                    sql = f"""
                        SELECT *, 1 - (embedding <=> %s::vector) AS similarity
                        FROM memories
                        WHERE {where}
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """
                    cur.execute(sql, [vec_str] + params + [vec_str, top_k])
                    rows = cur.fetchall()
                return [(self._row_to_memory(r), float(r["similarity"])) for r in rows]
        finally:
            self._put_conn(conn)

    def save_edge(
        self,
        namespace: str,
        source_id: str,
        target_id: str,
        relation_type: str = "related",
        confidence: float = 1.0,
    ) -> str:
        eid = uuid.uuid4().hex[:32]
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                self._apply_namespace_session(cur, namespace)
                cur.execute(
                    """
                    INSERT INTO memory_edges
                        (id, namespace, source_id, target_id, relation_type, confidence, active)
                    VALUES (%s, %s, %s, %s, %s, %s, 1)
                    ON CONFLICT (id) DO UPDATE SET active = 1, confidence = EXCLUDED.confidence
                    """,
                    (eid, namespace, source_id, target_id, relation_type, confidence),
                )
            conn.commit()
            return eid
        finally:
            self._put_conn(conn)

    def clear(self) -> None:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                self._apply_read_session(cur)
                cur.execute("DELETE FROM memories")
            conn.commit()
        finally:
            self._put_conn(conn)

    def count(self) -> int:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                self._apply_read_session(cur)
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
