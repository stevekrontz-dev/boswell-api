-- Migration 014: Boswell Immune System
-- Adds quarantine capability to blobs and audit logging for immune actions
-- Author: CC-Opus
-- Context: Immune system detects anomalies in memory graph, quarantines for human review

-- PART 1: QUARANTINE COLUMNS ON BLOBS
-- Blobs can be quarantined pending human review
ALTER TABLE blobs ADD COLUMN IF NOT EXISTS quarantined BOOLEAN DEFAULT FALSE;
ALTER TABLE blobs ADD COLUMN IF NOT EXISTS quarantined_at TIMESTAMPTZ;
ALTER TABLE blobs ADD COLUMN IF NOT EXISTS quarantine_reason TEXT;

-- Index for fast quarantine lookups (partial index - only quarantined blobs)
CREATE INDEX IF NOT EXISTS idx_blobs_quarantined ON blobs(quarantined) WHERE quarantined = TRUE;

-- PART 2: IMMUNE_LOG TABLE (Audit Trail)
-- Tracks all immune system actions: patrols, quarantines, reinstatements, deletions
CREATE TABLE IF NOT EXISTS immune_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
    action VARCHAR(50) NOT NULL,           -- QUARANTINE, REINSTATE, DELETE, PATROL_START, PATROL_END
    blob_hash VARCHAR(64),                 -- NULL for patrol entries
    patrol_type VARCHAR(50),               -- CENTROID_DRIFT, ORPHAN_BLOB, BROKEN_LINK, etc.
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for immune_log
CREATE INDEX IF NOT EXISTS idx_immune_log_action ON immune_log(action);
CREATE INDEX IF NOT EXISTS idx_immune_log_blob ON immune_log(blob_hash) WHERE blob_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_immune_log_tenant ON immune_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_immune_log_created ON immune_log(created_at DESC);

-- Row Level Security for immune_log
ALTER TABLE immune_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON immune_log
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- PART 3: BRANCH HEALTH TRACKING
-- Extend branch_fingerprints with health metrics
ALTER TABLE branch_fingerprints ADD COLUMN IF NOT EXISTS health_score FLOAT DEFAULT 1.0;
ALTER TABLE branch_fingerprints ADD COLUMN IF NOT EXISTS last_patrol TIMESTAMPTZ;

-- PART 4: GRANTS
GRANT ALL ON immune_log TO postgres;

-- PART 5: VERIFY
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'blobs' AND column_name LIKE 'quarantine%';
-- SELECT table_name FROM information_schema.tables WHERE table_name = 'immune_log';
