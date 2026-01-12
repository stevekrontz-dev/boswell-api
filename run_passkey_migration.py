#!/usr/bin/env python3
"""
Run passkey credentials migration for WebAuthn authentication.
Author: CC2
Context: Swarm task beta-4 - God Mode dashboard passkey authentication
"""

import psycopg2
import sys

# Railway Postgres connection
DATABASE_URL = "postgresql://postgres:upJwGUEdZPdIWBkMZApoUKwpdcnxzQcY@gondola.proxy.rlwy.net:13404/railway?sslmode=require"

MIGRATION_SQL = """
-- PASSKEY CREDENTIALS SCHEMA FOR WEBAUTHN AUTHENTICATION

-- PART 1: PASSKEY CREDENTIALS TABLE
CREATE TABLE IF NOT EXISTS passkey_credentials (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id VARCHAR(255) NOT NULL,
  credential_id BYTEA NOT NULL UNIQUE,
  public_key BYTEA NOT NULL,
  counter INTEGER DEFAULT 0,
  device_type VARCHAR(50),
  backed_up BOOLEAN DEFAULT FALSE,
  transports TEXT[],
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_used_at TIMESTAMPTZ,
  friendly_name VARCHAR(255)
);

-- PART 2: USER CHALLENGES TABLE
CREATE TABLE IF NOT EXISTS passkey_challenges (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id VARCHAR(255),
  challenge BYTEA NOT NULL,
  type VARCHAR(20) NOT NULL,
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

-- PART 5: CLEANUP FUNCTIONS
CREATE OR REPLACE FUNCTION cleanup_expired_challenges()
RETURNS void AS $$
BEGIN
  DELETE FROM passkey_challenges WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void AS $$
BEGIN
  DELETE FROM passkey_sessions WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;
"""

def main():
    print("=" * 60)
    print("PASSKEY CREDENTIALS MIGRATION")
    print("=" * 60)

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
            WHERE table_schema = 'public'
            AND table_name IN ('passkey_credentials', 'passkey_challenges', 'passkey_sessions')
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        if len(tables) == 3:
            print("\n[SUCCESS] Tables created:")
            for t in tables:
                print(f"  - {t}")
            conn.commit()
            print("\nMigration committed successfully!")
        else:
            print(f"\n[ERROR] Expected 3 tables, found {len(tables)}")
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
