"""
Onboarding Routes
Owner: CC1

POST /v2/onboard/provision   - Create account (public, rate-limited)
POST /v2/onboard/seed-manifest - Seed starter sacred manifest (API key auth)
"""

import re
import uuid
import json
import hashlib
import time
from collections import defaultdict
from datetime import datetime
from flask import Blueprint, request, jsonify, g

from auth import hash_password, hash_password_v2, generate_jwt
from billing.provisioning import provision_tenant

onboarding_bp = Blueprint('onboarding', __name__, url_prefix='/v2/onboard')


# ============================================================================
# Simple in-memory rate limiter for the provision endpoint
# ============================================================================

_provision_rate = defaultdict(list)   # ip -> [timestamp, ...]
PROVISION_RATE_LIMIT = 5             # max requests
PROVISION_RATE_WINDOW = 3600         # per 1 hour (seconds)


def _is_rate_limited(ip: str) -> bool:
    """Check and enforce rate limit for provision endpoint."""
    now = time.time()
    window_start = now - PROVISION_RATE_WINDOW
    # Purge old entries
    _provision_rate[ip] = [t for t in _provision_rate[ip] if t > window_start]
    if len(_provision_rate[ip]) >= PROVISION_RATE_LIMIT:
        return True
    _provision_rate[ip].append(now)
    return False


