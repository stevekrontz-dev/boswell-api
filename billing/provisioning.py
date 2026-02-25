"""
Shared Tenant Provisioning Logic
Owner: CC1
Domain: Onboarding

Extracted from stripe_handler.py handle_checkout_completed().
Both the Stripe webhook and POST /v2/onboard/provision call this.
"""

import uuid
import secrets
import hashlib
from datetime import datetime
from auth import encrypt_api_key


DEFAULT_BRANCHES = ['command-center', 'work', 'personal', 'research']


def provision_tenant(cursor, email: str, user_id: str = None) -> dict:
    """Create tenant, default branches, and API key for a new user.

    This is the single source of truth for provisioning. Called by:
    - POST /v2/onboard/provision (CLI signup, no Stripe)
    - handle_checkout_completed() in stripe_handler.py (Stripe checkout)

    Args:
        cursor: Active database cursor (caller owns the transaction).
        email: User email, used as tenant name.
        user_id: Existing user ID. If None, a new UUID is generated.

    Returns:
        dict with keys: tenant_id, user_id, api_key (raw), api_key_encrypted,
                        key_hash, key_id, branches
    """
    now = datetime.utcnow().isoformat() + 'Z'

    if not user_id:
        user_id = str(uuid.uuid4())

    # --- Tenant ---
    tenant_id = str(uuid.uuid4())
    cursor.execute(
        '''INSERT INTO tenants (id, name, created_at)
           VALUES (%s, %s, %s)''',
        (tenant_id, email, now)
    )
    print(f"[PROVISION] Created tenant {tenant_id} for {email}", flush=True)

    # --- Default Branches ---
    for branch_name in DEFAULT_BRANCHES:
        cursor.execute(
            '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
               VALUES (%s, %s, 'GENESIS', %s)''',
            (tenant_id, branch_name, now)
        )
    print(f"[PROVISION] Created {len(DEFAULT_BRANCHES)} default branches", flush=True)

    # --- API Key ---
    api_key = 'bos_' + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_id = str(uuid.uuid4())

    cursor.execute(
        '''INSERT INTO api_keys (id, tenant_id, user_id, key_hash, name, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)''',
        (key_id, tenant_id, user_id, key_hash, 'Auto-generated', now)
    )
    print(f"[PROVISION] Created API key for user {user_id}", flush=True)

    api_key_encrypted = encrypt_api_key(api_key)

    return {
        'tenant_id': tenant_id,
        'user_id': user_id,
        'api_key': api_key,
        'api_key_encrypted': api_key_encrypted,
        'key_hash': key_hash,
        'key_id': key_id,
        'branches': list(DEFAULT_BRANCHES),
    }
