#!/usr/bin/env python3
"""Run branch fingerprints migration."""
import os
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("DATABASE_URL not set")
    exit(1)

print("Connecting to Railway Postgres...")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("Running branch fingerprints migration...")

migration_sql = open('db/migrations/012_branch_fingerprints.sql').read()
cur.execute(migration_sql)
conn.commit()

print("Migration complete!")

# Verify
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'branch_fingerprints'")
cols = [r[0] for r in cur.fetchall()]
print(f"branch_fingerprints columns: {cols}")

cur.close()
conn.close()
