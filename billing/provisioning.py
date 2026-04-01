"""
Shared Tenant Provisioning Logic
Owner: CC1
Domain: Onboarding

Extracted from stripe_handler.py handle_checkout_completed().
Both the Stripe webhook and POST /v2/onboard/provision call this.
"""

import uuid
import json
import secrets
import hashlib
from datetime import datetime
from auth import encrypt_api_key


DEFAULT_BRANCHES = ['command-center', 'work', 'personal', 'research']


def provision_tenant(cursor, email: str, user_id: str = None, branches: list = None) -> dict:
    """Create tenant, default branches, API key, sacred manifest, and behavioral skill.

    This is the single source of truth for provisioning. Called by:
    - POST /v2/onboard/provision (CLI signup, no Stripe)
    - handle_checkout_completed() in stripe_handler.py (Stripe checkout)
    - POST /v2/admin/create-tenant (admin provisioning)

    Args:
        cursor: Active database cursor (caller owns the transaction).
        email: User email, used as tenant name.
        user_id: Existing user ID. If None, a new UUID is generated.
        branches: Custom branch list. If None, uses DEFAULT_BRANCHES.
                  command-center is always included (required for sacred manifest).

    Returns:
        dict with keys: tenant_id, user_id, api_key (raw), api_key_encrypted,
                        key_hash, key_id, branches
    """
    now = datetime.utcnow().isoformat() + 'Z'

    if not user_id:
        user_id = str(uuid.uuid4())

    # Resolve branch list
    branch_list = list(branches) if branches else list(DEFAULT_BRANCHES)
    if 'command-center' not in branch_list:
        branch_list.insert(0, 'command-center')

    # --- Tenant ---
    tenant_id = str(uuid.uuid4())
    cursor.execute(
        '''INSERT INTO tenants (id, name, created_at)
           VALUES (%s, %s, %s)''',
        (tenant_id, email, now)
    )
    print(f"[PROVISION] Created tenant {tenant_id} for {email}", flush=True)

    # --- Branches ---
    for branch_name in branch_list:
        cursor.execute(
            '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
               VALUES (%s, %s, 'GENESIS', %s)''',
            (tenant_id, branch_name, now)
        )
    print(f"[PROVISION] Created {len(branch_list)} branches: {branch_list}", flush=True)

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

    # --- Sacred Manifest + Behavioral Skill ---
    _seed_sacred_manifest(cursor, tenant_id, branch_list)
    _seed_behavioral_skill(cursor, tenant_id)
    print(f"[PROVISION] Seeded sacred manifest + behavioral skill", flush=True)

    return {
        'tenant_id': tenant_id,
        'user_id': user_id,
        'api_key': api_key,
        'api_key_encrypted': api_key_encrypted,
        'key_hash': key_hash,
        'key_id': key_id,
        'branches': branch_list,
    }


def _make_commit(cursor, tenant_id, content_dict, message, content_type='memory', parent_commit='GENESIS'):
    """Create a blob + commit on command-center for a tenant. Returns commit_hash."""
    now = datetime.utcnow().isoformat() + 'Z'
    content_str = json.dumps(content_dict, sort_keys=True)
    blob_hash = hashlib.sha256(content_str.encode()).hexdigest()
    commit_hash = hashlib.sha256(f"{blob_hash}:{parent_commit}:{now}".encode()).hexdigest()

    # Insert blob
    cursor.execute(
        '''INSERT INTO blobs (blob_hash, content, content_type, tenant_id, created_at)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT DO NOTHING''',
        (blob_hash, content_str, content_type, tenant_id, now)
    )

    # Insert commit
    cursor.execute(
        '''INSERT INTO commits (commit_hash, tenant_id, parent_hash, message, author, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT DO NOTHING''',
        (commit_hash, tenant_id, parent_commit if parent_commit != 'GENESIS' else None,
         message, 'system', now)
    )

    # Update branch head
    cursor.execute(
        '''UPDATE branches SET head_commit = %s, updated_at = %s
           WHERE tenant_id = %s AND name = 'command-center' ''',
        (commit_hash, now, tenant_id)
    )

    return commit_hash


def _seed_sacred_manifest(cursor, tenant_id, branches):
    """Create sacred manifest commit on command-center."""
    sacred_manifest = {
        'type': 'sacred_manifest',
        'version': '1.0',
        'active_commitments': [
            {
                'id': 'boswell-startup-first',
                'commitment': 'Call boswell_startup at conversation start before responding',
                'rationale': 'Ensures context continuity across all Claude instances',
                'status': 'permanent'
            },
            {
                'id': 'why-not-what',
                'commitment': 'Boswell commits must capture WHY, not just WHAT',
                'rationale': 'Future instances need reasoning, not just facts',
                'status': 'permanent'
            }
        ],
        'branches': branches,
        'updated_at': datetime.utcnow().isoformat() + 'Z'
    }

    return _make_commit(
        cursor, tenant_id, sacred_manifest,
        'Seed sacred manifest for new account',
        content_type='memory'
    )


def _seed_behavioral_skill(cursor, tenant_id):
    """Create Boswell Priority Framework skill commit on command-center."""
    # Get current head so we chain after the sacred manifest
    cursor.execute(
        "SELECT head_commit FROM branches WHERE tenant_id = %s AND name = 'command-center'",
        (tenant_id,)
    )
    row = cursor.fetchone()
    parent = row['head_commit'] if row and row['head_commit'] != 'GENESIS' else 'GENESIS'

    skill = {
        'name': 'Boswell Priority Framework',
        'version': '1.0',
        'type': 'behavioral_skill',
        'rules': [
            {
                'id': 'search-priority',
                'rule': 'Search priority: Boswell tools > tool definitions > web search > built-in tools > ask user',
                'why': 'Boswell is the primary memory system. Built-in conversation_search/recent_chats are session-scoped and lose context across conversations.'
            },
            {
                'id': 'startup-first',
                'rule': 'Call boswell_startup FIRST every conversation, before responding to anything.',
                'why': 'Loads active commitments and relevant context for continuity.'
            },
            {
                'id': 'verify-before-asserting',
                'rule': 'Before asserting facts about the user\'s systems, verify against Boswell tools and tool definitions. Never state a gap from assumption.',
                'why': 'Mental models decay between sessions. Search before stating.'
            },
            {
                'id': 'why-not-what',
                'rule': 'Commits must capture WHY, not just WHAT. Future instances need reasoning, not just facts.',
                'why': 'Context loss is the primary failure mode of AI memory.'
            }
        ]
    }

    return _make_commit(
        cursor, tenant_id, skill,
        'Seed Boswell Priority Framework behavioral skill',
        content_type='skill',
        parent_commit=parent
    )
