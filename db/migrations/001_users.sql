-- Migration 001: Users table for SaaS authentication
-- Owner: CC1
-- Task: W1P1 - User Registration

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    email_verified_at TIMESTAMP WITH TIME ZONE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,

    CONSTRAINT email_lowercase CHECK (email = LOWER(email))
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at);

-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see their own data
CREATE POLICY users_self_access ON users
    FOR ALL
    USING (id::text = current_setting('app.current_user', true));

-- Policy: admin access via tenant
CREATE POLICY users_tenant_admin ON users
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

COMMENT ON TABLE users IS 'User accounts for Boswell SaaS. Supports multi-tenancy.';
COMMENT ON COLUMN users.password_hash IS 'SHA256 hash with salt in format salt:hash';
