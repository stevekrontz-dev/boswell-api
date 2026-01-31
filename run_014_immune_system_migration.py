#!/usr/bin/env python3
"""
Run migration 014: Immune System
Adds quarantine columns to blobs and creates immune_log table
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

    print("[MIGRATE] Running 014_immune_system.sql...")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Read and execute migration
        migration_path = os.path.join(os.path.dirname(__file__), 'db', 'migrations', '014_immune_system.sql')
        with open(migration_path, 'r') as f:
            sql = f.read()

        # Split on semicolons but preserve content
        # Execute statement by statement for better error reporting
        statements = [s.strip() for s in sql.split(';') if s.strip() and not s.strip().startswith('--')]

        for i, stmt in enumerate(statements):
            # Skip pure comment blocks
            lines = [l for l in stmt.split('\n') if l.strip() and not l.strip().startswith('--')]
            if not lines:
                continue
            try:
                cur.execute(stmt)
                print(f"  [OK] Statement {i+1}")
            except psycopg2.errors.DuplicateColumn as e:
                print(f"  [SKIP] Column already exists: {e.diag.message_primary}")
                conn.rollback()
            except psycopg2.errors.DuplicateTable as e:
                print(f"  [SKIP] Table already exists: {e.diag.message_primary}")
                conn.rollback()
            except psycopg2.errors.DuplicateObject as e:
                print(f"  [SKIP] Object already exists: {e.diag.message_primary}")
                conn.rollback()
            except Exception as e:
                print(f"  [WARN] Statement {i+1}: {e}")
                conn.rollback()

        conn.commit()

        # Verify
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'blobs' AND column_name LIKE 'quarantine%'
        """)
        quarantine_cols = [r['column_name'] for r in cur.fetchall()]
        print(f"[VERIFY] Quarantine columns: {quarantine_cols}")

        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'immune_log'
        """)
        immune_log_exists = cur.fetchone() is not None
        print(f"[VERIFY] immune_log table exists: {immune_log_exists}")

        print("[MIGRATE] 014_immune_system.sql complete!")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}", file=sys.stderr)
        conn.rollback()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
