-- Migration 003: API Keys for tenant authentication
-- Owner: CC1
-- Task: W1P3 - API Key Management (BLOCKING CC4)

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT key_hash_not_empty CHECK (key_hash != '')
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);

-- Enable RLS
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see their own keys
CREATE POLICY api_keys_user_access ON api_keys
    FOR ALL
    USING (user_id::text = current_setting('app.current_user', true));

-- Policy: tenant admin can see all tenant keys
CREATE POLICY api_keys_tenant_access ON api_keys
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

COMMENT ON TABLE api_keys IS 'API keys for programmatic access. Keys are hashed - plaintext shown once on creation.';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA256 hash of the API key. Original key never stored.';
