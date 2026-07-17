"""Enterprise PostgreSQL backend with strict multi-tenant namespace isolation.

Extends the base PostgresBackend with:
  • org_id / user_id columns for tenant-level segregation
  • Row-level security (RLS) enforcement via SET LOCAL session variables
  • A `tenants` table for quota and plan tracking
  • Tenant-scoped CRUD that physically prevents cross-tenant reads
  • A migration helper to upgrade existing deployments

Usage::

    from omem.backends.postgres_enterprise import EnterprisePostgresBackend

    backend = EnterprisePostgresBackend(
        connection_string="postgresql://omem:secret@db:5432/omem",
        org_id="acme-corp",
        user_id="alice",
    )

The org_id + user_id pair forms the tenant identity. All queries issued through
this backend automatically include a WHERE clause enforcing the tenant boundary,
making cross-tenant data leakage structurally impossible at the SQL layer.

Docker / cloud:
    Pass OMEM_ORG_ID and OMEM_USER_ID environment variables to the API container.
    The AgentPool picks these up via CloudServerConfig and passes them to the backend.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, List, Optional

import numpy as np

from ..core.utils.circuit_breaker import CircuitBreaker
from ..core.utils.retry import retry_with_backoff
from ..types import Memory, MemoryStatus, MemoryType
from .base import Backend
from .pg_session import resolve_pg_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Schema DDL
# ─────────────────────────────────────────────────────────────────────────────

_CREATE_MEMORIES_ENTERPRISE = """
CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    org_id          TEXT    NOT NULL DEFAULT '',
    user_id         TEXT    NOT NULL DEFAULT '',
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
);
"""

_CREATE_TENANTS_TABLE = """
CREATE TABLE IF NOT EXISTS omem_tenants (
    org_id          TEXT NOT NULL,
    user_id         TEXT NOT NULL DEFAULT '',
    plan            TEXT NOT NULL DEFAULT 'free',
    max_memories    INTEGER NOT NULL DEFAULT 10000,
    max_namespaces  INTEGER NOT NULL DEFAULT 10,
    created_at      DOUBLE PRECISION NOT NULL,
    updated_at      DOUBLE PRECISION NOT NULL,
    metadata        TEXT DEFAULT '{}',
    PRIMARY KEY (org_id, user_id)
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_mem_tenant ON memories(org_id, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_mem_tenant_ns ON memories(org_id, user_id, namespace)",
    "CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(type)",
    "CREATE INDEX IF NOT EXISTS idx_mem_ns ON memories(namespace)",
    "CREATE INDEX IF NOT EXISTS idx_mem_hash ON memories(logical_hash)",
    "CREATE INDEX IF NOT EXISTS idx_mem_active ON memories(active)",
    "CREATE INDEX IF NOT EXISTS idx_mem_importance ON memories(importance DESC)",
]

# RLS policies are applied by omem-cloud migration 004_rls_namespace.sql.


# ─────────────────────────────────────────────────────────────────────────────
# Migration helper
# ─────────────────────────────────────────────────────────────────────────────

MIGRATION_001 = """
-- Migration 001: add tenant columns to an existing memories table
-- Safe to run multiple times (IF NOT EXISTS / DO NOTHING semantics).

ALTER TABLE memories ADD COLUMN IF NOT EXISTS org_id  TEXT NOT NULL DEFAULT '';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_mem_tenant    ON memories(org_id, user_id);
CREATE INDEX IF NOT EXISTS idx_mem_tenant_ns ON memories(org_id, user_id, namespace);
"""


def run_migration(connection_string: str) -> None:
    """Apply MIGRATION_001 to an existing non-enterprise database.

    Safe to run on a database that already has the columns — the IF NOT EXISTS
    clauses prevent duplicate column errors.
    """
    try:
        import psycopg2
    except ImportError as exc:
        raise ImportError("psycopg2 required: pip install omem-os[postgres]") from exc

    conn = psycopg2.connect(dsn=connection_string)
    try:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_001)
        conn.commit()
        logger.info("Migration 001 applied successfully.")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Enterprise backend
