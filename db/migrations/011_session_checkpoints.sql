-- SESSION CHECKPOINTS - Ephemeral state layer for crash recovery
-- Migration: Add session_checkpoints table
-- Author: CC (Claude Code)
-- Context: CW-Opus glitched during router implementation. Git commits preserve WHAT happened but not WHERE the instance WAS.
-- This captures ephemeral "where I was" state separate from permanent memory commits.

-- PART 1: SESSION_CHECKPOINTS TABLE
-- One row per task - UPSERT semantics for checkpointing
CREATE TABLE session_checkpoints (
  task_id UUID PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  instance_id TEXT,                           -- which agent instance created this checkpoint
  progress TEXT,                              -- human-readable progress description
  next_step TEXT,                             -- what to do next on resume
  context_snapshot JSONB DEFAULT '{}',        -- arbitrary context data
  checkpoint_at TIMESTAMPTZ DEFAULT NOW(),    -- when this checkpoint was created/updated
  expires_at TIMESTAMPTZ                      -- optional TTL for auto-cleanup
);

-- PART 2: INDEXES
CREATE INDEX idx_session_checkpoints_tenant ON session_checkpoints(tenant_id);
CREATE INDEX idx_session_checkpoints_instance ON session_checkpoints(tenant_id, instance_id);
CREATE INDEX idx_session_checkpoints_expires ON session_checkpoints(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_session_checkpoints_stale ON session_checkpoints(checkpoint_at);

-- PART 3: ROW LEVEL SECURITY
ALTER TABLE session_checkpoints ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON session_checkpoints
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- PART 4: AUTO-UPDATE TRIGGER
CREATE OR REPLACE FUNCTION update_session_checkpoint_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.checkpoint_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER session_checkpoint_timestamp_trigger
  BEFORE UPDATE ON session_checkpoints
  FOR EACH ROW
  EXECUTE FUNCTION update_session_checkpoint_timestamp();

-- PART 5: VERIFY
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'session_checkpoints';

-- PART 6: USAGE NOTES
--
-- Checkpoint (UPSERT):
--   INSERT INTO session_checkpoints (task_id, tenant_id, instance_id, progress, next_step, context_snapshot)
--   VALUES ($1, $2, $3, $4, $5, $6)
--   ON CONFLICT (task_id) DO UPDATE SET
--     instance_id = EXCLUDED.instance_id,
--     progress = EXCLUDED.progress,
--     next_step = EXCLUDED.next_step,
--     context_snapshot = EXCLUDED.context_snapshot;
--
-- Resume (get checkpoint if exists):
--   SELECT * FROM session_checkpoints WHERE task_id = $1 AND tenant_id = $2;
--
-- Clear checkpoint (on task completion):
--   DELETE FROM session_checkpoints WHERE task_id = $1;
--
-- Find orphaned checkpoints (crashed instances):
--   SELECT sc.*, t.status, t.description
--   FROM session_checkpoints sc
--   JOIN tasks t ON sc.task_id = t.id
--   WHERE sc.checkpoint_at < NOW() - INTERVAL '2 hours'
--   AND t.status NOT IN ('done', 'deleted');
