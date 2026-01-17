import psycopg2

# The SECOND database I migrated (shuttle/pgvector) - what is this?
conn = psycopg2.connect('postgres://postgres:NSDvmh55Uo4jCTv2h3w.d2L6APrvme53@shuttle.proxy.rlwy.net:40665/railway')
cur = conn.cursor()

print("=== SHUTTLE DATABASE (second one - pgvector) ===")
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

if 'blobs' in tables:
    cur.execute("SELECT COUNT(*) FROM blobs")
    print(f"Blobs count: {cur.fetchone()[0]}")

cur.close()
conn.close()