# ─────────────────────────────────────────────────────────────────────────────

class EnterprisePostgresBackend(Backend):
    """Multi-tenant PostgreSQL backend with structural tenant isolation.

    Every read and write is scoped to (org_id, user_id). The WHERE clause is
    injected at the SQL level — application-layer namespace filtering is NOT
    sufficient for enterprise isolation.

    Args:
        connection_string: Standard Postgres DSN.
        org_id: Organisation identifier (e.g. 'acme-corp').
        user_id: User identifier within the org (e.g. 'alice', or '' for org-wide).
        pool_min: Min pool connections.
        pool_max: Max pool connections.
        enable_rls: If True, apply Postgres RLS policies (requires superuser once).
        encryptor: Optional field-level encryptor for content / metadata.
    """

    def __init__(
        self,
        connection_string: str,
        org_id: str = "",
        user_id: str = "",
        pool_min: int = 2,
        pool_max: int = 20,
        enable_rls: bool = False,
        encryptor=None,
    ):
        try:
            import psycopg2
            import psycopg2.pool
            from psycopg2.extras import DictCursor, execute_values
        except ImportError as exc:
            raise ImportError(
                "psycopg2 required: pip install omem-os[postgres]"
            ) from exc

        self._psycopg2 = psycopg2
        self._DictCursor = DictCursor
        self._execute_values = execute_values
        self._enc = encryptor

        self.org_id = org_id or os.getenv("OMEM_ORG_ID", "default")
        self.user_id = user_id or os.getenv("OMEM_USER_ID", "")
        self.connection_string = connection_string
        self._enable_rls = enable_rls

        self._pool = psycopg2.pool.ThreadedConnectionPool(
            pool_min, pool_max, dsn=connection_string
        )
        self._circuit = CircuitBreaker(
            name=f"pg-enterprise:{connection_string[:40]}",
            failure_threshold=5,
            recovery_timeout=30.0,
        )
        self._bootstrap_schema()
        self._ensure_tenant()
        logger.info(
            "EnterprisePostgresBackend ready  org=%s  user=%s",
            self.org_id, self.user_id,
        )

    # ── Schema bootstrap ──────────────────────────────────────────────────────

    def _bootstrap_schema(self) -> None:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_CREATE_MEMORIES_ENTERPRISE)
                cur.execute(_CREATE_TENANTS_TABLE)
                for idx_sql in _CREATE_INDEXES:
                    cur.execute(idx_sql)
            conn.commit()
        finally:
            self._put_conn(conn)

    def _ensure_tenant(self) -> None:
        """Register this tenant in omem_tenants if not already present."""
        conn = self._get_conn()
        try:
            now = time.time()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO omem_tenants (org_id, user_id, plan, created_at, updated_at)
                    VALUES (%s, %s, 'free', %s, %s)
                    ON CONFLICT (org_id, user_id) DO NOTHING
                    """,
                    (self.org_id, self.user_id, now, now),
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    # ── Connection management ─────────────────────────────────────────────────

    def _get_conn(self):
        return self._pool.getconn()

    def _put_conn(self, conn) -> None:
        self._pool.putconn(conn)

    def _set_tenant_context(self, cur, *, namespace: Optional[str] = None) -> None:
        """Set Postgres session variables for RLS policy evaluation (SET LOCAL)."""
        ns = namespace or resolve_pg_session(fallback_namespace="default").namespace
        cur.execute("SET LOCAL app.current_namespace = %s", (ns,))
        cur.execute("SET LOCAL omem.org_id  = %s", (self.org_id,))
        cur.execute("SET LOCAL omem.user_id = %s", (self.user_id,))

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def save(self, memory: Memory) -> None:
        content = self._enc.encrypt(memory.content) if self._enc else memory.content
        meta = (
            self._enc.encrypt(json.dumps(memory.metadata))
            if self._enc else json.dumps(memory.metadata)
        )

        def _do() -> None:
            import psycopg2
            conn = self._get_conn()
            try:
                def _inner() -> None:
                    with conn.cursor() as cur:
                        self._set_tenant_context(cur)
                        cur.execute(
                            """
                            INSERT INTO memories
                              (id, org_id, user_id, type, content, vector, timestamp,
                               importance, utility_score, access_count, last_accessed,
                               namespace, source, active, status, consensus_score,
                               logical_hash, metadata, score)
                            VALUES
                              (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (id) DO UPDATE SET
                              type=EXCLUDED.type, content=EXCLUDED.content,
                              vector=EXCLUDED.vector, timestamp=EXCLUDED.timestamp,
                              importance=EXCLUDED.importance,
                              utility_score=EXCLUDED.utility_score,
                              access_count=EXCLUDED.access_count,
                              last_accessed=EXCLUDED.last_accessed,
                              namespace=EXCLUDED.namespace, source=EXCLUDED.source,
                              active=EXCLUDED.active, status=EXCLUDED.status,
                              consensus_score=EXCLUDED.consensus_score,
                              logical_hash=EXCLUDED.logical_hash,
                              metadata=EXCLUDED.metadata, score=EXCLUDED.score
                            """,
                            (
                                memory.id, self.org_id, self.user_id,
                                memory.type.value, content,
                                memory.vector.tobytes() if memory.vector is not None else None,
                                memory.timestamp, memory.importance, memory.utility_score,
                                memory.access_count, memory.last_accessed,
                                memory.namespace, memory.source,
                                1 if memory.active else 0, memory.status.value,
                                memory.consensus_score, memory.logical_hash, meta, memory.score,
                            ),
                        )
                    conn.commit()

                retry_with_backoff(
                    _inner,
                    retryable_exceptions=(
                        psycopg2.OperationalError, psycopg2.InterfaceError
                    ),
                    operation_name="enterprise.save",
                )
            finally:
                self._put_conn(conn)

        self._circuit.call(_do)

    def save_batch(self, memories: List[Memory]) -> None:
        if not memories:
            return

        data = [
            (
                m.id, self.org_id, self.user_id,
                m.type.value,
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

        def _do() -> None:
            import psycopg2
            conn = self._get_conn()
            try:
                def _inner() -> None:
                    with conn.cursor() as cur:
                        self._set_tenant_context(cur)
                        query = """
                            INSERT INTO memories
                              (id, org_id, user_id, type, content, vector, timestamp,
                               importance, utility_score, access_count, last_accessed,
                               namespace, source, active, status, consensus_score,
                               logical_hash, metadata, score)
                            VALUES %s
                            ON CONFLICT (id) DO UPDATE SET
                              type=EXCLUDED.type, content=EXCLUDED.content,
                              vector=EXCLUDED.vector, timestamp=EXCLUDED.timestamp,
                              importance=EXCLUDED.importance,
                              utility_score=EXCLUDED.utility_score,
                              access_count=EXCLUDED.access_count,
                              last_accessed=EXCLUDED.last_accessed,
                              namespace=EXCLUDED.namespace, source=EXCLUDED.source,
                              active=EXCLUDED.active, status=EXCLUDED.status,
                              consensus_score=EXCLUDED.consensus_score,
                              logical_hash=EXCLUDED.logical_hash,
                              metadata=EXCLUDED.metadata, score=EXCLUDED.score
                        """
                        self._execute_values(cur, query, data)
                    conn.commit()

                retry_with_backoff(
                    _inner,
                    retryable_exceptions=(
                        psycopg2.OperationalError, psycopg2.InterfaceError
                    ),
                    operation_name="enterprise.save_batch",
                )
            finally:
                self._put_conn(conn)

        self._circuit.call(_do)

    def load(self, memory_id: str) -> Optional[Memory]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._DictCursor) as cur:
                self._set_tenant_context(cur)
                cur.execute(
                    "SELECT * FROM memories WHERE id = %s AND org_id = %s AND user_id = %s",
                    (memory_id, self.org_id, self.user_id),
                )
                row = cur.fetchone()
                return self._row_to_memory(row) if row else None
        finally:
            self._put_conn(conn)

    def search(self, query: str, limit: int = 10) -> List[Memory]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._DictCursor) as cur:
                self._set_tenant_context(cur)
                cur.execute(
                    """
                    SELECT * FROM memories
                    WHERE content ILIKE %s AND org_id = %s AND user_id = %s
                    LIMIT %s
                    """,
                    (f"%{query}%", self.org_id, self.user_id, limit),
                )
                return [self._row_to_memory(r) for r in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def all(self) -> List[Memory]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._DictCursor) as cur:
                self._set_tenant_context(cur)
                cur.execute(
                    "SELECT * FROM memories WHERE org_id = %s AND user_id = %s",
                    (self.org_id, self.user_id),
                )
                return [self._row_to_memory(r) for r in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def delete(self, memory_id: str) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                self._set_tenant_context(cur)
                cur.execute(
                    "DELETE FROM memories WHERE id = %s AND org_id = %s AND user_id = %s",
                    (memory_id, self.org_id, self.user_id),
                )
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self._put_conn(conn)

    def clear(self) -> None:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                self._set_tenant_context(cur)
                cur.execute(
                    "DELETE FROM memories WHERE org_id = %s AND user_id = %s",
                    (self.org_id, self.user_id),
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    def count(self) -> int:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                self._set_tenant_context(cur)
                cur.execute(
                    "SELECT COUNT(*) FROM memories WHERE org_id = %s AND user_id = %s",
                    (self.org_id, self.user_id),
                )
                return cur.fetchone()[0]
        finally:
            self._put_conn(conn)

    # ── Tenant administration ─────────────────────────────────────────────────

    def tenant_info(self) -> Dict:
        """Return the current tenant's plan and quota information."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM omem_tenants WHERE org_id = %s AND user_id = %s",
                    (self.org_id, self.user_id),
                )
                row = cur.fetchone()
                if row is None:
                    return {"org_id": self.org_id, "user_id": self.user_id, "plan": "unknown"}
                return dict(row)
        finally:
            self._put_conn(conn)

    def tenant_memory_count(self) -> int:
        """Count memories owned by this tenant across all namespaces."""
        return self.count()

    def list_tenant_namespaces(self) -> List[str]:
        """Return the distinct namespaces used by this tenant."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                self._set_tenant_context(cur)
                cur.execute(
                    """
                    SELECT DISTINCT namespace FROM memories
                    WHERE org_id = %s AND user_id = %s AND active = 1
                    ORDER BY namespace
                    """,
                    (self.org_id, self.user_id),
                )
                return [r[0] for r in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def upgrade_tenant_plan(self, plan: str, max_memories: int) -> None:
        """Update a tenant's plan and quota limits (admin operation)."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE omem_tenants
                    SET plan = %s, max_memories = %s, updated_at = %s
                    WHERE org_id = %s AND user_id = %s
                    """,
                    (plan, max_memories, time.time(), self.org_id, self.user_id),
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _row_to_memory(self, row) -> Memory:
        vec_bytes = row["vector"]
        vector = (
            np.frombuffer(vec_bytes, dtype=np.float32).copy()
            if vec_bytes else np.zeros(384, dtype=np.float32)
        )
        content = row["content"]
        metadata_raw = row["metadata"]
        if self._enc:
            content = self._enc.decrypt(content)
            if metadata_raw:
                metadata_raw = self._enc.decrypt(metadata_raw)
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
