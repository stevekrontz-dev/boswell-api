#!/usr/bin/env python3
"""
Run migration 024: password_hash_v2 column on users table.

Lazy migration to Argon2id — see db/migrations/024_password_hash_v2.sql
for the full strategy note. No user data is rewritten by this migration;
the new column is added NULL and populated on subsequent logins by the
auth code (auth/__init__.py hash_password_v2 / verify_password).

Run with DATABASE_URL in env. Idempotent (IF NOT EXISTS guard).
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get('DATABASE_URL')


def main():
    if not DATABASE_URL:
        print("[ERROR] DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    print("[MIGRATE] Running 024_password_hash_v2.sql...")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        migration_path = os.path.join(os.path.dirname(__file__), 'db', 'migrations', '024_password_hash_v2.sql')
        with open(migration_path, 'r') as f:
            sql = f.read()

        cur.execute(sql)
        conn.commit()

        # Verify column exists
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'password_hash_v2'
        """)
        col = cur.fetchone()
        if col:
            print(f"[VERIFY] users.password_hash_v2 — type={col['data_type']} nullable={col['is_nullable']}")
        else:
            print("[ERROR] password_hash_v2 column not found after migration", file=sys.stderr)
            sys.exit(1)

        # Report coverage so we know the migration baseline
        cur.execute("SELECT COUNT(*) AS n FROM users")
        total = cur.fetchone()['n']
        cur.execute("SELECT COUNT(*) AS n FROM users WHERE password_hash_v2 IS NOT NULL")
        migrated = cur.fetchone()['n']
        print(f"[COVERAGE] {migrated}/{total} users on v2 (expected 0/N at first run)")

        print("[MIGRATE] 024_password_hash_v2.sql complete!")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}", file=sys.stderr)
        conn.rollback()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
