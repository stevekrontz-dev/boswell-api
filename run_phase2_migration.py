#!/usr/bin/env python3
"""
Phase 2 Migration: Encrypt all Boswell blobs with local AES-256-GCM master key.

Replaces GCP KMS approach. Reads BOSWELL_MASTER_KEY from environment.

Steps:
1. Schema migration (ensure encryption columns exist)
2. Generate new DEK with local master key
3. Retire old GCP-wrapped DEK (if any)
4. Encrypt all plaintext blobs (batch 100)
5. Re-encrypt 17 GCP-encrypted blobs from plaintext content column
6. Verify: no blobs with NULL content_encrypted
"""

import os
import sys
import psycopg2
import psycopg2.extras
import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encryption_service import EncryptionService, get_encryption_service

# Configuration
POSTGRES_URL = os.environ.get('DATABASE_URL')
if not POSTGRES_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    sys.exit(1)

DEFAULT_TENANT = '00000000-0000-0000-0000-000000000001'
BATCH_SIZE = 100


def run_schema_migration(conn):
    """Ensure Phase 2 schema exists (idempotent)."""
    print("\n[1/5] Verifying schema...")

    cur = conn.cursor()

    statements = [
        ("Create data_encryption_keys table",
         """CREATE TABLE IF NOT EXISTS data_encryption_keys (
                key_id VARCHAR(64) PRIMARY KEY,
                tenant_id UUID REFERENCES tenants(id) DEFAULT '00000000-0000-0000-0000-000000000001',
                wrapped_key BYTEA NOT NULL,
                kms_key_version VARCHAR(255),
                algorithm VARCHAR(50) DEFAULT 'AES-256-GCM',
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                rotated_at TIMESTAMPTZ
            )"""),
        ("Create DEK tenant index",
         "CREATE INDEX IF NOT EXISTS idx_dek_tenant ON data_encryption_keys(tenant_id)"),
        ("Create DEK status index",
         "CREATE INDEX IF NOT EXISTS idx_dek_status ON data_encryption_keys(status)"),
        ("Add content_encrypted to blobs",
         "ALTER TABLE blobs ADD COLUMN IF NOT EXISTS content_encrypted BYTEA"),
        ("Add nonce to blobs",
         "ALTER TABLE blobs ADD COLUMN IF NOT EXISTS nonce BYTEA"),
        ("Add encryption_key_id to blobs",
         "ALTER TABLE blobs ADD COLUMN IF NOT EXISTS encryption_key_id VARCHAR(64)"),
    ]

    for desc, sql in statements:
        print(f"  {desc}...", end=" ")
        try:
            cur.execute(sql)
            print("OK")
        except Exception as e:
            print(f"SKIP ({e})")

    conn.commit()
    cur.close()
    print("  Schema verified!")


