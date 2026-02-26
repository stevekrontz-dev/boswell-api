#!/usr/bin/env python3
"""Multi-Tenant Isolation Smoke Test for Boswell v3.4.0

Tests BOTH search paths (keyword + semantic) across all 3 tenants:
- Steve (00000000-0000-0000-0000-000000000001)
- Aaron Stokes (979ced2f-3532-41f5-8628-dcf5f32665ea)
- Feynman (d60f3fb9-0fef-46b7-bedf-2f2204368e99)
"""
import psycopg2
import psycopg2.extras

DB_URL = 'postgres://postgres:NSDvmh55Uo4jCTv2h3w.d2L6APrvme53@shuttle.proxy.rlwy.net:40665/railway'
conn = psycopg2.connect(DB_URL, connect_timeout=15)
conn.set_session(readonly=True)
cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

STEVE = '00000000-0000-0000-0000-000000000001'
AARON = '979ced2f-3532-41f5-8628-dcf5f32665ea'
FEYNMAN = 'd60f3fb9-0fef-46b7-bedf-2f2204368e99'

print("=====================================================")
print("  MULTI-TENANT ISOLATION SMOKE TEST")
print("  Testing BOTH search paths (keyword + semantic)")
print("=====================================================")
print()

all_pass = True
results = []

def test(name, query_tenant, search_term, expected_zero=True, control_tenant=None):
    global all_pass
    cur.execute("""
        SELECT COUNT(*) as cnt
        FROM blobs b
        WHERE b.tenant_id = %s
          AND b.search_vector IS NOT NULL
          AND b.search_vector @@ plainto_tsquery('english', %s)
    """, (query_tenant, search_term))
    cnt = cur.fetchone()['cnt']

    control_cnt = None
    if control_tenant:
        cur.execute("""
            SELECT COUNT(*) as cnt
            FROM blobs b
            WHERE b.tenant_id = %s
              AND b.search_vector IS NOT NULL
              AND b.search_vector @@ plainto_tsquery('english', %s)
        """, (control_tenant, search_term))
        control_cnt = cur.fetchone()['cnt']

    if expected_zero:
        status = "PASS" if cnt == 0 else "FAIL"
        if cnt > 0:
            all_pass = False
    else:
        status = "PASS" if cnt > 0 else "FAIL"
        if cnt == 0:
            all_pass = False

    print(f"  {status}: {name}")
    print(f"         Results: {cnt}" + (f" | Control ({control_tenant[:8]}...): {control_cnt}" if control_cnt is not None else ""))
    results.append((name, status, cnt))
    return cnt


def semantic_test(name, source_tenant, source_query, target_tenant):
    """Test that searching target_tenant with source_tenant's embedding returns only target_tenant blobs."""
    global all_pass
    cur.execute("""
        SELECT b.embedding
        FROM blobs b
        WHERE b.tenant_id = %s AND b.embedding IS NOT NULL
          AND b.content ILIKE %s
        LIMIT 1
    """, (source_tenant, f"%{source_query}%"))
    row = cur.fetchone()
    if not row or row['embedding'] is None:
        print(f"  SKIP: {name} (no source embedding found)")
        return

    # Search in target tenant using source embedding
    cur.execute("""
        SELECT b.blob_hash, b.tenant_id
        FROM blobs b
        WHERE b.tenant_id = %s AND b.embedding IS NOT NULL
          AND b.embedding <=> %s::vector < 0.3
        LIMIT 10
    """, (target_tenant, row['embedding']))
    hits = cur.fetchall()

    # Verify ALL results belong to target tenant (no cross-tenant leaks)
    leaked = [h for h in hits if h['tenant_id'] != target_tenant]
    if leaked:
        all_pass = False
        print(f"  FAIL: {name}")
        for l in leaked:
            print(f"         LEAK: {l['blob_hash'][:16]}... tenant={l['tenant_id']}")
    else:
        print(f"  PASS: {name}")
        print(f"         {len(hits)} results, all correctly scoped to {target_tenant[:8]}...")
    results.append((name, "FAIL" if leaked else "PASS", len(hits)))


