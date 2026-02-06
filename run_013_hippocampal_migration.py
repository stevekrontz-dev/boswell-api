#!/usr/bin/env python3
"""Run hippocampal memory staging migration (Boswell v4.0)."""
import os
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("DATABASE_URL not set")
    exit(1)

print("Connecting to Railway Postgres...")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("Running hippocampal staging migration (013)...")

migration_sql = open('db/migrations/013_hippocampal_staging.sql').read()
cur.execute(migration_sql)
conn.commit()

print("Migration complete!")

# Verify tables exist
for table in ['candidate_memories', 'replay_events', 'consolidation_log']:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position", (table,))
    cols = [r[0] for r in cur.fetchall()]
    print(f"{table} columns: {cols}")

cur.close()
conn.close()
