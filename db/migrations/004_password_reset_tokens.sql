-- Migration 004: Password Reset Tokens
-- Owner: CC1
-- Task: W1P4 - Password Reset

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() + INTERVAL '1 hour',
    used_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT token_hash_not_empty CHECK (token_hash != '')
);

-- Index for fast token lookup
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash ON password_reset_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id);

-- Cleanup: auto-delete expired tokens (can be run periodically)
-- DELETE FROM password_reset_tokens WHERE expires_at < NOW();

COMMENT ON TABLE password_reset_tokens IS 'Tokens for password reset flow. Tokens expire after 1 hour and are single-use.';
COMMENT ON COLUMN password_reset_tokens.token_hash IS 'SHA256 hash of the reset token. Original token sent via email, never stored.';
