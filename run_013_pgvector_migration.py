#!/usr/bin/env python3
"""
Run migration to add 'deleted' status to task_status enum on pgvector database.
This is the CORRECT database that the Boswell API uses.
"""

import psycopg2

# pgvector PUBLIC connection (not Postgres)
DATABASE_URL = "postgresql://postgres:NSDvmh55Uo4jCTv2h3w.d2L6APrvme53@shuttle.proxy.rlwy.net:40665/railway"

print("Connecting to Railway pgvector database...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("Adding 'deleted' value to task_status enum...")
try:
    cur.execute("ALTER TYPE task_status ADD VALUE 'deleted'")
    print("SUCCESS: Added 'deleted' to task_status enum")
except psycopg2.errors.DuplicateObject:
    print("SKIPPED: 'deleted' already exists in task_status enum")
except Exception as e:
    print(f"ERROR: {e}")

# Verify the enum values
cur.execute("""
    SELECT unnest(enum_range(NULL::task_status))::text as status
    ORDER BY status
""")
statuses = [row[0] for row in cur.fetchall()]
print(f"Current task_status values: {statuses}")

cur.close()
conn.close()
print("Connection closed.")
