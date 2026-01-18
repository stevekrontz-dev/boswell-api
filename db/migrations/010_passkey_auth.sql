-- Migration: Passkey Authentication Tables (WebAuthn / Face ID)
-- Author: CC1
-- Context: WebAuthn backend implementation for Face ID login

-- Stores registered passkey credentials (Face ID, Touch ID, etc.)
CREATE TABLE IF NOT EXISTS passkey_credentials (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    credential_id BYTEA NOT NULL UNIQUE,
    public_key BYTEA NOT NULL,
    device_type VARCHAR(50) DEFAULT 'platform',
    backed_up BOOLEAN DEFAULT FALSE,
    transports TEXT[] DEFAULT ARRAY['internal'],
    friendly_name VARCHAR(255) DEFAULT 'My Passkey',
    counter INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_passkey_credentials_user ON passkey_credentials(user_id);

-- Stores temporary challenges for WebAuthn ceremonies
CREATE TABLE IF NOT EXISTS passkey_challenges (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    challenge BYTEA NOT NULL,
    type VARCHAR(50) NOT NULL, -- 'registration' or 'authentication'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '5 minutes'
);

CREATE INDEX IF NOT EXISTS idx_passkey_challenges_user ON passkey_challenges(user_id);

-- Auto-cleanup expired challenges
CREATE INDEX IF NOT EXISTS idx_passkey_challenges_expires ON passkey_challenges(expires_at);

-- Stores active sessions
CREATE TABLE IF NOT EXISTS passkey_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    token VARCHAR(128) NOT NULL UNIQUE,
    user_agent TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);

CREATE INDEX IF NOT EXISTS idx_passkey_sessions_token ON passkey_sessions(token);
CREATE INDEX IF NOT EXISTS idx_passkey_sessions_user ON passkey_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_passkey_sessions_expires ON passkey_sessions(expires_at);
