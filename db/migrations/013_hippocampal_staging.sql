-- Migration 013: Hippocampal Memory Staging (Boswell v4.0)
-- Two-stage memory: working memory (candidate_memories) + long-term (existing blobs/commits)
-- Connected by nightly consolidation cycle (sleep phase)

-- Enum for candidate status lifecycle
DO $$ BEGIN
    CREATE TYPE candidate_status AS ENUM ('active', 'cooling', 'promoted', 'expired');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- Table 1: candidate_memories (Working Memory / RAM)
-- ============================================================
CREATE TABLE IF NOT EXISTS candidate_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    branch VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    content JSONB,
    message TEXT,
    tags TEXT[],
    salience FLOAT DEFAULT 0.3,
    salience_type VARCHAR(50),
    replay_count INTEGER DEFAULT 0,
    consolidation_score FLOAT,

    -- Dual embeddings: content for search, context for auto-replay differentiation
    embedding vector(1536),          -- content embedding for search surfacing
    context_embedding vector(1536),  -- creation context embedding for auto-replay (NULL if no context)

    status candidate_status DEFAULT 'active',
    source_instance VARCHAR(255),
    session_context JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days',
    promoted_at TIMESTAMPTZ,
    promoted_commit_hash VARCHAR(64)
);

-- HNSW indexes on both embedding columns for fast vector search (works on empty tables)
CREATE INDEX IF NOT EXISTS idx_candidate_memories_embedding
    ON candidate_memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_candidate_memories_context_embedding
    ON candidate_memories USING hnsw (context_embedding vector_cosine_ops);

-- Operational indexes
CREATE INDEX IF NOT EXISTS idx_candidate_memories_status
    ON candidate_memories (status);
CREATE INDEX IF NOT EXISTS idx_candidate_memories_salience
    ON candidate_memories (salience DESC);
CREATE INDEX IF NOT EXISTS idx_candidate_memories_expires_at
    ON candidate_memories (expires_at);
CREATE INDEX IF NOT EXISTS idx_candidate_memories_replay_count
    ON candidate_memories (replay_count DESC);
CREATE INDEX IF NOT EXISTS idx_candidate_memories_tenant_branch
    ON candidate_memories (tenant_id, branch);
CREATE INDEX IF NOT EXISTS idx_candidate_memories_tenant_status
    ON candidate_memories (tenant_id, status);

-- RLS policy on tenant_id
ALTER TABLE candidate_memories ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS candidate_memories_tenant_isolation ON candidate_memories;
CREATE POLICY candidate_memories_tenant_isolation ON candidate_memories
    USING (tenant_id::text = current_setting('app.current_tenant', true));

-- ============================================================
-- Table 2: replay_events (Topic Recurrence Tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS replay_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    candidate_id UUID NOT NULL REFERENCES candidate_memories(id) ON DELETE CASCADE,
    session_id VARCHAR(255),
    replay_context TEXT,
    similarity_score FLOAT,
    fired BOOLEAN DEFAULT true,           -- false for near-misses logged for tuning
    threshold_used FLOAT,                 -- which threshold triggered (0.3 or 0.5)
    context_type VARCHAR(50),             -- 'context_embedding' or 'content_fallback'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_replay_events_candidate
    ON replay_events (candidate_id);
CREATE INDEX IF NOT EXISTS idx_replay_events_session
    ON replay_events (session_id);
CREATE INDEX IF NOT EXISTS idx_replay_events_tenant
    ON replay_events (tenant_id);

-- ============================================================
-- Table 3: consolidation_log (Sleep Cycle History)
-- ============================================================
CREATE TABLE IF NOT EXISTS consolidation_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    cycle_type VARCHAR(20) NOT NULL DEFAULT 'nightly',  -- nightly | manual
    candidates_evaluated INTEGER DEFAULT 0,
    candidates_promoted INTEGER DEFAULT 0,
    candidates_expired INTEGER DEFAULT 0,
    top_score FLOAT,
    threshold_used FLOAT,
    promoted_commits TEXT[],
    duration_ms INTEGER,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_consolidation_log_tenant
    ON consolidation_log (tenant_id);
CREATE INDEX IF NOT EXISTS idx_consolidation_log_started
    ON consolidation_log (started_at DESC);
