"""
Boswell OAuth 2.1 Authorization Server
Owner: CC1

Minimal OAuth server for MCP connector auth. Replaces Auth0 proxy
approach which failed because Auth0 returns opaque JWE tokens when
the client doesn't pass audience (Auth0-specific param, not in RFC 8707).

Flow:
1. Client redirects to /oauth/authorize
2. User sees login form, enters email + password
3. Server validates, generates auth code, redirects to client callback
4. Client exchanges code at /oauth/token for a JWT
5. JWT is validated by existing verify_jwt() / check_mcp_auth()
"""

import os
import secrets
import time
import sys
from string import Template
from urllib.parse import urlencode, urlparse, parse_qs

from flask import Blueprint, request, jsonify, redirect, make_response

from auth import (
    verify_password, generate_jwt, verify_jwt,
    JWT_SECRET, JWT_ALGORITHM
)

oauth_bp = Blueprint('oauth', __name__)

# In-memory auth code store: code -> {user_id, email, tenant_id, redirect_uri, client_id, expires, code_challenge, code_challenge_method}
_auth_codes = {}
# In-memory refresh token store: token -> {user_id, email, tenant_id, client_id}
_refresh_tokens = {}
# In-memory client registration store: client_id -> {client_secret, redirect_uris, ...}
_registered_clients = {}

CODE_TTL = 300  # 5 minutes


def _cleanup_expired_codes():
    """Remove expired auth codes."""
    now = time.time()
    expired = [k for k, v in _auth_codes.items() if v['expires'] < now]
    for k in expired:
        del _auth_codes[k]


def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    """Verify PKCE code challenge."""
    if method == 'plain':
        return code_verifier == code_challenge
    elif method == 'S256':
        import hashlib
        import base64
        digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
        return computed == code_challenge
    return False


