-- POSTGRES SCHEMA FOR BOSWELL MULTI-TENANT
-- Run these statements in order

-- PART 1: EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- PART 2: TENANTS TABLE
CREATE TABLE tenants (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(255) NOT NULL,
  domain VARCHAR(255) UNIQUE,
  settings JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- PART 3: DEFAULT TENANT
INSERT INTO tenants (id, name, domain) VALUES ('00000000-0000-0000-0000-000000000001', 'Steve Krontz', 'default.local');

-- PART 4: DATA TABLES
CREATE TABLE branches (
  id SERIAL PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  name VARCHAR(255) NOT NULL,
  head_commit VARCHAR(64),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(tenant_id, name)
);

CREATE TABLE blobs (
  blob_hash VARCHAR(64) PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  content TEXT,
  content_type VARCHAR(50) DEFAULT 'memory',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  byte_size INTEGER
);

CREATE TABLE commits (
  commit_hash VARCHAR(64) PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  tree_hash VARCHAR(64),
  parent_hash VARCHAR(64),
  author VARCHAR(255),
  message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tree_entries (
  id SERIAL PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  tree_hash VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  blob_hash VARCHAR(64) NOT NULL,
  mode VARCHAR(20)
);

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
);

CREATE TABLE tags (
  id SERIAL PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  blob_hash VARCHAR(64),
  tag VARCHAR(100),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(tenant_id, name)
);

CREATE TABLE sessions (
  session_id VARCHAR(64) PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
  branch VARCHAR(255),
  content TEXT,
  summary TEXT,
  synced_at TIMESTAMPTZ,
  status VARCHAR(50)
);

-- PART 4B: BILLING TABLES (W2P3)
CREATE TABLE subscriptions (
  id SERIAL PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id) UNIQUE,
  stripe_customer_id VARCHAR(255),
  stripe_subscription_id VARCHAR(255) UNIQUE,
  plan_id VARCHAR(50) NOT NULL DEFAULT 'free',
  status VARCHAR(50) NOT NULL DEFAULT 'active',
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  canceled_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- PART 5: INDEXES
CREATE INDEX idx_branches_tenant ON branches(tenant_id);
CREATE INDEX idx_blobs_tenant ON blobs(tenant_id);
CREATE INDEX idx_commits_tenant ON commits(tenant_id);
CREATE INDEX idx_tree_entries_tenant ON tree_entries(tenant_id);
CREATE INDEX idx_cross_references_tenant ON cross_references(tenant_id);
CREATE INDEX idx_tags_tenant ON tags(tenant_id);
CREATE INDEX idx_sessions_tenant ON sessions(tenant_id);
CREATE INDEX idx_subscriptions_tenant ON subscriptions(tenant_id);

-- PART 6: ROW LEVEL SECURITY
ALTER TABLE branches ENABLE ROW LEVEL SECURITY;
ALTER TABLE blobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE commits ENABLE ROW LEVEL SECURITY;
ALTER TABLE tree_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE cross_references ENABLE ROW LEVEL SECURITY;
ALTER TABLE tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON branches USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY tenant_isolation ON blobs USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY tenant_isolation ON commits USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY tenant_isolation ON tree_entries USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY tenant_isolation ON cross_references USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY tenant_isolation ON tags USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY tenant_isolation ON sessions USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY tenant_isolation ON subscriptions USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- PART 7: VERIFY
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
-- Should return 8 tables: tenants, branches, blobs, commits, tree_entries, cross_references, tags, sessions
-- SELECT COUNT(*) FROM tenants;
-- Should return 1
