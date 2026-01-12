-- PASSKEY CREDENTIALS SCHEMA FOR WEBAUTHN AUTHENTICATION
-- Migration: Add passkey_credentials table for Face ID / Passkey login
-- Author: CC2
-- Context: Swarm task beta-4 - God Mode dashboard passkey authentication

-- PART 1: PASSKEY CREDENTIALS TABLE
CREATE TABLE IF NOT EXISTS passkey_credentials (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id VARCHAR(255) NOT NULL,           -- username or email
  credential_id BYTEA NOT NULL UNIQUE,     -- WebAuthn credential ID
  public_key BYTEA NOT NULL,               -- credential public key
  counter INTEGER DEFAULT 0,               -- signature counter for replay protection
  device_type VARCHAR(50),                 -- 'singleDevice' or 'multiDevice'
  backed_up BOOLEAN DEFAULT FALSE,         -- whether credential is backed up
  transports TEXT[],                       -- array of transports (usb, ble, nfc, internal)
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_used_at TIMESTAMPTZ,
  friendly_name VARCHAR(255)               -- e.g. "Steve's iPhone", "MacBook Pro"
);

-- PART 2: USER CHALLENGES TABLE (for registration/auth flow)
CREATE TABLE IF NOT EXISTS passkey_challenges (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id VARCHAR(255),
  challenge BYTEA NOT NULL,
  type VARCHAR(20) NOT NULL,               -- 'registration' or 'authentication'
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '5 minutes'
);

-- PART 3: SESSIONS TABLE
CREATE TABLE IF NOT EXISTS passkey_sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id VARCHAR(255) NOT NULL,
  token VARCHAR(255) NOT NULL UNIQUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days',
  user_agent TEXT,
  ip_address VARCHAR(45)
);

-- PART 4: INDEXES
CREATE INDEX IF NOT EXISTS idx_passkey_credentials_user ON passkey_credentials(user_id);
CREATE INDEX IF NOT EXISTS idx_passkey_credentials_credential_id ON passkey_credentials(credential_id);
CREATE INDEX IF NOT EXISTS idx_passkey_challenges_user ON passkey_challenges(user_id);
CREATE INDEX IF NOT EXISTS idx_passkey_challenges_expires ON passkey_challenges(expires_at);
CREATE INDEX IF NOT EXISTS idx_passkey_sessions_token ON passkey_sessions(token);
CREATE INDEX IF NOT EXISTS idx_passkey_sessions_expires ON passkey_sessions(expires_at);

-- PART 5: CLEANUP FUNCTION FOR EXPIRED CHALLENGES
CREATE OR REPLACE FUNCTION cleanup_expired_challenges()
RETURNS void AS $$
BEGIN
  DELETE FROM passkey_challenges WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

-- PART 6: CLEANUP FUNCTION FOR EXPIRED SESSIONS
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void AS $$
BEGIN
  DELETE FROM passkey_sessions WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;
