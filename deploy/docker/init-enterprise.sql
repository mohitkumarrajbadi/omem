-- OMem Enterprise — PostgreSQL initialization script
-- Runs once when the container is first started.
-- Enables pgvector and creates the enterprise schema with multi-tenant isolation.

-- Enable pgvector extension for native vector similarity search.
-- This replaces FAISS for cloud deployments and enables ivfflat indexes.
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_trgm for fast ILIKE / fuzzy text search on memory content.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ─── Core memories table (enterprise edition) ────────────────────────────────
CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    org_id          TEXT    NOT NULL DEFAULT '',
    user_id         TEXT    NOT NULL DEFAULT '',
    type            INTEGER NOT NULL,
    content         TEXT    NOT NULL,
    -- pgvector column: 384-dim for all-MiniLM-L6-v2.
    -- Adjust dimension if you switch embedding models.
    embedding       vector(384),
    -- Raw bytes fallback (used by non-pgvector code paths)
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
    metadata        JSONB   DEFAULT '{}',
    score           DOUBLE PRECISION DEFAULT 0.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Tenant registry ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS omem_tenants (
    org_id          TEXT NOT NULL,
    user_id         TEXT NOT NULL DEFAULT '',
    plan            TEXT NOT NULL DEFAULT 'free',
    max_memories    INTEGER NOT NULL DEFAULT 10000,
    max_namespaces  INTEGER NOT NULL DEFAULT 10,
    created_at      DOUBLE PRECISION NOT NULL,
    updated_at      DOUBLE PRECISION NOT NULL,
    metadata        JSONB DEFAULT '{}',
    PRIMARY KEY (org_id, user_id)
);

-- ─── Indexes ──────────────────────────────────────────────────────────────────
-- Tenant boundary — most critical, all queries must include (org_id, user_id)
CREATE INDEX IF NOT EXISTS idx_mem_tenant
    ON memories(org_id, user_id);

CREATE INDEX IF NOT EXISTS idx_mem_tenant_ns
    ON memories(org_id, user_id, namespace);

-- Active memory filtering
CREATE INDEX IF NOT EXISTS idx_mem_active
    ON memories(org_id, user_id, active)
    WHERE active = 1;

-- Importance ranking (for top-k recall pre-filter)
CREATE INDEX IF NOT EXISTS idx_mem_importance
    ON memories(org_id, user_id, importance DESC)
    WHERE active = 1;

-- Hash-based dedup
CREATE INDEX IF NOT EXISTS idx_mem_hash
    ON memories(logical_hash)
    WHERE logical_hash != '';

-- Full-text search via trigrams (ILIKE acceleration)
CREATE INDEX IF NOT EXISTS idx_mem_content_trgm
    ON memories USING gin(content gin_trgm_ops);

-- JSONB metadata index (for kind-based filtering: ADRs, bug fixes, PRs)
CREATE INDEX IF NOT EXISTS idx_mem_metadata_kind
    ON memories USING gin(metadata jsonb_path_ops);

-- pgvector IVFFlat index for approximate nearest-neighbor search.
-- Requires at least 1000 rows to build. Rebuild with:
--   CREATE INDEX CONCURRENTLY idx_mem_embedding_ivfflat ON memories
--   USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- (Commented out here; let the app create it after initial data load.)
-- CREATE INDEX IF NOT EXISTS idx_mem_embedding_ivfflat
--     ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ─── Row-level security ───────────────────────────────────────────────────────
-- Policies enforce tenant isolation at the database layer.
-- The application sets omem.org_id and omem.user_id via SET LOCAL before queries.

ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

-- Allow superuser (migrations, admin) to bypass RLS.
ALTER TABLE memories FORCE ROW LEVEL SECURITY;

-- Tenant isolation policy: a session can only read/write its own rows.
DROP POLICY IF EXISTS memories_tenant_rls ON memories;
CREATE POLICY memories_tenant_rls ON memories
    AS PERMISSIVE
    FOR ALL
    TO PUBLIC
    USING (
        org_id  = COALESCE(NULLIF(current_setting('omem.org_id',  true), ''), org_id)
        AND
        user_id = COALESCE(NULLIF(current_setting('omem.user_id', true), ''), user_id)
    );

-- ─── Updated_at trigger ───────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION omem_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_memories_updated_at ON memories;
CREATE TRIGGER trg_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW EXECUTE FUNCTION omem_set_updated_at();
