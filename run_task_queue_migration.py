#!/usr/bin/env python3
"""
Run task queue migration for multi-agent coordination.
Author: CC2
Context: Three-instance consensus session - foundation for boswell_startup v2 and boswell_dashboard
"""

import psycopg2
import hashlib
import sys

# Railway Postgres connection
DATABASE_URL = "postgresql://postgres:upJwGUEdZPdIWBkMZApoUKwpdcnxzQcY@gondola.proxy.rlwy.net:13404/railway?sslmode=require"

MIGRATION_SQL = """
-- TASK QUEUE SCHEMA FOR MULTI-AGENT COORDINATION

-- PART 1: STATUS ENUM
DO $$ BEGIN
    CREATE TYPE task_status AS ENUM ('open', 'claimed', 'blocked', 'done');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- PART 2: TASKS TABLE
CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  description TEXT NOT NULL,
  branch VARCHAR(255),
  assigned_to VARCHAR(255),
  status task_status DEFAULT 'open',
  priority INTEGER DEFAULT 5,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deadline TIMESTAMPTZ,
  metadata JSONB DEFAULT '{}'
);

-- PART 3: TASK_CLAIMS TABLE
CREATE TABLE IF NOT EXISTS task_claims (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
  instance_id VARCHAR(255) NOT NULL,
  claimed_at TIMESTAMPTZ DEFAULT NOW(),
  released_at TIMESTAMPTZ,
  release_reason VARCHAR(50)
);

-- PART 4: INDEXES (using IF NOT EXISTS pattern)
CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(tenant_id, assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_branch ON tasks(tenant_id, branch);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(tenant_id, priority, status);

CREATE INDEX IF NOT EXISTS idx_task_claims_tenant ON task_claims(tenant_id);
CREATE INDEX IF NOT EXISTS idx_task_claims_task ON task_claims(task_id);
CREATE INDEX IF NOT EXISTS idx_task_claims_instance ON task_claims(tenant_id, instance_id);

-- PART 5: ROW LEVEL SECURITY
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_claims ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist, then create
DROP POLICY IF EXISTS tenant_isolation ON tasks;
DROP POLICY IF EXISTS tenant_isolation ON task_claims;

CREATE POLICY tenant_isolation ON tasks
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY tenant_isolation ON task_claims
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- PART 6: UPDATED_AT TRIGGER
CREATE OR REPLACE FUNCTION update_tasks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tasks_updated_at_trigger ON tasks;
CREATE TRIGGER tasks_updated_at_trigger
  BEFORE UPDATE ON tasks
  FOR EACH ROW
  EXECUTE FUNCTION update_tasks_updated_at();
"""

def main():
    print("=" * 60)
    print("TASK QUEUE MIGRATION")
    print("=" * 60)

    # Calculate hash for Boswell documentation
    sql_hash = hashlib.sha256(MIGRATION_SQL.encode()).hexdigest()[:16]
    print(f"Migration SQL hash: {sql_hash}")

    try:
        print("\nConnecting to Railway Postgres...")
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Running migration...")
        cursor.execute(MIGRATION_SQL)

        # Verify tables exist
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN ('tasks', 'task_claims')
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        if 'tasks' in tables and 'task_claims' in tables:
            print("\n[SUCCESS] Tables created:")
            for t in tables:
                print(f"  - {t}")

            conn.commit()
            print("\nMigration committed successfully!")
            print(f"\nDocument in Boswell with hash: {sql_hash}")
        else:
            print("\n[ERROR] Expected tables not found!")
            conn.rollback()
            sys.exit(1)

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