def _validate_email(email: str) -> bool:
    """Basic email format validation."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def init_onboarding(get_db, get_cursor):
    """Initialize onboarding blueprint with database access functions."""

    # ------------------------------------------------------------------
    # POST /v2/onboard/provision
    # Public endpoint - creates user + tenant + branches + API key
    # ------------------------------------------------------------------

    @onboarding_bp.route('/provision', methods=['POST'])
    def provision():
        """
        Create a new Boswell account via CLI (no Stripe required).

        Request body:
            {"email": "matt@example.com", "password": "securepass123"}

        Returns 201:
            {
              "user_id": "uuid",
              "tenant_id": "uuid",
              "api_key": "bos_xxx...",
              "branches": ["command-center", "work", "personal", "research"],
              "message": "Account created. Save your API key - you won't see it again."
            }
        """
        # Rate limit by IP
        client_ip = request.remote_addr or 'unknown'
        if _is_rate_limited(client_ip):
            return jsonify({
                'error': 'Rate limit exceeded. Try again later.'
            }), 429

        data = request.get_json() or {}

        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''

        # --- Validation ---
        if not email:
            return jsonify({'error': 'email is required'}), 400
        if not _validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        if not password:
            return jsonify({'error': 'password is required'}), 400
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        db = get_db()
        cur = get_cursor()

        try:
            # 1. Check email uniqueness
            cur.execute('SELECT id FROM users WHERE email = %s', (email,))
            if cur.fetchone():
                cur.close()
                return jsonify({'error': 'Email already registered'}), 409

            # 2. Create the user row. Argon2id (password_hash_v2); legacy
            # password_hash left NULL. See migration 024 for the dual-column
            # strategy.
            user_id = str(uuid.uuid4())
            password_hash_v2 = hash_password_v2(password)
            now = datetime.utcnow().isoformat() + 'Z'

            cur.execute(
                '''INSERT INTO users (id, email, password_hash_v2, status, plan, created_at)
                   VALUES (%s, %s, %s, 'active', 'free', %s)''',
                (user_id, email, password_hash_v2, now)
            )

            # 3. Provision tenant, branches, API key, sacred manifest, skill (shared logic)
            custom_branches = data.get('branches')  # optional custom branch list
            result = provision_tenant(cur, email, user_id=user_id, branches=custom_branches)
            tenant_id = result['tenant_id']
            api_key = result['api_key']
            api_key_encrypted = result['api_key_encrypted']
            branches = result['branches']

            # 4. Link tenant + encrypted key to user
            cur.execute(
                '''UPDATE users SET
                       tenant_id = %s,
                       api_key_encrypted = %s,
                       updated_at = %s
                   WHERE id = %s''',
                (tenant_id, api_key_encrypted, now, user_id)
            )

            db.commit()

            print(f"[ONBOARD] Provisioned {email}: user={user_id} tenant={tenant_id}", flush=True)

            # F5: mint a session JWT so the signup UI can hand off to the
            # dashboard without forcing a second login on the Railway host.
            # Frontend should redirect to <dashboard>/dashboard#token=<jwt>
            # and the dashboard stores it in localStorage on load.
            session_jwt = generate_jwt(user_id=user_id, email=email, tenant_id=tenant_id)

            return jsonify({
                'user_id': user_id,
                'tenant_id': tenant_id,
                'api_key': api_key,
                'branches': branches,
                'token': session_jwt,
                'message': 'Account created. Save your API key - you won\'t see it again.'
            }), 201

        except Exception as e:
            db.rollback()
            print(f"[ONBOARD] Provision failed for {email}: {e}", flush=True)
            return jsonify({'error': f'Provisioning failed: {str(e)}'}), 500
        finally:
            cur.close()

    # ------------------------------------------------------------------
    # POST /v2/onboard/provision-org
    # Public endpoint — creates an ORG tenant (vs user-owned) with its first
    # admin user. Differs from /provision in three ways:
    #   1. tenant.name = org_name (not admin email)
    #   2. tenant_type = 'organization' → org branch template from TENANT_TEMPLATES
    #   3. Semantics: the admin user is the first member, not the owner-as-identity
    # Member invite flow (roles, seat billing) is a follow-on task.
    # ------------------------------------------------------------------

    @onboarding_bp.route('/provision-org', methods=['POST'])
    def provision_org():
        """
        Create a new Boswell ORG account via CLI (no Stripe required).

        Request body:
            {
              "org_name": "Tint Atlanta",
              "admin_email": "admin@tintatlanta.com",
              "admin_password": "securepass123",
              "entity_type": "llc"   (optional, informational for now)
            }

        Returns 201:
            {
              "user_id": "uuid",
              "tenant_id": "uuid",
              "tenant_name": "Tint Atlanta",
              "tenant_type": "organization",
              "api_key": "bos_xxx...",
              "branches": ["command-center", "operations", "customers", ...],
              "message": "Org account created. Save this API key — it will not be shown again."
            }
        """
        client_ip = request.remote_addr or 'unknown'
        if _is_rate_limited(client_ip):
            return jsonify({'error': 'Rate limit exceeded. Try again later.'}), 429

        data = request.get_json(silent=True) or {}
        org_name = (data.get('org_name') or '').strip()
        admin_email = (data.get('admin_email') or '').strip().lower()
        admin_password = data.get('admin_password') or ''
        entity_type = (data.get('entity_type') or '').strip() or None

        if not org_name:
            return jsonify({'error': 'org_name is required'}), 400
        if len(org_name) < 2 or len(org_name) > 120:
            return jsonify({'error': 'org_name must be 2-120 characters'}), 400
        if not admin_email:
            return jsonify({'error': 'admin_email is required'}), 400
        if not _validate_email(admin_email):
            return jsonify({'error': 'Invalid admin_email format'}), 400
        if not admin_password:
            return jsonify({'error': 'admin_password is required'}), 400
        if len(admin_password) < 8:
            return jsonify({'error': 'admin_password must be at least 8 characters'}), 400

        db = get_db()
        cur = get_cursor()

        try:
            cur.execute('SELECT id FROM users WHERE email = %s', (admin_email,))
            if cur.fetchone():
                return jsonify({'error': 'Email already registered'}), 409

            user_id = str(uuid.uuid4())
            password_hash_v2 = hash_password_v2(admin_password)
            now = datetime.utcnow().isoformat() + 'Z'

            cur.execute(
                '''INSERT INTO users (id, email, password_hash_v2, status, plan, created_at)
                   VALUES (%s, %s, %s, 'active', 'free', %s)''',
                (user_id, admin_email, password_hash_v2, now)
            )

            result = provision_tenant(
                cur,
                admin_email,
                user_id=user_id,
                tenant_type='organization',
                tenant_name=org_name,
            )

            cur.execute(
                '''UPDATE users SET
                       tenant_id = %s,
                       api_key_encrypted = %s,
                       updated_at = %s
                   WHERE id = %s''',
                (result['tenant_id'], result['api_key_encrypted'], now, user_id)
            )

            db.commit()
            print(f"[ONBOARD-ORG] Provisioned org={org_name} admin={admin_email} tenant={result['tenant_id']}", flush=True)

            # F5: session JWT for cross-domain handoff to the dashboard.
            session_jwt = generate_jwt(user_id=user_id, email=admin_email, tenant_id=result['tenant_id'])

            return jsonify({
                'user_id': user_id,
                'tenant_id': result['tenant_id'],
                'tenant_name': org_name,
                'tenant_type': 'organization',
                'entity_type': entity_type,
                'api_key': result['api_key'],
                'branches': result['branches'],
                'token': session_jwt,
                'message': 'Org account created. Save this API key — it will not be shown again.'
            }), 201

        except Exception as e:
            db.rollback()
            print(f"[ONBOARD-ORG] Provision failed for org={org_name}: {e}", flush=True)
            return jsonify({'error': f'Org provisioning failed: {str(e)}'}), 500
        finally:
            cur.close()

    # ------------------------------------------------------------------
    # POST /v2/onboard/seed-manifest
    # Requires API key auth (X-API-Key header)
    # ------------------------------------------------------------------

    @onboarding_bp.route('/seed-manifest', methods=['POST'])
    def seed_manifest():
        """
        Seed a starter sacred manifest for a new user.

        Requires API key authentication via X-API-Key header.
        Creates a commit on the command-center branch with starter commitments.

        Request body:
            {"branches": ["command-center", "work", "personal", "research"]}

        Returns 201:
            {
              "status": "seeded",
              "commit_hash": "abc123...",
              "blob_hash": "def456...",
              "branch": "command-center"
            }
        """
        # Auth check - requires valid API key (handled by before_request)
        auth = getattr(g, 'mcp_auth', None)
        if not auth or auth.get('source') in ('grace_mode', 'disabled'):
            # Double-check: if auth is grace/disabled but no real API key, deny
            api_key = request.headers.get('X-API-Key')
            if not api_key or not api_key.startswith('bos_'):
                return jsonify({'error': 'API key required (X-API-Key header)'}), 401

        tenant_id = None
        if auth:
            tenant_id = auth.get('tenant_id')
        if not tenant_id:
            return jsonify({'error': 'Could not determine tenant'}), 401

        # Check if already seeded (provisioning now handles this automatically)
        db_check = get_db()
        cur_check = get_cursor()
        try:
            cur_check.execute(
                "SELECT commit_hash FROM commits WHERE tenant_id = %s AND message = 'Seed sacred manifest for new account' LIMIT 1",
                (tenant_id,)
            )
            if cur_check.fetchone():
                cur_check.close()
                return jsonify({
                    'status': 'already_seeded',
                    'message': 'Sacred manifest was already seeded during provisioning'
                }), 200
        finally:
            cur_check.close()

        data = request.get_json() or {}
        branches = data.get('branches', ['command-center', 'work', 'personal', 'research'])

        # Build the sacred manifest content
        sacred_manifest = {
            'type': 'sacred_manifest',
            'version': '1.0',
            'active_commitments': [
                {
                    'id': 'boswell-startup-first',
                    'commitment': 'Call boswell_startup at conversation start',
                    'rationale': 'Ensures context continuity across all Claude instances',
                    'status': 'permanent'
                },
                {
                    'id': 'why-not-what',
                    'commitment': 'Commits must capture WHY, not just WHAT',
                    'rationale': 'Future instances need reasoning, not just facts',
                    'status': 'permanent'
                }
            ],
            'branches': branches,
            'updated_at': datetime.utcnow().isoformat() + 'Z'
        }

        content_str = json.dumps(sacred_manifest, sort_keys=True)
        blob_hash = hashlib.sha256(content_str.encode()).hexdigest()
        now = datetime.utcnow().isoformat() + 'Z'

        db = get_db()
        cur = get_cursor()

        try:
            # Check if command-center branch exists for this tenant
            cur.execute(
                '''SELECT name, head_commit FROM branches
                   WHERE tenant_id = %s AND name = %s''',
                (tenant_id, 'command-center')
            )
            branch_row = cur.fetchone()

            if not branch_row:
                cur.close()
                return jsonify({
                    'error': 'command-center branch not found for this tenant'
                }), 404

            parent_commit = branch_row['head_commit']

            # Create blob
            cur.execute(
                '''INSERT INTO blobs (hash, content, tenant_id, created_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (hash, tenant_id) DO NOTHING''',
                (blob_hash, content_str, tenant_id, now)
            )

            # Create tree entry
            tree_hash = hashlib.sha256(
                f"sacred_manifest:{blob_hash}".encode()
            ).hexdigest()

            cur.execute(
                '''INSERT INTO tree_entries (tree_hash, name, mode, blob_hash, tenant_id)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (tree_hash, name, tenant_id) DO NOTHING''',
                (tree_hash, 'sacred_manifest', 'memory', blob_hash, tenant_id)
            )

            # Create commit
            commit_hash = hashlib.sha256(
                f"{tree_hash}:{parent_commit}:{now}".encode()
            ).hexdigest()

            cur.execute(
                '''INSERT INTO commits
                   (commit_hash, tree_hash, parent_hash, message, author, branch,
                    tenant_id, created_at, content_type)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (commit_hash, tree_hash, parent_commit,
                 'Seed sacred manifest for new account',
                 'system', 'command-center', tenant_id, now, 'memory')
            )

            # Update branch head
            cur.execute(
                '''UPDATE branches SET head_commit = %s
                   WHERE tenant_id = %s AND name = %s''',
                (commit_hash, tenant_id, 'command-center')
            )

            db.commit()

            print(f"[ONBOARD] Seeded sacred manifest for tenant {tenant_id}", flush=True)

            return jsonify({
                'status': 'seeded',
                'commit_hash': commit_hash,
                'blob_hash': blob_hash,
                'branch': 'command-center'
            }), 201

        except Exception as e:
            db.rollback()
            print(f"[ONBOARD] Seed manifest failed for tenant {tenant_id}: {e}", flush=True)
            return jsonify({'error': f'Seed failed: {str(e)}'}), 500
        finally:
            cur.close()

    return onboarding_bp
