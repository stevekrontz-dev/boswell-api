"""
API Key Management Module
Owner: CC1
Task: W1P3 - API Key Management (BLOCKING CC4)
"""

import secrets
import hashlib
import uuid
from flask import Blueprint, request, jsonify, g
from . import require_jwt

api_keys_bp = Blueprint('api_keys', __name__, url_prefix='/v2/auth/keys')


def generate_api_key() -> str:
    """Generate a new API key with bos_ prefix."""
    raw = secrets.token_urlsafe(32)
    return f"bos_{raw}"


def hash_key(key: str) -> str:
    """Hash API key using SHA256."""
    return hashlib.sha256(key.encode()).hexdigest()


def mask_key(key_hash: str) -> str:
    """Create a masked preview of the key hash for display."""
    # Since we don't store the original key, show hash preview
    return f"bos_****...{key_hash[-8:]}"


def init_api_keys(get_db, get_cursor):
    """Initialize API keys routes with database access."""

    @api_keys_bp.route('/create', methods=['POST'])
    @require_jwt
    def create_key():
        """
        Create a new API key.

        Request body:
        {
            "name": "My CLI Key"
        }

        Returns:
        {
            "id": "uuid",
            "key": "bos_xxxxx",  # SHOWN ONCE ONLY
            "name": "My CLI Key",
            "created_at": "timestamp"
        }
        """
        data = request.get_json() or {}
        name = data.get('name', '').strip() or 'Unnamed Key'

        user_id = g.current_user.get('sub')
        tenant_id = g.current_user.get('tenant_id')

        # Generate the key
        raw_key = generate_api_key()
        key_hash = hash_key(raw_key)

        cur = get_cursor()
        db = get_db()

        try:
            key_id = str(uuid.uuid4())

            cur.execute(
                '''INSERT INTO api_keys (id, tenant_id, user_id, key_hash, name, created_at)
                   VALUES (%s, %s, %s, %s, %s, NOW())
                   RETURNING created_at''',
                (key_id, tenant_id, user_id, key_hash, name)
            )
            result = cur.fetchone()
            created_at = result['created_at'] if result else None

            db.commit()
            cur.close()

            return jsonify({
                'id': key_id,
                'key': raw_key,  # WARNING: Shown once only!
                'name': name,
                'created_at': str(created_at),
                'warning': 'Save this key now. It will not be shown again.'
            }), 201

        except Exception as e:
            db.rollback()
            cur.close()
            return jsonify({'error': f'Failed to create key: {str(e)}'}), 500

    @api_keys_bp.route('', methods=['GET'])
    @require_jwt
    def list_keys():
        """
        List all API keys for the current user/tenant.

        Returns:
        [
            {
                "id": "uuid",
                "name": "My CLI Key",
                "key_preview": "bos_****...xxxx",
                "created_at": "timestamp",
                "last_used_at": "timestamp"
            }
        ]
        """
        user_id = g.current_user.get('sub')
        tenant_id = g.current_user.get('tenant_id')

        cur = get_cursor()

        try:
            # Get keys for this user (or tenant if admin)
            cur.execute(
                '''SELECT id, name, key_hash, created_at, last_used_at
                   FROM api_keys
                   WHERE user_id = %s AND revoked_at IS NULL
                   ORDER BY created_at DESC''',
                (user_id,)
            )
            rows = cur.fetchall()
            cur.close()

            keys = []
            for row in rows:
                keys.append({
                    'id': str(row['id']),
                    'name': row['name'],
                    'key_preview': mask_key(row['key_hash']),
                    'created_at': str(row['created_at']) if row['created_at'] else None,
                    'last_used_at': str(row['last_used_at']) if row['last_used_at'] else None
                })

            return jsonify(keys), 200

        except Exception as e:
            cur.close()
            return jsonify({'error': f'Failed to list keys: {str(e)}'}), 500

    @api_keys_bp.route('/<key_id>', methods=['DELETE'])
    @require_jwt
    def revoke_key(key_id):
        """
        Revoke (soft delete) an API key.

        Returns:
        {
            "success": true,
            "message": "Key revoked"
        }
        """
        user_id = g.current_user.get('sub')

        cur = get_cursor()
        db = get_db()

        try:
            # Verify key belongs to user and revoke it
            cur.execute(
                '''UPDATE api_keys
                   SET revoked_at = NOW()
                   WHERE id = %s AND user_id = %s AND revoked_at IS NULL
                   RETURNING id''',
                (key_id, user_id)
            )
            result = cur.fetchone()

            if not result:
                cur.close()
                return jsonify({'error': 'Key not found or already revoked'}), 404

            db.commit()
            cur.close()

            return jsonify({
                'success': True,
                'message': 'Key revoked'
            }), 200

        except Exception as e:
            db.rollback()
            cur.close()
            return jsonify({'error': f'Failed to revoke key: {str(e)}'}), 500

    return api_keys_bp


def validate_api_key(key: str, get_cursor, get_db) -> dict:
    """
    Validate an API key and return tenant info.
    Used by MCP handler for API key authentication.

    Returns:
        dict with tenant_id, user_id if valid
        None if invalid
    """
    if not key or not key.startswith('bos_'):
        return None

    key_hash = hash_key(key)
    cur = get_cursor()
    db = get_db()

    try:
        cur.execute(
            '''SELECT tenant_id, user_id
               FROM api_keys
               WHERE key_hash = %s AND revoked_at IS NULL''',
            (key_hash,)
        )
        result = cur.fetchone()

        if result:
            # Update last_used_at
            cur.execute(
                '''UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = %s''',
                (key_hash,)
            )
            db.commit()
            cur.close()
            return {
                'tenant_id': str(result['tenant_id']) if result['tenant_id'] else None,
                'user_id': str(result['user_id']) if result['user_id'] else None
            }

        cur.close()
        return None

    except Exception:
        cur.close()
        return None
