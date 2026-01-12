-- TASK QUEUE SCHEMA FOR MULTI-AGENT COORDINATION
-- Migration: Add tasks and task_claims tables
-- Author: CC2 (Claude Code instance 2)
-- Context: Three-instance consensus session - foundation for boswell_startup v2 and boswell_dashboard

-- PART 1: STATUS ENUM
CREATE TYPE task_status AS ENUM ('open', 'claimed', 'blocked', 'done');

-- PART 2: TASKS TABLE
-- Central table for all agent tasks
CREATE TABLE tasks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  description TEXT NOT NULL,
  branch VARCHAR(255),                    -- cognitive branch context (command-center, tint-atlanta, etc.)
  assigned_to VARCHAR(255),               -- instance identifier (CC1, CC2, CW, etc.)
  status task_status DEFAULT 'open',
  priority INTEGER DEFAULT 5,             -- 1 = highest, 10 = lowest
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deadline TIMESTAMPTZ,                   -- optional deadline
  metadata JSONB DEFAULT '{}'             -- extensible for future fields
);

-- PART 3: TASK_CLAIMS TABLE
-- Tracks which instance claimed which task and when
-- Enables collision detection and work coordination
CREATE TABLE task_claims (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
  instance_id VARCHAR(255) NOT NULL,      -- which agent claimed it
  claimed_at TIMESTAMPTZ DEFAULT NOW(),
  released_at TIMESTAMPTZ,                -- NULL if still claimed
  release_reason VARCHAR(50),             -- 'completed', 'blocked', 'timeout', 'manual'
  UNIQUE(task_id, instance_id, claimed_at)
);

-- PART 4: INDEXES
-- Performance indexes matching existing patterns
CREATE INDEX idx_tasks_tenant ON tasks(tenant_id);
CREATE INDEX idx_tasks_status ON tasks(tenant_id, status);
CREATE INDEX idx_tasks_assigned ON tasks(tenant_id, assigned_to);
CREATE INDEX idx_tasks_branch ON tasks(tenant_id, branch);
CREATE INDEX idx_tasks_priority ON tasks(tenant_id, priority, status);

CREATE INDEX idx_task_claims_tenant ON task_claims(tenant_id);
CREATE INDEX idx_task_claims_task ON task_claims(task_id);
CREATE INDEX idx_task_claims_instance ON task_claims(tenant_id, instance_id);
CREATE INDEX idx_task_claims_active ON task_claims(task_id) WHERE released_at IS NULL;

-- PART 5: ROW LEVEL SECURITY
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_claims ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tasks
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY tenant_isolation ON task_claims
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- PART 6: UPDATED_AT TRIGGER
-- Auto-update updated_at on tasks table
CREATE OR REPLACE FUNCTION update_tasks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tasks_updated_at_trigger
  BEFORE UPDATE ON tasks
  FOR EACH ROW
  EXECUTE FUNCTION update_tasks_updated_at();

-- PART 7: VERIFY
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('tasks', 'task_claims');
-- Should return 2 tables

-- PART 8: SAMPLE QUERIES FOR AGENTS
--
-- Get open tasks for an instance:
--   SELECT * FROM tasks WHERE assigned_to = 'CC2' AND status = 'open' ORDER BY priority, created_at;
--
-- Claim a task:
--   UPDATE tasks SET status = 'claimed' WHERE id = $1;
--   INSERT INTO task_claims (task_id, instance_id) VALUES ($1, 'CC2');
--
-- Complete a task:
--   UPDATE tasks SET status = 'done' WHERE id = $1;
--   UPDATE task_claims SET released_at = NOW(), release_reason = 'completed' WHERE task_id = $1 AND released_at IS NULL;
--
-- Find collision (task claimed by multiple):
--   SELECT task_id, COUNT(*) FROM task_claims WHERE released_at IS NULL GROUP BY task_id HAVING COUNT(*) > 1;