def inspect_existing_encrypted_blobs(conn):
    """Check the 17 GCP-encrypted blobs before overwriting."""
    print("\n[2/5] Inspecting existing encrypted blobs...")

    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT blob_hash, created_at, updated_at, encryption_key_id,
               content IS NOT NULL as has_plaintext
        FROM blobs
        WHERE content_encrypted IS NOT NULL AND tenant_id = %s
        ORDER BY created_at
    """, (DEFAULT_TENANT,))

    rows = cur.fetchall()
    cur.close()

    if not rows:
        print("  No existing encrypted blobs found.")
        return 0

    print(f"  Found {len(rows)} existing encrypted blobs:")
    suspicious = 0
    for row in rows:
        updated = row['updated_at']
        created = row['created_at']
        marker = ""
        if updated and created and updated > created:
            marker = " *** UPDATED AFTER CREATION — inspect before overwriting"
            suspicious += 1
        print(f"    {row['blob_hash'][:12]}  created={created}  key={row['encryption_key_id']}  plaintext={row['has_plaintext']}{marker}")

    if suspicious > 0:
        print(f"\n  WARNING: {suspicious} blobs have updated_at > created_at.")
        response = input("  Continue anyway? (yes/no): ").strip().lower()
        if response != 'yes':
            print("  Aborting.")
            sys.exit(1)

    return len(rows)


def generate_new_dek(conn, encryption_service):
    """Generate a new DEK with local master key."""
    print("\n[3/5] Generating new DEK with local master key...")

    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Check for existing active DEK (from previous local-key migration)
    cur.execute("""
        SELECT key_id FROM data_encryption_keys
        WHERE tenant_id = %s AND status = 'active'
        AND kms_key_version = 'local-master-key'
    """, (DEFAULT_TENANT,))
    existing = cur.fetchone()
    if existing:
        print(f"  Active local DEK already exists: {existing['key_id']}")
        cur.close()
        return existing['key_id']

    # Retire any old GCP-wrapped DEKs
    cur.execute("""
        UPDATE data_encryption_keys
        SET status = 'retired', rotated_at = NOW()
        WHERE tenant_id = %s AND status = 'active'
    """, (DEFAULT_TENANT,))
    retired = cur.rowcount
    if retired:
        print(f"  Retired {retired} old GCP-wrapped DEK(s)")

    # Generate new DEK
    key_id, wrapped_dek, _ = encryption_service.generate_dek()

    # Store wrapped DEK
    cur.execute(
        """INSERT INTO data_encryption_keys (key_id, tenant_id, wrapped_key, kms_key_version, algorithm, status)
           VALUES (%s, %s, %s, 'local-master-key', 'AES-256-GCM', 'active')""",
        (key_id, DEFAULT_TENANT, psycopg2.Binary(wrapped_dek))
    )
    conn.commit()
    cur.close()

    print(f"  Generated DEK: {key_id}")
    return key_id


def migrate_blobs(conn, encryption_service, key_id):
    """Encrypt all blobs that don't have content_encrypted populated."""
    print("\n[4/5] Encrypting blobs...")

    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Get wrapped DEK
    cur.execute("SELECT wrapped_key FROM data_encryption_keys WHERE key_id = %s", (key_id,))
    wrapped_dek = bytes(cur.fetchone()['wrapped_key'])
    plaintext_dek = encryption_service.unwrap_dek(key_id, wrapped_dek)

    # Count totals
    cur.execute("SELECT COUNT(*) as total FROM blobs WHERE tenant_id = %s", (DEFAULT_TENANT,))
    total = cur.fetchone()['total']

    # Find all blobs needing encryption (includes both plaintext-only AND old GCP-encrypted that need re-encryption)
    # We re-encrypt everything from the plaintext content column using the new local DEK
    cur.execute("""
        SELECT blob_hash, content FROM blobs
        WHERE tenant_id = %s AND content IS NOT NULL
        AND (content_encrypted IS NULL OR encryption_key_id != %s)
        ORDER BY created_at
    """, (DEFAULT_TENANT, key_id))

    blobs = cur.fetchall()

    if not blobs:
        print(f"  All {total} blobs already encrypted with current DEK.")
        cur.close()
        return 0

    print(f"  {len(blobs)} blobs to encrypt (of {total} total)...")
    migrated = 0
    errors = 0
    start = time.time()

    for blob_hash, content in blobs:
        try:
            ciphertext, nonce = encryption_service.encrypt(content, plaintext_dek)

            cur.execute(
                """UPDATE blobs
                   SET content_encrypted = %s, nonce = %s, encryption_key_id = %s
                   WHERE blob_hash = %s AND tenant_id = %s""",
                (psycopg2.Binary(ciphertext), psycopg2.Binary(nonce), key_id,
                 blob_hash, DEFAULT_TENANT)
            )
            migrated += 1

            if migrated % BATCH_SIZE == 0:
                conn.commit()
                elapsed = time.time() - start
                rate = migrated / elapsed if elapsed > 0 else 0
                print(f"    {migrated}/{len(blobs)} ({rate:.0f} blobs/sec)...")

        except Exception as e:
            errors += 1
            print(f"  ERROR on {blob_hash[:12]}: {e}")
            if errors > 10:
                print("  Too many errors, aborting.")
                conn.rollback()
                sys.exit(1)

    conn.commit()
    cur.close()
    elapsed = time.time() - start
    print(f"  Encrypted {migrated} blobs in {elapsed:.1f}s ({errors} errors)")
    return migrated


