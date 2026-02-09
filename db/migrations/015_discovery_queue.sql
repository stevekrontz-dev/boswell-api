-- Migration 015: Discovery queue for orphan surfacing
-- Part of the Auto-Trail + Semantic Discovery architecture

CREATE TABLE IF NOT EXISTS discovery_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL DEFAULT 'default',
    blob_hash VARCHAR(64) NOT NULL,
    orphan_score FLOAT NOT NULL,
    value_score FLOAT NOT NULL,
    branch VARCHAR(255),
    preview TEXT,
    commit_message TEXT,
    surfaced_at TIMESTAMPTZ DEFAULT NOW(),
    consumed_by VARCHAR(255),
    consumed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'pending',
    UNIQUE(tenant_id, blob_hash)
);

CREATE INDEX IF NOT EXISTS idx_discovery_queue_status ON discovery_queue(status, value_score DESC);
