import psycopg2

conn = psycopg2.connect('postgresql://postgres:upJwGUEdZPdIWBkMZApoUKwpdcnxzQcY@gondola.proxy.rlwy.net:13404/railway')
cur = conn.cursor()

# Check existing columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
cols = [r[0] for r in cur.fetchall()]
print(f"Existing columns: {cols}")

# Add missing columns
missing = []

if 'status' not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN status VARCHAR(50) DEFAULT 'pending_payment'")
    missing.append('status')

if 'terms_accepted_at' not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN terms_accepted_at TIMESTAMPTZ")
    missing.append('terms_accepted_at')

if 'stripe_customer_id' not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255)")
    missing.append('stripe_customer_id')

if 'tenant_id' not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN tenant_id UUID REFERENCES tenants(id)")
    missing.append('tenant_id')

if 'name' not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN name VARCHAR(255)")
    missing.append('name')

conn.commit()

if missing:
    print(f"Added columns: {missing}")
else:
    print("All columns already exist")

# Verify
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
cols = [r[0] for r in cur.fetchall()]
print(f"Final columns: {cols}")

cur.close()
conn.close()
