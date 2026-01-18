#!/usr/bin/env python3
"""
Run the Passkey Authentication migration for Boswell.
Creates tables for WebAuthn/Face ID login.

Usage:
    DATABASE_URL=<url> python run_010_passkey_migration.py

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
    ('Create passkey_credentials table', '''
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
)'''),

    ('Create passkey_credentials user index',
     'CREATE INDEX IF NOT EXISTS idx_passkey_credentials_user ON passkey_credentials(user_id)'),

    ('Create passkey_challenges table', '''
CREATE TABLE IF NOT EXISTS passkey_challenges (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    challenge BYTEA NOT NULL,
    type VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '5 minutes'
)'''),

    ('Create passkey_challenges user index',
     'CREATE INDEX IF NOT EXISTS idx_passkey_challenges_user ON passkey_challenges(user_id)'),

    ('Create passkey_challenges expires index',
     'CREATE INDEX IF NOT EXISTS idx_passkey_challenges_expires ON passkey_challenges(expires_at)'),

    ('Create passkey_sessions table', '''
CREATE TABLE IF NOT EXISTS passkey_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    token VARCHAR(128) NOT NULL UNIQUE,
    user_agent TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
)'''),

    ('Create passkey_sessions token index',
     'CREATE INDEX IF NOT EXISTS idx_passkey_sessions_token ON passkey_sessions(token)'),

    ('Create passkey_sessions user index',
     'CREATE INDEX IF NOT EXISTS idx_passkey_sessions_user ON passkey_sessions(user_id)'),

    ('Create passkey_sessions expires index',
     'CREATE INDEX IF NOT EXISTS idx_passkey_sessions_expires ON passkey_sessions(expires_at)'),
]

print("Connecting to Railway Postgres...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("Running passkey authentication migration...\n")
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

# Verify tables exist
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name LIKE 'passkey%'
    ORDER BY table_name;
""")
tables = cur.fetchall()
print(f"Passkey tables: {[t[0] for t in tables]}")

cur.close()
conn.close()
print("Connection closed.")
