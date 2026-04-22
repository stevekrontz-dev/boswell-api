#!/usr/bin/env python3
"""
Run migration 028: plan_closeout lookup + unique idempotency indexes.

Supports boswell_update_plan — plans' effective lifecycle status now lives
on the newest plan_closeout memory per blob_hash (within tenant), not in a
sidecar table. See db/migrations/028_plan_closeout_lookup.sql for the full
design note.

The SQL file includes a DO block that aborts if any tenant already has
duplicate plan_closeout tuples on (tenant_id, plan_blob, type, status). If
the migration raises that exception, reconcile (silt older dupes, keep
newest) before retrying.

Run with DATABASE_URL in env. Idempotent (IF NOT EXISTS guards).
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

    print("[MIGRATE] Running 028_plan_closeout_lookup.sql...")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        migration_path = os.path.join(os.path.dirname(__file__), 'db', 'migrations', '028_plan_closeout_lookup.sql')
        with open(migration_path, 'r') as f:
            sql = f.read()

        cur.execute(sql)
        conn.commit()

        # Verify both indexes exist.
        cur.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'blobs'
              AND indexname IN ('idx_plan_closeout_lookup', 'uq_plan_closeout_idempotent')
            ORDER BY indexname
        """)
        rows = cur.fetchall()
        if len(rows) != 2:
            print(f"[ERROR] Expected 2 indexes, found {len(rows)}", file=sys.stderr)
            for row in rows:
                print(f"  - {row['indexname']}")
            sys.exit(1)
        for row in rows:
            print(f"[VERIFY] {row['indexname']}")

        # Report closeout coverage so we have a baseline.
        cur.execute("""
            SELECT COUNT(*) AS n
            FROM blobs
            WHERE content_type = 'memory'
              AND safe_jsonb_field(content, 'type') = 'plan_closeout'
        """)
        closeouts = cur.fetchone()['n']
        cur.execute("""
            SELECT COUNT(DISTINCT content::jsonb->>'plan_blob') AS n
            FROM blobs
            WHERE content_type = 'memory'
              AND safe_jsonb_field(content, 'type') = 'plan_closeout'
        """)
        distinct_plans = cur.fetchone()['n']
        print(f"[COVERAGE] {closeouts} plan_closeout memories covering {distinct_plans} distinct plans")

        print("[MIGRATE] 028_plan_closeout_lookup.sql complete!")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}", file=sys.stderr)
        conn.rollback()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