LOGIN_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Boswell — Sign In</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0a; color: #e0e0e0; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
  .card { background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 2rem; width: 100%; max-width: 380px; }
  h1 { font-size: 1.5rem; margin: 0 0 0.5rem; color: #fff; }
  p { color: #888; font-size: 0.9rem; margin: 0 0 1.5rem; }
  label { display: block; font-size: 0.85rem; color: #aaa; margin-bottom: 0.3rem; }
  input { width: 100%; padding: 0.6rem; background: #111; border: 1px solid #333; border-radius: 6px; color: #fff; font-size: 1rem; margin-bottom: 1rem; box-sizing: border-box; }
  input:focus { outline: none; border-color: #4a9eff; }
  button { width: 100%; padding: 0.7rem; background: #4a9eff; color: #fff; border: none; border-radius: 6px; font-size: 1rem; cursor: pointer; }
  button:hover { background: #3a8eef; }
  .error { color: #ff6b6b; font-size: 0.85rem; margin-bottom: 1rem; }
</style>
</head><body>
<div class="card">
  <h1>Boswell</h1>
  <p>Sign in to connect your memory system</p>
  $error
  <form method="POST">
    <input type="hidden" name="state" value="$state">
    <input type="hidden" name="redirect_uri" value="$redirect_uri">
    <input type="hidden" name="client_id" value="$client_id">
    <input type="hidden" name="code_challenge" value="$code_challenge">
    <input type="hidden" name="code_challenge_method" value="$code_challenge_method">
    <input type="hidden" name="scope" value="$scope">
    <label>Email</label>
    <input type="email" name="email" required autofocus>
    <label>Password</label>
    <input type="password" name="password" required>
    <button type="submit">Sign In</button>
  </form>
</div>
</body></html>"""


def init_oauth(get_db, get_cursor):
    """Initialize OAuth blueprint with database access."""

    @oauth_bp.route('/oauth/authorize', methods=['GET'])
    def authorize_get():
        """Show login form for OAuth authorization."""
        state = request.args.get('state', '')
        redirect_uri = request.args.get('redirect_uri', '')
        client_id = request.args.get('client_id', '')
        code_challenge = request.args.get('code_challenge', '')
        code_challenge_method = request.args.get('code_challenge_method', 'S256')
        scope = request.args.get('scope', '')

        html = Template(LOGIN_HTML).safe_substitute(
            state=state,
            redirect_uri=redirect_uri,
            client_id=client_id,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            error=''
        )
        return make_response(html, 200, {'Content-Type': 'text/html'})

    @oauth_bp.route('/oauth/authorize', methods=['POST'])
    def authorize_post():
        """Process login and issue authorization code."""
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        state = request.form.get('state', '')
        redirect_uri = request.form.get('redirect_uri', '')
        client_id = request.form.get('client_id', '')
        code_challenge = request.form.get('code_challenge', '')
        code_challenge_method = request.form.get('code_challenge_method', 'S256')
        scope = request.form.get('scope', '')

        def _error(msg):
            html = Template(LOGIN_HTML).safe_substitute(
                state=state,
                redirect_uri=redirect_uri,
                client_id=client_id,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                scope=scope,
                error=f'<div class="error">{msg}</div>'
            )
            return make_response(html, 200, {'Content-Type': 'text/html'})

        if not email or not password:
            return _error('Email and password required')

        # Look up user
        cur = get_cursor()
        try:
            cur.execute(
                'SELECT id, email, password_hash, tenant_id, status FROM users WHERE email = %s',
                (email,)
            )
            user = cur.fetchone()
        finally:
            cur.close()

        if not user:
            return _error('Invalid email or password')

        if not verify_password(password, user['password_hash']):
            return _error('Invalid email or password')

        if user['status'] != 'active':
            return _error('Account not active')

        if not user.get('tenant_id'):
            return _error('No tenant associated with this account')

        # Generate authorization code
        _cleanup_expired_codes()
        code = secrets.token_urlsafe(32)
        _auth_codes[code] = {
            'user_id': str(user['id']),
            'email': user['email'],
            'tenant_id': str(user['tenant_id']),
            'redirect_uri': redirect_uri,
            'client_id': client_id,
            'code_challenge': code_challenge,
            'code_challenge_method': code_challenge_method,
            'expires': time.time() + CODE_TTL,
        }

        print(f'[OAUTH] Issued auth code for {email} → {redirect_uri[:60]}...', file=sys.stderr)

        # Redirect back to client with code
        sep = '&' if '?' in redirect_uri else '?'
        callback = f'{redirect_uri}{sep}{urlencode({"code": code, "state": state})}'
        return redirect(callback)

    @oauth_bp.route('/oauth/token', methods=['POST'])
    def token():
        """Exchange authorization code or refresh token for JWT."""
        # Accept both form-encoded and JSON
        if request.is_json:
            data = request.get_json()
        else:
            data = dict(request.form)

        grant_type = data.get('grant_type')

        if grant_type == 'authorization_code':
            return _handle_auth_code(data)
        elif grant_type == 'refresh_token':
            return _handle_refresh_token(data)
        else:
            return jsonify({'error': 'unsupported_grant_type'}), 400

    def _handle_auth_code(data):
        code = data.get('code')
        redirect_uri = data.get('redirect_uri', '')
        code_verifier = data.get('code_verifier', '')

        _cleanup_expired_codes()

        if not code or code not in _auth_codes:
            print(f'[OAUTH] Invalid/expired auth code', file=sys.stderr)
            return jsonify({'error': 'invalid_grant', 'error_description': 'Invalid or expired authorization code'}), 400

        code_data = _auth_codes.pop(code)

        # Verify redirect_uri matches
        if redirect_uri and redirect_uri != code_data['redirect_uri']:
            print(f'[OAUTH] redirect_uri mismatch', file=sys.stderr)
            return jsonify({'error': 'invalid_grant', 'error_description': 'redirect_uri mismatch'}), 400

        # Verify PKCE
        if code_data['code_challenge']:
            if not code_verifier:
                return jsonify({'error': 'invalid_grant', 'error_description': 'code_verifier required'}), 400
            if not _verify_pkce(code_verifier, code_data['code_challenge'], code_data['code_challenge_method']):
                print(f'[OAUTH] PKCE verification failed', file=sys.stderr)
                return jsonify({'error': 'invalid_grant', 'error_description': 'PKCE verification failed'}), 400

        # Generate JWT access token
        access_token = generate_jwt(
            user_id=code_data['user_id'],
            email=code_data['email'],
            tenant_id=code_data['tenant_id']
        )

        # Generate refresh token
        refresh = secrets.token_urlsafe(48)
        _refresh_tokens[refresh] = {
            'user_id': code_data['user_id'],
            'email': code_data['email'],
            'tenant_id': code_data['tenant_id'],
            'client_id': code_data['client_id'],
        }

        print(f'[OAUTH] Issued JWT for {code_data["email"]} (tenant={code_data["tenant_id"]})', file=sys.stderr)

        return jsonify({
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': 168 * 3600,  # 7 days
            'refresh_token': refresh,
        })

    def _handle_refresh_token(data):
        refresh = data.get('refresh_token')

        if not refresh or refresh not in _refresh_tokens:
            return jsonify({'error': 'invalid_grant', 'error_description': 'Invalid refresh token'}), 400

        token_data = _refresh_tokens[refresh]

        # Issue new access token
        access_token = generate_jwt(
            user_id=token_data['user_id'],
            email=token_data['email'],
            tenant_id=token_data['tenant_id']
        )

        # Rotate refresh token
        new_refresh = secrets.token_urlsafe(48)
        _refresh_tokens[new_refresh] = token_data
        del _refresh_tokens[refresh]

        print(f'[OAUTH] Refreshed JWT for {token_data["email"]}', file=sys.stderr)

        return jsonify({
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': 168 * 3600,
            'refresh_token': new_refresh,
        })

    @oauth_bp.route('/oauth/register', methods=['POST'])
    def register_client():
        """RFC 7591 - Dynamic Client Registration.
        MCP clients register themselves to get a client_id."""
        data = request.get_json() or {}

        client_id = secrets.token_urlsafe(24)
        client_secret = secrets.token_urlsafe(32)

        _registered_clients[client_id] = {
            'client_secret': client_secret,
            'redirect_uris': data.get('redirect_uris', []),
            'client_name': data.get('client_name', 'MCP Client'),
            'grant_types': data.get('grant_types', ['authorization_code', 'refresh_token']),
            'response_types': data.get('response_types', ['code']),
            'token_endpoint_auth_method': data.get('token_endpoint_auth_method', 'client_secret_post'),
        }

        print(f'[OAUTH] Registered client: {client_id} name={_registered_clients[client_id]["client_name"]}', file=sys.stderr)

        return jsonify({
            'client_id': client_id,
            'client_secret': client_secret,
            'client_id_issued_at': int(time.time()),
            'client_secret_expires_at': 0,  # never expires
            'redirect_uris': _registered_clients[client_id]['redirect_uris'],
            'client_name': _registered_clients[client_id]['client_name'],
            'grant_types': _registered_clients[client_id]['grant_types'],
            'response_types': _registered_clients[client_id]['response_types'],
            'token_endpoint_auth_method': _registered_clients[client_id]['token_endpoint_auth_method'],
        }), 201

    return oauth_bp
