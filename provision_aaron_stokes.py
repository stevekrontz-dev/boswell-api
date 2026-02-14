#!/usr/bin/env python3
"""
Provision Aaron Stokes Preservation Agent tenant in Boswell.

Creates:
  - New tenant: aaron-stokes
  - 6 branches: shop-operations, people-leadership, financial-mastery,
                 sales-process, tech-development, mindset
  - API key (bos_ prefix)
  - Sacred manifest committed to mindset branch

Usage:
    python provision_aaron_stokes.py
"""

import uuid
import json
import hashlib
import secrets
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

# Railway Postgres (same connection as run_schema.py)
DATABASE_URL = "postgresql://postgres:ItAxQqfRlFJlScRpgzPGswYNKMvzCuTg@gondola.proxy.rlwy.net:13404/railway?sslmode=require"


def compute_hash(content: str) -> str:
    """SHA-256 hash matching app.py compute_hash()."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def generate_api_key() -> str:
    """Generate bos_ prefixed API key matching auth/api_keys.py."""
    return f"bos_{secrets.token_urlsafe(32)}"


def hash_key(key: str) -> str:
    """SHA-256 hash of API key matching auth/api_keys.py."""
    return hashlib.sha256(key.encode()).hexdigest()


SACRED_MANIFEST = {
    "type": "sacred_manifest",
    "version": "1.0",
    "identity": "Aaron Stokes (1978-2026), Founder of Shop Fix Academy, Franklin TN",
    "mission": "Our mission is to stop the average small business from destroying the average small family in America. We are owners helping owners.",
    "voice": {
        "style": "Direct, pastoral, occasionally profane. Youth pastor meets 8th-grade dropout who crawled out of $5.5M debt. Not neutral — pushes back hard. Sees solutions fast. Coaches from his smartphone.",
        "key_trait": "Everything taught was tested in his own 11-shop operation first. Practitioner, not consultant.",
        "faith": "Christian faith openly integrated into leadership philosophy. Not performative — foundational."
    },
    "core_frameworks": [
        "Three Capitals: Cash, Systems, People",
        "Ceiling of Complexity (Popcorn Bucket)",
        "Peers, Heroes, and Mentors",
        "Teetering Tower / Build for Busy Days",
        "Opportunity Drive vs Opportunity Court"
    ],
    "sacred_quotes": [
        "Your shop is a mirror of you. If you want to fix your shop, you have to start with yourself.",
        "The only thing that matters is net worth.",
        "Money loves speed.",
        "There are no spare customers.",
        "Never stop recruiting because you're going to make mistakes.",
        "I don't teach anything that I haven't used inside my own shops."
    ],
    "active_commitments": [
        {
            "id": "preservation-integrity",
            "commitment": "Every commit must preserve WHY Aaron taught what he taught, not just WHAT he taught",
            "rationale": "Future queries need his reasoning and voice, not just his frameworks as bullet points",
            "status": "permanent"
        },
        {
            "id": "practitioner-first",
            "commitment": "When answering queries, always ground advice in Aaron's real operational experience — 11 shops, $65M enterprise, $5.5M debt recovery",
            "rationale": "His credibility came from doing, not theorizing. The agent must reflect that.",
            "status": "permanent"
        }
    ]
}

BRANCHES = [
    'shop-operations',
    'people-leadership',
    'financial-mastery',
    'sales-process',
    'tech-development',
    'mindset',
]


def main():
    print("=" * 60)
    print("BOSWELL TENANT PROVISIONING")
    print("Tenant: Aaron Stokes - Shop Fix Academy")
    print("=" * 60)

    # Connect
    print("\nConnecting to Railway Postgres...")
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Bypass RLS (postgres superuser bypasses anyway, but set context for safety)
    cur.execute("SET app.current_tenant = '00000000-0000-0000-0000-000000000001'")

    try:
        # 1. Generate credentials
        tenant_id = str(uuid.uuid4())
        api_key = generate_api_key()
        api_key_hash = hash_key(api_key)
        tenant_name = "Aaron Stokes - Shop Fix Academy"

        print(f"\n  Tenant ID:  {tenant_id}")
        print(f"  API Key:    {api_key}")
        print(f"  Key Hash:   {api_key_hash[:16]}...")

        # 2. Insert tenant
        print("\n  Creating tenant...", end=" ")
        cur.execute(
            '''INSERT INTO tenants (id, name, created_at)
               VALUES (%s, %s, NOW())
               RETURNING id, name, created_at''',
            (tenant_id, tenant_name)
        )
        tenant_row = cur.fetchone()
        print(f"OK — {tenant_row['name']}")

        # 3. Store API key hash
        print("  Storing API key...", end=" ")
        key_id = str(uuid.uuid4())
        cur.execute(
            '''INSERT INTO api_keys (id, tenant_id, user_id, key_hash, name, created_at)
               VALUES (%s, %s, NULL, %s, %s, NOW())''',
            (key_id, tenant_id, api_key_hash, f"Default key for {tenant_name}")
        )
        print("OK")

        # 4. Create 6 branches
        print("  Creating branches...")
        for branch_name in BRANCHES:
            cur.execute(
                '''INSERT INTO branches (tenant_id, name, head_commit)
                   VALUES (%s, %s, NULL)
                   ON CONFLICT DO NOTHING''',
                (tenant_id, branch_name)
            )
            print(f"    [OK] {branch_name}")

        # 5. Commit sacred manifest to mindset branch
        print("\n  Committing sacred manifest to mindset branch...", end=" ")

        now = datetime.now(timezone.utc).isoformat()
        content_str = json.dumps(SACRED_MANIFEST, indent=2)
        blob_hash = compute_hash(content_str)
        message = "SACRED: Aaron Stokes preservation agent manifest - voice, frameworks, commitments"
        author = "claude-code"

        # Set tenant context for this insert
        cur.execute(f"SET app.current_tenant = '{tenant_id}'")

        # Insert blob
        cur.execute(
            '''INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (blob_hash) DO NOTHING''',
            (blob_hash, tenant_id, content_str, 'memory', now, len(content_str))
        )

        # Insert tree entry
        tree_hash = compute_hash(f"mindset:{blob_hash}:{now}")
        cur.execute(
            '''INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
               VALUES (%s, %s, %s, %s, %s)''',
            (tenant_id, tree_hash, message[:100], blob_hash, 'memory')
        )

        # Get parent (should be None for first commit)
        cur.execute(
            'SELECT head_commit FROM branches WHERE name = %s AND tenant_id = %s',
            ('mindset', tenant_id)
        )
        branch_row = cur.fetchone()
        parent_hash = branch_row['head_commit'] if branch_row else None

        # Create commit
        commit_data = f"{tree_hash}:{parent_hash}:{message}:{now}"
        commit_hash = compute_hash(commit_data)

        cur.execute(
            '''INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (commit_hash, tenant_id, tree_hash, parent_hash, author, message, now)
        )

        # Update branch head
        cur.execute(
            'UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s',
            (commit_hash, 'mindset', tenant_id)
        )

        # Add tags
        for tag in ['sacred_manifest', 'aaron-stokes', 'preservation-agent']:
            cur.execute(
                '''INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
                   VALUES (%s, %s, %s, %s)''',
                (tenant_id, blob_hash, tag, now)
            )

        print("OK")

        # COMMIT TRANSACTION
        conn.commit()

        # 6. Verify
        print("\n" + "=" * 60)
        print("PROVISIONING COMPLETE")
        print("=" * 60)
        print(f"\n  Tenant ID:    {tenant_id}")
        print(f"  Tenant Name:  {tenant_name}")
        print(f"  API Key:      {api_key}")
        print(f"  Branches:     {', '.join(BRANCHES)}")
        print(f"\n  Sacred Manifest:")
        print(f"    Commit:     {commit_hash}")
        print(f"    Blob:       {blob_hash}")
        print(f"    Branch:     mindset")
        print(f"\n  WARNING: SAVE THE API KEY NOW -- it cannot be retrieved again!")
        print("=" * 60)

        # Return values for programmatic use
        return {
            'tenant_id': tenant_id,
            'api_key': api_key,
            'branches': BRANCHES,
            'sacred_manifest_commit': commit_hash,
            'sacred_manifest_blob': blob_hash,
        }

    except Exception as e:
        conn.rollback()
        print(f"\n  ERROR: {e}")
        raise
    finally:
        cur.close()
        conn.close()
        print("\nConnection closed.")


if __name__ == '__main__':
    main()