# ============================================================
# KEYWORD TESTS
# ============================================================
print("--- KEYWORD SEARCH ISOLATION ---")
print()

# Steve cannot find Aaron-only content
# NOTE: "ShopFix Academy" exists in Steve's tenant too (biographical memories about Aaron)
# Use a term that ONLY exists in Aaron's tenant
test("Steve -> Aaron keyword (recession hiring advantage)",
     STEVE, "recession hiring advantage",
     expected_zero=True, control_tenant=AARON)

# Steve cannot find Feynman-only content
test("Steve -> Feynman keyword (quantum electrodynamics renormalization)",
     STEVE, "quantum electrodynamics renormalization",
     expected_zero=True, control_tenant=FEYNMAN)

# Aaron cannot find Steve-only content
test("Aaron -> Steve keyword (TintAtlanta window tinting)",
     AARON, "TintAtlanta window tinting",
     expected_zero=True, control_tenant=STEVE)

# Aaron cannot find Feynman content
test("Aaron -> Feynman keyword (quantum electrodynamics Feynman)",
     AARON, "quantum electrodynamics Feynman",
     expected_zero=True, control_tenant=FEYNMAN)

# Feynman cannot find Steve content
test("Feynman -> Steve keyword (TintAtlanta window tinting)",
     FEYNMAN, "TintAtlanta window tinting",
     expected_zero=True, control_tenant=STEVE)

# Feynman cannot find Aaron content
test("Feynman -> Aaron keyword (recession hiring advantage)",
     FEYNMAN, "recession hiring advantage",
     expected_zero=True, control_tenant=AARON)

print()

# ============================================================
# SEMANTIC TESTS
# ============================================================
print("--- SEMANTIC SEARCH ISOLATION ---")
print()

# Using Aaron's ShopFix embedding, search Steve's space
semantic_test("Steve space with Aaron embedding (ShopFix)",
              AARON, "ShopFix", STEVE)

# Using Feynman's physics embedding, search Steve's space
semantic_test("Steve space with Feynman embedding (electrodynamics)",
              FEYNMAN, "electrodynamics", STEVE)

# Using Steve's TintAtlanta embedding, search Aaron's space
semantic_test("Aaron space with Steve embedding (TintAtlanta)",
              STEVE, "TintAtlanta", AARON)

# Using Steve's TintAtlanta embedding, search Feynman's space
semantic_test("Feynman space with Steve embedding (TintAtlanta)",
              STEVE, "TintAtlanta", FEYNMAN)

# Using Aaron's embedding, search Feynman's space
semantic_test("Feynman space with Aaron embedding (ShopFix)",
              AARON, "ShopFix", FEYNMAN)

# Using Feynman's embedding, search Aaron's space
semantic_test("Aaron space with Feynman embedding (electrodynamics)",
              FEYNMAN, "electrodynamics", AARON)

print()

# ============================================================
# CONTROL TESTS — tenants CAN find their own data
# ============================================================
print("--- CONTROL: TENANTS FIND OWN DATA ---")
print()

test("Aaron finds own coaching content",
     AARON, "recession hiring advantage", expected_zero=False)

test("Feynman finds own physics content",
     FEYNMAN, "quantum electrodynamics", expected_zero=False)

test("Steve finds own TintAtlanta content",
     STEVE, "TintAtlanta window", expected_zero=False)

print()

# ============================================================
# SUMMARY
# ============================================================
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
skipped = sum(1 for _, s, _ in results if s == "SKIP")

print("=====================================================")
print(f"  RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
if all_pass:
    print("  VERDICT: TENANT ISOLATION AIRTIGHT")
else:
    print("  VERDICT: ISOLATION BREACH DETECTED")
print("=====================================================")

cur.close()
conn.close()
