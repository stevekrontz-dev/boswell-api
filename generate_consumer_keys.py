#!/usr/bin/env python3
"""
Generate API keys for Boswell consumers.

Inserts 5 bos_ keys into the api_keys table for each autonomous consumer.
Prints raw keys ONCE to stdout — save them immediately.

Usage:
    DATABASE_URL=postgres://... python generate_consumer_keys.py
"""

import os
import sys
import uuid
import psycopg2
import psycopg2.extras

# Reuse existing key generation from auth module
sys.path.insert(0, os.path.dirname(__file__))
from auth.api_keys import generate_api_key, hash_key

DATABASE_URL = os.environ.get('DATABASE_URL')
DEFAULT_TENANT = '00000000-0000-0000-0000-000000000001'

CONSUMERS = [
    'sentinel-farm',
    'viscera-defcon',
    'overwatch',
    'ios-shortcuts',
    'cw-mcp',
]


def main():
    if not DATABASE_URL:
        print("ERROR: Set DATABASE_URL environment variable", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # RLS requires tenant context
    cur.execute(f"SET app.current_tenant = '{DEFAULT_TENANT}'")

    print("=" * 60)
    print("BOSWELL CONSUMER API KEYS")
    print("Save these keys now. They will NOT be shown again.")
    print("=" * 60)

    for consumer in CONSUMERS:
        raw_key = generate_api_key()
        key_hash_val = hash_key(raw_key)
        key_id = str(uuid.uuid4())

        cur.execute(
            '''INSERT INTO api_keys (id, tenant_id, user_id, key_hash, name, created_at)
               VALUES (%s, %s, NULL, %s, %s, NOW())''',
            (key_id, DEFAULT_TENANT, key_hash_val, consumer)
        )

        print(f"\n  {consumer}:")
        print(f"    Key: {raw_key}")
        print(f"    ID:  {key_id}")

    conn.commit()
    cur.close()
    conn.close()

    print("\n" + "=" * 60)
    print(f"{len(CONSUMERS)} keys created successfully.")
    print("Set BOSWELL_API_KEY env var on each consumer.")
    print("=" * 60)


if __name__ == '__main__':
    main()
