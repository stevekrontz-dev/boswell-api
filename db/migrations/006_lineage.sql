-- Migration 006: Lineage tracking for sub-agent architecture
-- Owner: CC4
-- Task: Sub-agent memory architecture (from debate-001)
--
-- Adds lineage fields to commits table for tracking agent hierarchy:
--   agent_id: identifier for the agent that created this commit
--   parent_agent: the parent agent that spawned this agent
--   depth: depth level in agent hierarchy (0 = root)
--   swarm_run_id: groups commits from same swarm execution
--
-- Creates sediment table for consolidated long-term memory

-- PART 1: Add lineage columns to commits table
ALTER TABLE commits
ADD COLUMN IF NOT EXISTS agent_id VARCHAR(50),
ADD COLUMN IF NOT EXISTS parent_agent VARCHAR(50),
ADD COLUMN IF NOT EXISTS depth INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS swarm_run_id VARCHAR(100);

-- PART 2: Create indexes for lineage queries
CREATE INDEX IF NOT EXISTS idx_commits_agent ON commits(agent_id);
CREATE INDEX IF NOT EXISTS idx_commits_swarm_run ON commits(swarm_run_id);
CREATE INDEX IF NOT EXISTS idx_commits_depth ON commits(depth);
CREATE INDEX IF NOT EXISTS idx_commits_parent_agent ON commits(parent_agent);

-- PART 3: Enable pgvector extension if available (for semantic search)
-- This is optional - sediment table works without it
CREATE EXTENSION IF NOT EXISTS vector;

-- PART 4: Create sediment table for consolidated memories
CREATE TABLE IF NOT EXISTS sediment (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
    swarm_run_id VARCHAR(100) NOT NULL,
    branch VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    source_commits TEXT[], -- array of commit hashes that were consolidated
    agent_count INTEGER,
    depth_max INTEGER,
    conflicts JSONB DEFAULT '[]', -- detected contradictions
    consolidated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, swarm_run_id, branch)
);

-- Add embedding column if pgvector is available
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        ALTER TABLE sediment ADD COLUMN IF NOT EXISTS embedding VECTOR(1536);
        CREATE INDEX IF NOT EXISTS idx_sediment_embedding ON sediment USING ivfflat (embedding vector_cosine_ops);
    END IF;
END $$;

-- PART 5: Indexes for sediment table
CREATE INDEX IF NOT EXISTS idx_sediment_tenant ON sediment(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sediment_swarm_run ON sediment(swarm_run_id);
CREATE INDEX IF NOT EXISTS idx_sediment_branch ON sediment(branch);
CREATE INDEX IF NOT EXISTS idx_sediment_consolidated ON sediment(consolidated_at);

-- PART 6: Row Level Security for sediment
ALTER TABLE sediment ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON sediment
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- PART 7: Comments for documentation
COMMENT ON COLUMN commits.agent_id IS 'Identifier for agent that created this commit (e.g., CC4, CC4a-1)';
COMMENT ON COLUMN commits.parent_agent IS 'Parent agent that spawned this agent (null for root agents)';
COMMENT ON COLUMN commits.depth IS 'Depth in agent hierarchy: 0=root, 1=first-level sub-agent, etc.';
COMMENT ON COLUMN commits.swarm_run_id IS 'Groups commits from same swarm execution for consolidation';

COMMENT ON TABLE sediment IS 'Consolidated long-term memory from swarm runs. Created by nightly consolidation job.';
COMMENT ON COLUMN sediment.conflicts IS 'JSON array of detected contradictions between agents in this run';
COMMENT ON COLUMN sediment.embedding IS 'Vector embedding for semantic search (requires pgvector extension)';

-- PART 8: Verify migration
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'commits';
-- Should include: agent_id, parent_agent, depth, swarm_run_id
-- SELECT table_name FROM information_schema.tables WHERE table_name = 'sediment';
-- Should return 1 row
