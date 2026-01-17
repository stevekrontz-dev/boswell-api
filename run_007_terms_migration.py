#!/usr/bin/env python3
"""
Run migration 007 additions: terms_accepted_at column
"""
import os
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    exit(1)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

try:
    # Add terms_accepted_at column
    cur.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMP;
    """)
    
    # Add comment
    cur.execute("""
        COMMENT ON COLUMN users.terms_accepted_at 
        IS 'Timestamp when user accepted Terms of Service and Privacy Policy';
    """)
    
    conn.commit()
    print("✅ Migration complete: terms_accepted_at column added")
    
except Exception as e:
    conn.rollback()
    print(f"❌ Migration failed: {e}")
    
finally:
    cur.close()
    conn.close()
