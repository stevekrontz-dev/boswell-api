-- Migration 020: Performance indexes for P95 latency fix
-- Context: P95 at 1578ms, threshold 500ms. Missing indexes on trails table
-- cause full table scans on every P300 Wave 3 query and startup hot-trails query.
-- CC/CW consensus plan, March 29 2026.

-- Trails: source_blob + tenant_id (used in trail-boost, P300, startup hot-trails)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trails_source_tenant
ON trails(source_blob, tenant_id);

-- Trails: target_blob + tenant_id (used in trail-boost, supersession checks, P300)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trails_target_tenant
ON trails(target_blob, tenant_id);

-- Blobs: tenant_id filtered by embedding IS NOT NULL (vector search pre-filter)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_blobs_tenant_has_embedding
ON blobs(tenant_id) WHERE embedding IS NOT NULL;