def verify_migration(conn):
    """Verify all blobs are encrypted."""
    print("\n[5/5] Verification...")
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT COUNT(*) as count FROM blobs
        WHERE tenant_id = %s AND content_encrypted IS NULL
    """, (DEFAULT_TENANT,))
    unencrypted = cur.fetchone()['count']

    cur.execute("""
        SELECT COUNT(*) as count FROM blobs
        WHERE tenant_id = %s AND content_encrypted IS NOT NULL
    """, (DEFAULT_TENANT,))
    encrypted = cur.fetchone()['count']

    cur.execute("""
        SELECT COUNT(*) as count FROM data_encryption_keys
        WHERE tenant_id = %s AND status = 'active'
    """, (DEFAULT_TENANT,))
    active_keys = cur.fetchone()['count']

    cur.execute("""
        SELECT COUNT(*) as count FROM data_encryption_keys
        WHERE tenant_id = %s AND status = 'retired'
    """, (DEFAULT_TENANT,))
    retired_keys = cur.fetchone()['count']

    # Round-trip test: decrypt a random encrypted blob
    roundtrip_ok = False
    cur.execute("""
        SELECT blob_hash, content, content_encrypted, nonce, encryption_key_id
        FROM blobs
        WHERE tenant_id = %s AND content_encrypted IS NOT NULL AND content IS NOT NULL
        LIMIT 1
    """, (DEFAULT_TENANT,))
    test_blob = cur.fetchone()
    if test_blob:
        try:
            svc = get_encryption_service()
            dek_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            dek_cur.execute("SELECT wrapped_key FROM data_encryption_keys WHERE key_id = %s",
                            (test_blob['encryption_key_id'],))
            dek_row = dek_cur.fetchone()
            dek_cur.close()
            if dek_row:
                decrypted = svc.decrypt_with_wrapped_dek(
                    bytes(test_blob['content_encrypted']),
                    bytes(test_blob['nonce']),
                    test_blob['encryption_key_id'],
                    bytes(dek_row['wrapped_key'])
                )
                roundtrip_ok = (decrypted == test_blob['content'])
        except Exception as e:
            print(f"  Round-trip test error: {e}")

    cur.close()

    print(f"\n{'='*50}")
    print(f"  Unencrypted blobs: {unencrypted}")
    print(f"  Encrypted blobs:   {encrypted}")
    print(f"  Active DEKs:       {active_keys}")
    print(f"  Retired DEKs:      {retired_keys}")
    print(f"  Round-trip test:   {'PASS' if roundtrip_ok else 'FAIL'}")
    print(f"{'='*50}")

    if unencrypted == 0 and encrypted > 0 and roundtrip_ok:
        print("\n  *** MIGRATION SUCCESSFUL ***")
        print("  All blobs have content_encrypted populated.")
        print("  content column retained for tsvector trigger (Phase 2 will remove it).")
    else:
        print("\n  *** MIGRATION INCOMPLETE ***")
        if unencrypted > 0:
            print(f"  {unencrypted} blobs still need encryption.")
        if not roundtrip_ok:
            print("  Round-trip decryption test failed!")


def main():
    print("=" * 60)
    print("BOSWELL ENCRYPTION MIGRATION")
    print("Local AES-256-GCM Master Key")
    print("=" * 60)

    # Verify master key is set
    master_key = os.environ.get('BOSWELL_MASTER_KEY')
    if not master_key:
        print("\nERROR: BOSWELL_MASTER_KEY environment variable not set!")
        print("Generate with:")
        print('  python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"')
        sys.exit(1)

    print(f"\nMaster key: {master_key[:8]}...{master_key[-4:]} ({len(master_key)} chars)")

    # Initialize encryption service
    print("Initializing encryption service...")
    encryption_service = get_encryption_service()
    if not encryption_service:
        print("ERROR: Failed to initialize encryption service")
        sys.exit(1)

    # Canary test
    if not encryption_service.canary_test():
        print("ERROR: Encryption canary test failed!")
        sys.exit(1)
    print("  Canary test passed!")

    # Connect to Postgres
    print("\nConnecting to Postgres...")
    conn = psycopg2.connect(POSTGRES_URL)
    conn.autocommit = False
    print("  Connected!")

    # Set tenant context
    cur = conn.cursor()
    cur.execute(f"SET app.current_tenant = '{DEFAULT_TENANT}'")
    cur.close()

    try:
        run_schema_migration(conn)
        inspect_existing_encrypted_blobs(conn)
        key_id = generate_new_dek(conn, encryption_service)
        migrate_blobs(conn, encryption_service, key_id)
        verify_migration(conn)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        raise
    finally:
        conn.close()
        print("\nConnection closed.")

    print("\nNEXT STEPS:")
    print("  1. Back up BOSWELL_MASTER_KEY to password manager")
    print("  2. Verify health endpoint: curl <url>/v2/health | jq .encryption")
    print("  3. Test boswell_commit + verify content_encrypted populated")
    print("  4. Phase 2 (future): remove plaintext from content column")


if __name__ == '__main__':
    main()
