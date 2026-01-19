-- Migration: Branch Fingerprints for Intelligent Commit Routing
-- Semantic centroid per branch enables automatic routing validation

-- Ensure pgvector extension (may already exist)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS branch_fingerprints (
    tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
    branch_name VARCHAR(255) NOT NULL,
    centroid vector(1536),
    commit_count INTEGER DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, branch_name)
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_fingerprints_branch ON branch_fingerprints(branch_name);

-- Grant permissions
GRANT ALL ON branch_fingerprints TO postgres;
