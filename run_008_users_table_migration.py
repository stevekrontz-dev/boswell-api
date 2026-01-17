#!/usr/bin/env python3
"""
Migration: Create users table for self-service registration
Run this in Railway console or with DATABASE_URL env var set
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
    # Create users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(255),
            status VARCHAR(50) DEFAULT 'pending_payment',
            terms_accepted_at TIMESTAMPTZ,
            stripe_customer_id VARCHAR(255),
            tenant_id UUID REFERENCES tenants(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    
    # Add indexes
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_stripe ON users(stripe_customer_id);
    """)
    
    conn.commit()
    print("✅ Migration complete: users table created with indexes")
    
    # Verify
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
    columns = [row[0] for row in cur.fetchall()]
    print(f"✅ Users table columns: {columns}")
    
except Exception as e:
    conn.rollback()
    print(f"❌ Migration failed: {e}")
    
finally:
    cur.close()
    conn.close()
