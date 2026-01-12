-- Migration: API Keys table for multi-tenant authentication
-- Run this after schema_postgres.sql

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash VARCHAR(64) NOT NULL,  -- SHA256 hash of the API key
    name VARCHAR(255),              -- Description of the key
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT unique_key_hash UNIQUE (key_hash)
);

-- Index for fast API key lookup
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);

-- Enable RLS
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- Policy: tenants can only see their own keys
CREATE POLICY api_keys_tenant_isolation ON api_keys
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant')::uuid);

COMMENT ON TABLE api_keys IS 'API keys for tenant authentication. Keys are stored as SHA256 hashes.';
