-- Migration 016: Work Hierarchy — Plans as memories, tasks grouped under plans
-- Adds title (display name) and plan_blob_hash (FK to blobs) to tasks table
-- Plans are boswell_commit with content_type='plan', referenced by blob hash

-- Short display name ("M4 Sentinel Farm" vs 500-word description)
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS title VARCHAR(500);

-- FK to blobs table — groups tasks under plans
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS plan_blob_hash TEXT;

-- Partial index for landscape queries (tasks grouped by plan)
CREATE INDEX IF NOT EXISTS idx_tasks_plan ON tasks(tenant_id, plan_blob_hash)
  WHERE plan_blob_hash IS NOT NULL;

-- Index for orphan backlog queries (tasks not under any plan)
CREATE INDEX IF NOT EXISTS idx_tasks_orphans ON tasks(tenant_id)
  WHERE plan_blob_hash IS NULL AND status IN ('open', 'claimed', 'blocked');
