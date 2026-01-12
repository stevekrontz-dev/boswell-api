#!/usr/bin/env python3
"""
Phase 3 Migration: Add audit logging to Boswell
1. Run schema changes (create audit_logs table)
2. Verify table and indexes created
3. Test audit logging

Run with:
  DATABASE_URL='postgresql://...' python run_phase3_migration.py
"""

import os
import sys
import psycopg2

# Configuration - use environment variable
POSTGRES_URL = os.environ.get('DATABASE_URL')
if not POSTGRES_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    print("Set it with: export DATABASE_URL='postgresql://...'")
    sys.exit(1)

DEFAULT_TENANT = '00000000-0000-0000-0000-000000000001'


def run_schema_migration(conn):
    """Run the Phase 3 schema changes"""
    print("\n[1/3] Running schema migration...")

    cur = conn.cursor()

    # Read and execute migration SQL
    migration_path = os.path.join(os.path.dirname(__file__), 'migration_phase3_audit_logs.sql')

    if os.path.exists(migration_path):
        print(f"  Reading migration from {migration_path}")
        with open(migration_path, 'r') as f:
            sql = f.read()

        # Execute each statement separately (skip comments)
        statements = []
        current = []
        for line in sql.split('\n'):
            stripped = line.strip()
            if stripped.startswith('--') or not stripped:
                continue
            current.append(line)
            if stripped.endswith(';'):
                statements.append('\n'.join(current))
                current = []

        for stmt in statements:
            if stmt.strip():
                try:
                    cur.execute(stmt)
                    # Extract first meaningful line for logging
                    first_line = stmt.strip().split('\n')[0][:60]
                    print(f"  OK: {first_line}...")
                except Exception as e:
                    if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                        print(f"  SKIP: Already exists")
                    else:
                        print(f"  WARN: {e}")
    else:
        # Fallback: create table directly
        print("  Migration file not found, creating table directly...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                tenant_id UUID NOT NULL REFERENCES tenants(id),
                user_id UUID,
                api_key_id UUID,
                action VARCHAR(50) NOT NULL,
                resource_type VARCHAR(50) NOT NULL,
                resource_id VARCHAR(255),
                request_metadata JSONB DEFAULT '{}',
                response_status INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print("  Created audit_logs table")

    conn.commit()
    cur.close()
    print("  Schema migration complete!")


def verify_migration(conn):
    """Verify migration was successful"""
    print("\n[2/3] Verifying migration...")

    cur = conn.cursor()

    # Check table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'audit_logs'
        )
    """)
    table_exists = cur.fetchone()[0]
    print(f"  audit_logs table exists: {table_exists}")

    if not table_exists:
        cur.close()
        print("\n*** MIGRATION FAILED: audit_logs table not created ***")
        return False

    # Check column count
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_name = 'audit_logs'
    """)
    column_count = cur.fetchone()[0]
    print(f"  Column count: {column_count}")

    # Check indexes
    cur.execute("""
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'audit_logs'
    """)
    indexes = [row[0] for row in cur.fetchall()]
    print(f"  Indexes created: {len(indexes)}")
    for idx in indexes:
        print(f"    - {idx}")

    # Check RLS is enabled
    cur.execute("""
        SELECT relrowsecurity
        FROM pg_class
        WHERE relname = 'audit_logs'
    """)
    rls_enabled = cur.fetchone()[0]
    print(f"  Row Level Security enabled: {rls_enabled}")

    cur.close()
    return True


def test_audit_logging(conn):
    """Test audit logging by inserting a test record"""
    print("\n[3/3] Testing audit logging...")

    cur = conn.cursor()

    # Set tenant context
    cur.execute(f"SET app.current_tenant = '{DEFAULT_TENANT}'")

    # Insert test audit log
    try:
        cur.execute("""
            INSERT INTO audit_logs
            (tenant_id, action, resource_type, resource_id, response_status, duration_ms, request_metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            DEFAULT_TENANT,
            'MIGRATION_TEST',
            'test',
            'phase3_migration',
            200,
            1,
            '{"test": true, "phase": 3}'
        ))
        test_id = cur.fetchone()[0]
        print(f"  Test audit log created: {test_id}")
        conn.commit()

        # Verify we can read it back
        cur.execute("SELECT COUNT(*) FROM audit_logs WHERE tenant_id = %s", (DEFAULT_TENANT,))
        count = cur.fetchone()[0]
        print(f"  Total audit logs for tenant: {count}")

    except Exception as e:
        print(f"  ERROR: {e}")
        conn.rollback()
        cur.close()
        return False

    cur.close()
    return True


def main():
    print("=" * 60)
    print("BOSWELL PHASE 3: AUDIT LOGGING MIGRATION")
    print("=" * 60)

    # Connect to Postgres
    print("\nConnecting to Postgres...")
    conn = psycopg2.connect(POSTGRES_URL)
    conn.autocommit = False
    print("  Connected!")

    try:
        # Run migration steps
        run_schema_migration(conn)

        if verify_migration(conn):
            if test_audit_logging(conn):
                print("\n" + "=" * 60)
                print("*** PHASE 3 MIGRATION SUCCESSFUL ***")
                print("=" * 60)
                print("\nNext steps:")
                print("1. Push changes to GitHub")
                print("2. Railway will auto-deploy")
                print("3. Audit logging will start automatically")
                print("\nAPI endpoints available:")
                print("  GET /v2/audit - Query audit logs")
                print("  GET /v2/audit/stats - Get statistics")
            else:
                print("\n*** MIGRATION TEST FAILED ***")
        else:
            print("\n*** MIGRATION VERIFICATION FAILED ***")

    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
        print("\nConnection closed.")


if __name__ == '__main__':
    main()
