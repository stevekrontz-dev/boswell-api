#!/usr/bin/env python3
"""Run the Postgres schema for Boswell multi-tenant setup"""

import psycopg2

# Connection string from Railway (DATABASE_PUBLIC_URL format) with SSL
DATABASE_URL = "postgresql://postgres:TZZuQAjZiJZPwHojTDhwchCZmNVPbNXY@gondola.proxy.rlwy.net:13404/railway?sslmode=require"

# Define each SQL statement explicitly
STATEMENTS = [
    # PART 1: EXTENSIONS
    ('Enable uuid-ossp extension',
     'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'),

    # PART 2: TENANTS TABLE
    ('Create tenants table', '''
CREATE TABLE tenants (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(255) NOT NULL,
  domain VARCHAR(255) UNIQUE,
  settings JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
)'''),

    # PART 3: DEFAULT TENANT
    ('Insert default tenant',
     "INSERT INTO tenants (id, name, domain) VALUES ('00000000-0000-0000-0000-000000000001', 'Steve Krontz', 'default.local')"),

    # PART 4: DATA TABLES
    ('Create branches table', '''
CREATE TABLE branches (
  id SERIAL PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  name VARCHAR(255) NOT NULL,
  head_commit VARCHAR(64),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(tenant_id, name)
)'''),

    ('Create blobs table', '''
CREATE TABLE blobs (
  blob_hash VARCHAR(64) PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  content TEXT,
  content_type VARCHAR(50) DEFAULT 'memory',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  byte_size INTEGER
)'''),

    ('Create commits table', '''
CREATE TABLE commits (
  commit_hash VARCHAR(64) PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  tree_hash VARCHAR(64),
  parent_hash VARCHAR(64),
  author VARCHAR(255),
  message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
)'''),

    ('Create tree_entries table', '''
CREATE TABLE tree_entries (
  id SERIAL PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  tree_hash VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  blob_hash VARCHAR(64) NOT NULL,
  mode VARCHAR(20)
)'''),

    ('Create cross_references table', '''
CREATE TABLE cross_references (
  id SERIAL PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  source_blob VARCHAR(64),
  target_blob VARCHAR(64),
  source_branch VARCHAR(255),
  target_branch VARCHAR(255),
  link_type VARCHAR(50),
  weight FLOAT,
  reasoning TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
)'''),

    ('Create tags table', '''
CREATE TABLE tags (
  id SERIAL PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  blob_hash VARCHAR(64),
  tag VARCHAR(100),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(tenant_id, blob_hash, tag)
)'''),

    ('Create sessions table', '''
CREATE TABLE sessions (
  session_id VARCHAR(64) PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  branch VARCHAR(255),
  content TEXT,
  summary TEXT,
  synced_at TIMESTAMPTZ,
  status VARCHAR(50)
)'''),

    # PART 5: INDEXES
    ('Create branches tenant index', 'CREATE INDEX idx_branches_tenant ON branches(tenant_id)'),
    ('Create blobs tenant index', 'CREATE INDEX idx_blobs_tenant ON blobs(tenant_id)'),
    ('Create commits tenant index', 'CREATE INDEX idx_commits_tenant ON commits(tenant_id)'),
    ('Create tree_entries tenant index', 'CREATE INDEX idx_tree_entries_tenant ON tree_entries(tenant_id)'),
    ('Create cross_references tenant index', 'CREATE INDEX idx_cross_references_tenant ON cross_references(tenant_id)'),
    ('Create tags tenant index', 'CREATE INDEX idx_tags_tenant ON tags(tenant_id)'),
    ('Create sessions tenant index', 'CREATE INDEX idx_sessions_tenant ON sessions(tenant_id)'),

    # PART 6: ROW LEVEL SECURITY
    ('Enable RLS on branches', 'ALTER TABLE branches ENABLE ROW LEVEL SECURITY'),
    ('Enable RLS on blobs', 'ALTER TABLE blobs ENABLE ROW LEVEL SECURITY'),
    ('Enable RLS on commits', 'ALTER TABLE commits ENABLE ROW LEVEL SECURITY'),
    ('Enable RLS on tree_entries', 'ALTER TABLE tree_entries ENABLE ROW LEVEL SECURITY'),
    ('Enable RLS on cross_references', 'ALTER TABLE cross_references ENABLE ROW LEVEL SECURITY'),
    ('Enable RLS on tags', 'ALTER TABLE tags ENABLE ROW LEVEL SECURITY'),
    ('Enable RLS on sessions', 'ALTER TABLE sessions ENABLE ROW LEVEL SECURITY'),

    # PART 7: RLS POLICIES
    ('Create RLS policy on branches', "CREATE POLICY tenant_isolation ON branches USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"),
    ('Create RLS policy on blobs', "CREATE POLICY tenant_isolation ON blobs USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"),
    ('Create RLS policy on commits', "CREATE POLICY tenant_isolation ON commits USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"),
    ('Create RLS policy on tree_entries', "CREATE POLICY tenant_isolation ON tree_entries USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"),
    ('Create RLS policy on cross_references', "CREATE POLICY tenant_isolation ON cross_references USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"),
    ('Create RLS policy on tags', "CREATE POLICY tenant_isolation ON tags USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"),
    ('Create RLS policy on sessions', "CREATE POLICY tenant_isolation ON sessions USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"),
]

print("Connecting to Railway Postgres...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("Running schema...\n")
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

print(f"\nSchema execution complete! {success_count} succeeded, {error_count} errors")

# Verify tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
tables = cur.fetchall()
print(f"\nTables created: {[t[0] for t in tables]}")

# Verify tenant
if 'tenants' in [t[0] for t in tables]:
    cur.execute("SELECT COUNT(*) FROM tenants;")
    count = cur.fetchone()[0]
    print(f"Tenant count: {count}")

cur.close()
conn.close()
print("\nConnection closed.")
