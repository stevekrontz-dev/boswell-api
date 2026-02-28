"""
Auth Module for Boswell SaaS
Owner: CC1
Domain: Auth & Multi-tenancy
"""

import os
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', secrets.token_hex(32))
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_HOURS = int(os.environ.get('JWT_EXPIRY_HOURS', 168))


def generate_jwt(user_id: str, email: str, tenant_id: str = None) -> str:
    """Generate a JWT token for authenticated user."""
    payload = {
        'sub': user_id,
        'email': email,
        'tenant_id': tenant_id,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> dict:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError('Token has expired')
    except jwt.InvalidTokenError as e:
        raise ValueError(f'Invalid token: {str(e)}')


def hash_password(password: str) -> str:
    """Hash password using SHA256 with salt."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash."""
    try:
        salt, hashed = stored_hash.split(':')
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except ValueError:
        return False


def require_jwt(f):
    """Decorator to require JWT authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authorization header required'}), 401

        token = auth_header[7:]

        try:
            payload = verify_jwt(token)
            g.current_user = payload
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({'error': str(e)}), 401

    return decorated


# Simple encryption for storing API keys (for display in dashboard)
# Uses Fernet symmetric encryption derived from JWT_SECRET

def get_fernet():
    """Get Fernet instance for API key encryption."""
    import base64
    from cryptography.fernet import Fernet
    # Derive a 32-byte key from JWT_SECRET
    key_bytes = hashlib.sha256(JWT_SECRET.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_api_key(api_key: str) -> str:
    """Encrypt API key for storage."""
    fernet = get_fernet()
    return fernet.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    """Decrypt stored API key."""
    fernet = get_fernet()
    return fernet.decrypt(encrypted.encode()).decode()


# ==================== AUTH0 OAUTH 2.1 ====================
AUTH0_DOMAIN = os.environ.get('AUTH0_DOMAIN', '')
AUTH0_AUDIENCE = os.environ.get('AUTH0_AUDIENCE', '')
AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'false').lower() == 'true'
AUTH_GRACE_MODE = os.environ.get('AUTH_GRACE_MODE', 'false').lower() == 'true'
INTERNAL_SECRET = os.environ.get('INTERNAL_SECRET', '')
DEFAULT_TENANT = '00000000-0000-0000-0000-000000000001'

_jwks_client = None


def get_jwks_client():
    """Lazy-init JWKS client for Auth0."""
    global _jwks_client
    if _jwks_client is None and AUTH0_DOMAIN:
        from jwt import PyJWKClient
        _jwks_client = PyJWKClient(
            f'https://{AUTH0_DOMAIN}/.well-known/jwks.json',
            cache_keys=True,
            lifespan=3600
        )
    return _jwks_client


def _is_jwt_format(token: str) -> bool:
    """Check if token looks like a JWT (three dot-separated base64url parts)."""
    parts = token.split('.')
    return len(parts) == 3 and all(len(p) > 0 for p in parts)


def _validate_via_userinfo(token: str) -> dict:
    """Validate opaque token via Auth0 /userinfo endpoint.
    Returns partial auth info (tenant_id=None, needs DB lookup)."""
    import sys
    import urllib.request
    import json as _json

    if not AUTH0_DOMAIN:
        return None

    try:
        url = f'https://{AUTH0_DOMAIN}/userinfo'
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {token}'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_body = resp.read().decode()
            print(f'[AUTH] /userinfo raw response ({len(raw_body)} chars): {raw_body[:500]}', file=sys.stderr)
            userinfo = _json.loads(raw_body)

        sub = userinfo.get('sub')
        email = userinfo.get('email')

        if not sub:
            print(f'[AUTH] /userinfo returned no sub. Keys: {list(userinfo.keys())}', file=sys.stderr)
            return None

        print(f'[AUTH] Opaque token validated via /userinfo: sub={sub} email={email}', file=sys.stderr)
        return {
            'user_id': sub,
            'tenant_id': None,  # Resolved in check_mcp_auth via DB
            'scope': '',
            'email': email,
            'source': 'auth0_userinfo'
        }
    except Exception as e:
        print(f'[AUTH] /userinfo failed: {e}', file=sys.stderr)
        return None


def validate_auth0_token(token: str) -> dict:
    """Validate Auth0 token. Tries JWT first, falls back to /userinfo for opaque tokens."""
    import sys

    # Log token structure for debugging
    dot_count = token.count('.')
    print(f'[AUTH] Token: {len(token)} chars, {dot_count} dots, first20={token[:20]}...', file=sys.stderr)

    # Opaque token — skip JWT decode, go straight to /userinfo
    if not _is_jwt_format(token):
        print(f'[AUTH] Token is opaque, trying /userinfo', file=sys.stderr)
        return _validate_via_userinfo(token)

    # JWT path
    jwks = get_jwks_client()
    if not jwks:
        return None

    try:
        signing_key = jwks.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=['RS256'],
            audience=AUTH0_AUDIENCE,
            issuer=f'https://{AUTH0_DOMAIN}/'
        )
        tenant_id = payload.get('https://boswell.app/tenant_id')
        if not tenant_id:
            print(f'[AUTH] Auth0 JWT valid but missing tenant_id claim for {payload.get("email")}', file=sys.stderr)
            return {
                'user_id': payload['sub'],
                'tenant_id': None,  # Resolved in check_mcp_auth via DB
                'scope': payload.get('scope', ''),
                'email': payload.get('email'),
                'source': 'auth0'
            }
        return {
            'user_id': payload['sub'],
            'tenant_id': tenant_id,
            'scope': payload.get('scope', ''),
            'email': payload.get('email'),
            'source': 'auth0'
        }
    except Exception as e:
        print(f'[AUTH] Auth0 JWT decode failed: {e}, trying /userinfo fallback', file=sys.stderr)
        return _validate_via_userinfo(token)


def is_internal_request():
    """Check if request is from stdio (server.py → app.py)."""
    return INTERNAL_SECRET and request.headers.get('X-Boswell-Internal') == INTERNAL_SECRET


def check_mcp_auth(get_cursor_func, get_db_func=None):
    """
    MCP auth check for before_request.
    Returns None if OK, or (response, status) if denied.
    """
    import sys

    # Auth disabled - allow all
    if not AUTH_ENABLED:
        g.mcp_auth = {'source': 'disabled', 'tenant_id': DEFAULT_TENANT}
        return None

    # Skip discovery/health/public endpoints
    PUBLIC_PATHS = [
        '/', '/health', '/v2/health', '/v2/health/daemon', '/v2/health/ping',
        '/api/health', '/.well-known/oauth-protected-resource',
        '/.well-known/oauth-authorization-server',
        '/oauth/authorize', '/oauth/token', '/oauth/register',
        '/oauth/callback/github',
        '/v2/onboard/provision',  # Public signup — no auth required
        '/v2/auth/register',      # Public registration
    ]
    if request.path in PUBLIC_PATHS or request.path.startswith('/party'):
        return None

    # Internal request (stdio) - CRITICAL: protects CC/Desktop
    if is_internal_request():
        g.mcp_auth = {'source': 'internal', 'tenant_id': DEFAULT_TENANT}
        return None

    # Check API key auth (X-API-Key header)
    api_key = request.headers.get('X-API-Key')
    if api_key and api_key.startswith('bos_'):
        from auth.api_keys import validate_api_key
        key_info = validate_api_key(api_key, get_cursor_func, get_db_func)
        if key_info:
            tenant_id = key_info.get('tenant_id')
            if not tenant_id:
                # API key exists but has no tenant — deny, don't fall through to Steve's data
                print(f'[AUTH] API key valid but missing tenant_id, denying', file=sys.stderr)
                return jsonify({'error': 'forbidden', 'error_description': 'API key not associated with a tenant'}), 403
            g.mcp_auth = {
                'source': 'api_key',
                'tenant_id': tenant_id,
                'user_id': key_info.get('user_id'),
            }
            return None
        # Invalid API key — fall through to denial

    # Check Bearer token (our own JWT first, then Auth0 fallback)
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]

        # Try our own JWT first (from Boswell OAuth server)
        try:
            payload = verify_jwt(token)
            tenant_id = payload.get('tenant_id')
            if tenant_id:
                print(f'[AUTH] Boswell JWT valid for {payload.get("email")} tenant={tenant_id}', file=sys.stderr)
                g.mcp_auth = {
                    'source': 'boswell_jwt',
                    'tenant_id': tenant_id,
                    'user_id': payload.get('sub'),
                    'email': payload.get('email'),
                    'scope': '',
                }
                return None
        except ValueError:
            pass  # Not our JWT, try Auth0

        # Auth0 token fallback
        auth_info = validate_auth0_token(token)
        if auth_info:
            # Resolve tenant_id from DB if missing (opaque tokens, JWT without claim)
            if not auth_info.get('tenant_id') and auth_info.get('email'):
                try:
                    cur = get_cursor_func()
                    cur.execute('SELECT tenant_id FROM users WHERE email = %s', (auth_info['email'],))
                    row = cur.fetchone()
                    cur.close()
                    if row and row.get('tenant_id'):
                        auth_info['tenant_id'] = str(row['tenant_id'])
                        print(f'[AUTH] Resolved tenant {auth_info["tenant_id"]} from DB for {auth_info["email"]}', file=sys.stderr)
                except Exception as e:
                    print(f'[AUTH] Tenant DB lookup failed: {e}', file=sys.stderr)
            if not auth_info.get('tenant_id'):
                print(f'[AUTH] Auth0 user {auth_info.get("email")} has no tenant — denying', file=sys.stderr)
                return jsonify({
                    'error': 'forbidden',
                    'error_description': 'No tenant associated with this account. Register at /v2/onboard/provision first.'
                }), 403
            g.mcp_auth = auth_info
            return None

    # No valid auth — grace mode logs but allows through
    if AUTH_GRACE_MODE:
        print(
            f'[AUTH-GRACE] Unauthenticated request: {request.method} {request.path} '
            f'from {request.remote_addr}',
            file=sys.stderr
        )
        g.mcp_auth = {'source': 'grace_mode', 'tenant_id': DEFAULT_TENANT}
        return None

    # Hard deny
    return jsonify({
        'error': 'unauthorized',
        'error_description': 'Valid authentication required'
    }), 401
