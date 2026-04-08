#!/usr/bin/env python3
"""
Run migration 022 — Commit Agent source tag.

Adds cross_references.source column (default 'manual') and a partial index
for fast filtering of auto-created supersession links.

Plan B (Commit Agent v1.0) requires this column before its decision tree
can auto-create supersession links with guard rail #1 in place.

Plan source: bf298d68 / 2f947c3a / 552c7205 (Boswell)
Plan file: C:\\Users\\Steve\\.claude\\plans\\keen-watching-kettle.md

Usage:
    DATABASE_URL=<url> python run_022_commit_agent_source_migration.py

The migration is idempotent — safe to run multiple times.
"""

import os
import sys
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
    sys.exit(1)

# Two phases:
#   1. ADD COLUMN inside a transaction (fast, atomic)
#   2. CREATE INDEX CONCURRENTLY outside a transaction (no table lock)
ADD_COLUMN_SQL = """
ALTER TABLE cross_references
    ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'manual';
"""

CREATE_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cross_references_source
    ON cross_references(source)
    WHERE source != 'manual';
"""

print("Connecting to Postgres...")
conn = psycopg2.connect(DATABASE_URL)

print("Phase 1: ADD COLUMN cross_references.source (transactional)...")
try:
    cur = conn.cursor()
    cur.execute(ADD_COLUMN_SQL)
    conn.commit()
    cur.close()
    print("  OK")
except Exception as e:
    print(f"  ERROR: {e}", file=sys.stderr)
    conn.rollback()
    conn.close()
    sys.exit(1)

print("Phase 2: CREATE INDEX CONCURRENTLY (no table lock)...")
try:
    conn.autocommit = True  # CONCURRENTLY cannot run inside a transaction
    cur = conn.cursor()
    cur.execute(CREATE_INDEX_SQL)
    cur.close()
    print("  OK")
except Exception as e:
    # Index creation failures are non-fatal — the column itself is what's
    # required for guard rail #1. Index is a perf optimization.
    print(f"  WARNING (non-fatal): {e}", file=sys.stderr)

# Verify
print("\nVerification:")
conn.autocommit = False
cur = conn.cursor()
cur.execute("""
    SELECT column_name, data_type, column_default
    FROM information_schema.columns
    WHERE table_name = 'cross_references' AND column_name = 'source';
""")
row = cur.fetchone()
if row:
    print(f"  cross_references.source: {row[1]} DEFAULT {row[2]}")
else:
    print("  ERROR: source column not found", file=sys.stderr)
    cur.close()
    conn.close()
    sys.exit(1)

cur.execute("""
    SELECT indexname FROM pg_indexes
    WHERE tablename = 'cross_references' AND indexname = 'idx_cross_references_source';
""")
if cur.fetchone():
    print("  idx_cross_references_source: present")
else:
    print("  idx_cross_references_source: NOT present (non-fatal)")

cur.close()
conn.close()
print("\nMigration 022 complete.")
