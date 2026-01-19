#!/usr/bin/env python3
"""
Run the Session Checkpoints migration for Boswell.
Creates table for crash recovery / ephemeral state tracking.

Usage:
    DATABASE_URL=<url> python run_011_session_checkpoints_migration.py

Or set DATABASE_URL in environment and run directly.
"""

import os
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    print("Set it with: export DATABASE_URL='postgresql://...'")
    exit(1)

STATEMENTS = [
    ('Create session_checkpoints table', '''
CREATE TABLE IF NOT EXISTS session_checkpoints (
    task_id UUID PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
    instance_id TEXT,
    progress TEXT,
    next_step TEXT,
    context_snapshot JSONB DEFAULT '{}',
    checkpoint_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
)'''),

    ('Create tenant index',
     'CREATE INDEX IF NOT EXISTS idx_session_checkpoints_tenant ON session_checkpoints(tenant_id)'),

    ('Create instance index',
     'CREATE INDEX IF NOT EXISTS idx_session_checkpoints_instance ON session_checkpoints(tenant_id, instance_id)'),

    ('Create expires index',
     'CREATE INDEX IF NOT EXISTS idx_session_checkpoints_expires ON session_checkpoints(expires_at) WHERE expires_at IS NOT NULL'),

    ('Create stale checkpoint index',
     'CREATE INDEX IF NOT EXISTS idx_session_checkpoints_stale ON session_checkpoints(checkpoint_at)'),

    ('Enable Row Level Security',
     'ALTER TABLE session_checkpoints ENABLE ROW LEVEL SECURITY'),

    ('Create RLS policy', '''
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'session_checkpoints' AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON session_checkpoints
            USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
    END IF;
END $$;
'''),

    ('Create timestamp trigger function', '''
CREATE OR REPLACE FUNCTION update_session_checkpoint_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.checkpoint_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
'''),

    ('Create timestamp trigger', '''
DROP TRIGGER IF EXISTS session_checkpoint_timestamp_trigger ON session_checkpoints;
CREATE TRIGGER session_checkpoint_timestamp_trigger
    BEFORE UPDATE ON session_checkpoints
    FOR EACH ROW
    EXECUTE FUNCTION update_session_checkpoint_timestamp();
'''),
]

print("Connecting to Railway Postgres...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("Running session checkpoints migration...\n")
success_count = 0
error_count = 0

for desc, sql in STATEMENTS:
    print(f"  {desc}...", end=" ")
    try:
        cur.execute(sql)
        print("OK")
        success_count += 1
    except Exception as e:
        print(f"ERROR: {e}")
        error_count += 1

print(f"\nMigration complete! {success_count} succeeded, {error_count} errors")

# Verify table exists
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'session_checkpoints';
""")
tables = cur.fetchall()
if tables:
    print(f"Session checkpoints table: {tables[0][0]} - CREATED")
else:
    print("WARNING: session_checkpoints table not found!")

cur.close()
conn.close()
print("Connection closed.")
