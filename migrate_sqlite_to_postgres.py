#!/usr/bin/env python3
"""
Migrate Boswell data from SQLite to Postgres
Handles schema differences and adds tenant_id to all records
"""

import sqlite3
import psycopg2

# Constants
SQLITE_PATH = 'C:/dev/infrastructure/boswell-api-repo/boswell_v2.db'
POSTGRES_URL = "postgresql://postgres:TZZuQAjZiJZPwHojTDhwchCZmNVPbNXY@gondola.proxy.rlwy.net:13404/railway?sslmode=require"
DEFAULT_TENANT = '00000000-0000-0000-0000-000000000001'

# Migration order (respects foreign key dependencies)
# Note: Some tables have schema differences between SQLite and Postgres

def migrate():
    print("=" * 60)
    print("BOSWELL SQLITE -> POSTGRES MIGRATION")
    print("=" * 60)

    # Connect to both databases
    print("\nConnecting to SQLite...")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    print("Connecting to Postgres...")
    pg_conn = psycopg2.connect(POSTGRES_URL)
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor()

    # Set tenant context for RLS
    print(f"Setting tenant context to {DEFAULT_TENANT}...")
    pg_cur.execute(f"SET app.current_tenant = '{DEFAULT_TENANT}'")

    results = {}

    # 1. BLOBS - Direct mapping (add tenant_id)
    print("\n[1/7] Migrating blobs...")
    sqlite_cur.execute("SELECT blob_hash, content, content_type, created_at, byte_size FROM blobs")
    rows = sqlite_cur.fetchall()
    count = 0
    for row in rows:
        try:
            pg_cur.execute("""
                INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (blob_hash) DO NOTHING
            """, (row['blob_hash'], DEFAULT_TENANT, row['content'], row['content_type'],
                  row['created_at'], row['byte_size']))
            count += 1
        except Exception as e:
            print(f"  Error on blob {row['blob_hash'][:8]}...: {e}")
    results['blobs'] = count
    print(f"  Migrated {count} blobs")

    # 2. COMMITS - Direct mapping (add tenant_id)
    print("\n[2/7] Migrating commits...")
    sqlite_cur.execute("SELECT commit_hash, tree_hash, parent_hash, author, message, created_at FROM commits")
    rows = sqlite_cur.fetchall()
    count = 0
    for row in rows:
        try:
            pg_cur.execute("""
                INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (commit_hash) DO NOTHING
            """, (row['commit_hash'], DEFAULT_TENANT, row['tree_hash'], row['parent_hash'],
                  row['author'], row['message'], row['created_at']))
            count += 1
        except Exception as e:
            print(f"  Error on commit {row['commit_hash'][:8]}...: {e}")
    results['commits'] = count
    print(f"  Migrated {count} commits")

    # 3. TREE_ENTRIES - Direct mapping (add tenant_id, skip id)
    print("\n[3/7] Migrating tree_entries...")
    sqlite_cur.execute("SELECT tree_hash, name, blob_hash, mode FROM tree_entries")
    rows = sqlite_cur.fetchall()
    count = 0
    for row in rows:
        try:
            pg_cur.execute("""
                INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
                VALUES (%s, %s, %s, %s, %s)
            """, (DEFAULT_TENANT, row['tree_hash'], row['name'], row['blob_hash'], row['mode']))
            count += 1
        except Exception as e:
            print(f"  Error on tree_entry: {e}")
    results['tree_entries'] = count
    print(f"  Migrated {count} tree_entries")

    # 4. BRANCHES - Schema differs (SQLite has vector_index_path, description; Postgres doesn't)
    print("\n[4/7] Migrating branches...")
    sqlite_cur.execute("SELECT name, head_commit, created_at FROM branches")
    rows = sqlite_cur.fetchall()
    count = 0
    for row in rows:
        try:
            pg_cur.execute("""
                INSERT INTO branches (tenant_id, name, head_commit, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, name) DO UPDATE SET head_commit = EXCLUDED.head_commit
            """, (DEFAULT_TENANT, row['name'], row['head_commit'], row['created_at']))
            count += 1
        except Exception as e:
            print(f"  Error on branch {row['name']}: {e}")
    results['branches'] = count
    print(f"  Migrated {count} branches")

    # 5. CROSS_REFERENCES - Direct mapping (add tenant_id, skip created_by)
    print("\n[5/7] Migrating cross_references...")
    sqlite_cur.execute("""
        SELECT source_blob, target_blob, source_branch, target_branch,
               link_type, weight, reasoning, created_at
        FROM cross_references
    """)
    rows = sqlite_cur.fetchall()
    count = 0
    for row in rows:
        try:
            pg_cur.execute("""
                INSERT INTO cross_references (tenant_id, source_blob, target_blob, source_branch,
                                              target_branch, link_type, weight, reasoning, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (DEFAULT_TENANT, row['source_blob'], row['target_blob'], row['source_branch'],
                  row['target_branch'], row['link_type'], row['weight'], row['reasoning'], row['created_at']))
            count += 1
        except Exception as e:
            print(f"  Error on cross_reference: {e}")
    results['cross_references'] = count
    print(f"  Migrated {count} cross_references")

    # 6. TAGS - Schema differs significantly
    # SQLite: (name, commit_hash, created_at)
    # Postgres: (id, tenant_id, blob_hash, tag, created_at)
    # Need to map commit_hash -> blob_hash (via commits table)
    print("\n[6/7] Migrating tags...")
    print("  Note: Tags schema differs - mapping commit_hash to blob (via tree_hash)")
    sqlite_cur.execute("SELECT name, commit_hash, created_at FROM tags")
    rows = sqlite_cur.fetchall()
    count = 0
    skipped = 0
    for row in rows:
        # Try to find blob_hash from commit's tree
        sqlite_cur.execute("""
            SELECT te.blob_hash FROM tree_entries te
            JOIN commits c ON te.tree_hash = c.tree_hash
            WHERE c.commit_hash = ?
            LIMIT 1
        """, (row['commit_hash'],))
        blob_row = sqlite_cur.fetchone()
        if blob_row:
            try:
                pg_cur.execute("""
                    INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
                    VALUES (%s, %s, %s, %s)
                """, (DEFAULT_TENANT, blob_row['blob_hash'], row['name'], row['created_at']))
                count += 1
            except Exception as e:
                print(f"  Error on tag {row['name']}: {e}")
                skipped += 1
        else:
            skipped += 1
    results['tags'] = count
    print(f"  Migrated {count} tags (skipped {skipped} without blob mapping)")

    # 7. SESSIONS - Schema differs completely, skip for now
    print("\n[7/7] Migrating sessions...")
    print("  Note: Sessions schema differs significantly - skipping")
    print("  SQLite schema: id, source, project, session_start, session_end, etc.")
    print("  Postgres schema: session_id, tenant_id, branch, content, summary, etc.")
    results['sessions'] = 0

    # Summary
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print("\nResults:")
    for table, count in results.items():
        print(f"  {table}: {count} rows")

    # Verify in Postgres
    print("\nVerifying Postgres row counts:")
    for table in ['blobs', 'commits', 'tree_entries', 'branches', 'cross_references', 'tags', 'sessions']:
        pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = pg_cur.fetchone()[0]
        print(f"  {table}: {count}")

    # Cleanup
    sqlite_conn.close()
    pg_cur.close()
    pg_conn.close()
    print("\nConnections closed.")

if __name__ == '__main__':
    migrate()
