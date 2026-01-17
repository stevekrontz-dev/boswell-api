import psycopg2

# The FIRST database I migrated (gondola) - what is this?
conn = psycopg2.connect('postgresql://postgres:upJwGUEdZPdIWBkMZApoUKwpdcnxzQcY@gondola.proxy.rlwy.net:13404/railway')
cur = conn.cursor()

print("=== GONDOLA DATABASE (first one I migrated) ===")
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}")

if 'users' in tables:
    cur.execute("SELECT COUNT(*) FROM users")
    print(f"Users count: {cur.fetchone()[0]}")

if 'tenants' in tables:
    cur.execute("SELECT COUNT(*) FROM tenants")
    print(f"Tenants count: {cur.fetchone()[0]}")

if 'commits' in tables:
    cur.execute("SELECT COUNT(*) FROM commits")
    print(f"Commits count: {cur.fetchone()[0]}")

cur.close()
conn.close()
