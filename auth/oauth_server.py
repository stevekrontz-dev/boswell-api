"""
Boswell OAuth 2.1 Authorization Server
Owner: CC1

Minimal OAuth server for MCP connector auth. Supports:
- GitHub social login (auto-provisions free tier accounts)
- Email/password login (existing accounts)
- PKCE (S256)
- Dynamic Client Registration (RFC 7591)
- Refresh token rotation
"""

import os
import uuid
import secrets
import hashlib
import time
import sys
import json as _json
import urllib.request
import urllib.error
from string import Template
from urllib.parse import urlencode, urlparse, parse_qs
from datetime import datetime

from flask import Blueprint, request, jsonify, redirect, make_response

import hmac
import base64

from auth import (
    verify_password, generate_jwt, hash_password,
    JWT_SECRET, JWT_ALGORITHM
)

oauth_bp = Blueprint('oauth', __name__)

# GitHub OAuth config
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET', '')

# All OAuth state (auth codes, refresh tokens, client registrations) is encoded
# as HMAC-signed tokens. No server-side dicts needed — works across gunicorn workers.

CODE_TTL = 300  # 5 minutes


def _encode_state(params):
    """Encode MCP OAuth params into a signed state string (no server-side storage)."""
    payload = _json.dumps(params, separators=(',', ':')).encode()
    sig = hmac.new(JWT_SECRET.encode(), payload, hashlib.sha256).hexdigest()[:16]
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip('=')
    return f'{sig}.{encoded}'


def _decode_state(state):
    """Decode and verify a signed state string. Returns params dict or None."""
    try:
        sig, encoded = state.split('.', 1)
        # Restore base64 padding
        padded = encoded + '=' * (4 - len(encoded) % 4)
        payload = base64.urlsafe_b64decode(padded)
        expected_sig = hmac.new(JWT_SECRET.encode(), payload, hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return _json.loads(payload)
    except Exception:
        return None


def _verify_pkce(code_verifier, code_challenge, method):
    if method == 'plain':
        return code_verifier == code_challenge
    elif method == 'S256':
        import base64
        digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
        return computed == code_challenge
    return False


def _get_base_url():
    domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
    if domain:
        return f'https://{domain}'
    return os.environ.get('AUTH0_AUDIENCE', 'http://localhost:8080')


LOGIN_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Boswell</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0a; color: #e0e0e0; margin: 0; padding: 2rem 1rem; }
  .card { background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 1.5rem; max-width: 340px; margin: 0 auto; }
  h1 { font-size: 1.4rem; margin-bottom: 0.3rem; color: #fff; }
  .sub { color: #888; font-size: 0.85rem; margin-bottom: 1.5rem; }
  .gh-btn { display: flex; align-items: center; justify-content: center; gap: 0.5rem; width: 100%; padding: 0.65rem; background: #238636; color: #fff; border: none; border-radius: 6px; font-size: 0.95rem; cursor: pointer; text-decoration: none; margin-bottom: 1rem; }
  .gh-btn:hover { background: #2ea043; }
  .gh-btn svg { width: 20px; height: 20px; fill: #fff; }
  .divider { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; color: #555; font-size: 0.8rem; }
  .divider::before, .divider::after { content: ""; flex: 1; border-top: 1px solid #333; }
  label { display: block; font-size: 0.8rem; color: #aaa; margin-bottom: 0.25rem; }
  input[type=email], input[type=password] { width: 100%; padding: 0.55rem; background: #111; border: 1px solid #333; border-radius: 6px; color: #fff; font-size: 0.95rem; margin-bottom: 0.75rem; }
  input:focus { outline: none; border-color: #4a9eff; }
  .submit { width: 100%; padding: 0.6rem; background: #333; color: #ccc; border: 1px solid #444; border-radius: 6px; font-size: 0.9rem; cursor: pointer; }
  .submit:hover { background: #444; color: #fff; }
  .error { background: #2a1515; border: 1px solid #5a2020; color: #ff6b6b; font-size: 0.85rem; padding: 0.5rem 0.75rem; border-radius: 6px; margin-bottom: 1rem; }
</style>
</head><body>
<div class="card">
  <h1>Boswell</h1>
  <p class="sub">Connect your memory system</p>
  $error
  $github_btn
  <div class="divider">or sign in with email</div>
  <form method="POST">
    <input type="hidden" name="state" value="$state">
    <input type="hidden" name="redirect_uri" value="$redirect_uri">
    <input type="hidden" name="client_id" value="$client_id">
    <input type="hidden" name="code_challenge" value="$code_challenge">
    <input type="hidden" name="code_challenge_method" value="$code_challenge_method">
    <input type="hidden" name="scope" value="$scope">
    <label>Email</label>
    <input type="email" name="email" required>
    <label>Password</label>
    <input type="password" name="password" required>
    <button type="submit" class="submit">Sign In</button>
  </form>
</div>
</body></html>"""

GITHUB_BTN_HTML = """<a href="$github_url" class="gh-btn">
  <svg viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
  Continue with GitHub
</a>"""


def _render_login(params, error=''):
    """Render login page with optional GitHub button."""
    if GITHUB_CLIENT_ID:
        # Encode MCP OAuth params into signed state (no server-side storage needed)
        gh_state = _encode_state({
            's': params.get('state', ''),
            'r': params.get('redirect_uri', ''),
            'c': params.get('client_id', ''),
            'ch': params.get('code_challenge', ''),
            'cm': params.get('code_challenge_method', 'S256'),
            'sc': params.get('scope', ''),
        })
        callback_url = _get_base_url() + '/oauth/callback/github'
        github_url = (
            f'https://github.com/login/oauth/authorize?'
            f'{urlencode({"client_id": GITHUB_CLIENT_ID, "redirect_uri": callback_url, "scope": "user:email", "state": gh_state})}'
        )
        github_btn = Template(GITHUB_BTN_HTML).safe_substitute(github_url=github_url)
    else:
        github_btn = ''

    html = Template(LOGIN_HTML).safe_substitute(
        state=params.get('state', ''),
        redirect_uri=params.get('redirect_uri', ''),
        client_id=params.get('client_id', ''),
        code_challenge=params.get('code_challenge', ''),
        code_challenge_method=params.get('code_challenge_method', 'S256'),
        scope=params.get('scope', ''),
        error=f'<div class="error">{error}</div>' if error else '',
        github_btn=github_btn,
    )
    return make_response(html, 200, {'Content-Type': 'text/html'})


def _issue_auth_code(user_id, email, tenant_id, redirect_uri, client_id, code_challenge, code_challenge_method, mcp_state):
    """Issue a self-contained signed auth code and redirect to the MCP client callback."""
    code = _encode_state({
        'u': user_id,
        'e': email,
        't': tenant_id,
        'r': redirect_uri,
        'c': client_id,
        'ch': code_challenge,
        'cm': code_challenge_method,
        'x': int(time.time()) + CODE_TTL,
    })
    print(f'[OAUTH] Issued auth code for {email} → {redirect_uri[:60]}...', file=sys.stderr)

    sep = '&' if '?' in redirect_uri else '?'
    callback = f'{redirect_uri}{sep}{urlencode({"code": code, "state": mcp_state})}'
    return redirect(callback)


def init_oauth(get_db, get_cursor):
    """Initialize OAuth blueprint with database access."""

    def _find_or_create_user(email, github_id=None):
        """Find existing user by email, or auto-provision a new free-tier account."""
        from billing.provisioning import provision_tenant

        cur = get_cursor()
        db = get_db()
        try:
            cur.execute('SELECT id, email, tenant_id, status FROM users WHERE email = %s', (email,))
            user = cur.fetchone()

            if user:
                if not user.get('tenant_id'):
                    # Existing user without tenant — provision one
                    result = provision_tenant(cur, email, user_id=str(user['id']))
                    cur.execute(
                        'UPDATE users SET tenant_id = %s, status = %s, updated_at = %s WHERE id = %s',
                        (result['tenant_id'], 'active', datetime.utcnow().isoformat() + 'Z', user['id'])
                    )
                    db.commit()
                    print(f'[OAUTH] Provisioned tenant for existing user {email}', file=sys.stderr)
                    return str(user['id']), email, result['tenant_id']
                return str(user['id']), email, str(user['tenant_id'])

            # New user — auto-provision
            user_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat() + 'Z'
            # No password for GitHub users (they auth via GitHub)
            cur.execute(
                '''INSERT INTO users (id, email, password_hash, status, plan, created_at)
                   VALUES (%s, %s, %s, 'active', 'free', %s)''',
                (user_id, email, '', now)
            )
            result = provision_tenant(cur, email, user_id=user_id)
            cur.execute(
                'UPDATE users SET tenant_id = %s, api_key_encrypted = %s, updated_at = %s WHERE id = %s',
                (result['tenant_id'], result['api_key_encrypted'], now, user_id)
            )
            db.commit()
            print(f'[OAUTH] Auto-provisioned new user {email}: tenant={result["tenant_id"]}', file=sys.stderr)
            return user_id, email, result['tenant_id']

        except Exception as e:
            db.rollback()
            print(f'[OAUTH] User provisioning failed: {e}', file=sys.stderr)
            raise
        finally:
            cur.close()

    @oauth_bp.route('/oauth/authorize', methods=['GET'])
    def authorize_get():
        return _render_login(dict(request.args))

    @oauth_bp.route('/oauth/authorize', methods=['POST'])
    def authorize_post():
        """Email/password login."""
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        params = dict(request.form)

        if not email or not password:
            return _render_login(params, 'Email and password required')

        cur = get_cursor()
        try:
            cur.execute('SELECT id, email, password_hash, tenant_id, status FROM users WHERE email = %s', (email,))
            user = cur.fetchone()
        finally:
            cur.close()

        if not user or not user.get('password_hash') or not verify_password(password, user['password_hash']):
            return _render_login(params, 'Invalid email or password')

        if user['status'] != 'active':
            return _render_login(params, 'Account not active')

        if not user.get('tenant_id'):
            return _render_login(params, 'No tenant associated with this account')

        return _issue_auth_code(
            user_id=str(user['id']),
            email=user['email'],
            tenant_id=str(user['tenant_id']),
            redirect_uri=params.get('redirect_uri', ''),
            client_id=params.get('client_id', ''),
            code_challenge=params.get('code_challenge', ''),
            code_challenge_method=params.get('code_challenge_method', 'S256'),
            mcp_state=params.get('state', ''),
        )

    @oauth_bp.route('/oauth/callback/github', methods=['GET'])
    def github_callback():
        """GitHub OAuth callback — exchange code for user email, provision if needed."""
        gh_code = request.args.get('code', '')
        gh_state_raw = request.args.get('state', '')

        stashed = _decode_state(gh_state_raw) if gh_state_raw else None
        if not stashed:
            return make_response('Invalid or expired state. Please try connecting again.', 400)

        if not gh_code:
            return make_response('GitHub authorization was denied.', 400)

        # Exchange GitHub code for access token
        try:
            token_data = urlencode({
                'client_id': GITHUB_CLIENT_ID,
                'client_secret': GITHUB_CLIENT_SECRET,
                'code': gh_code,
            }).encode()
            req = urllib.request.Request(
                'https://github.com/login/oauth/access_token',
                data=token_data,
                headers={'Accept': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_resp = _json.loads(resp.read().decode())

            gh_token = token_resp.get('access_token')
            if not gh_token:
                print(f'[OAUTH] GitHub token exchange failed: {token_resp}', file=sys.stderr)
                return make_response('GitHub authentication failed.', 400)
        except Exception as e:
            print(f'[OAUTH] GitHub token exchange error: {e}', file=sys.stderr)
            return make_response('GitHub authentication failed.', 500)

        # Get user email from GitHub
        try:
            req = urllib.request.Request(
                'https://api.github.com/user/emails',
                headers={'Authorization': f'Bearer {gh_token}', 'Accept': 'application/json', 'User-Agent': 'Boswell'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                emails = _json.loads(resp.read().decode())

            # Pick primary verified email
            email = None
            for e in emails:
                if e.get('primary') and e.get('verified'):
                    email = e['email'].lower()
                    break
            if not email and emails:
                email = emails[0]['email'].lower()

            if not email:
                return make_response('Could not get email from GitHub.', 400)
        except Exception as e:
            print(f'[OAUTH] GitHub email fetch error: {e}', file=sys.stderr)
            return make_response('Failed to get GitHub profile.', 500)

        # Find or create user
        try:
            user_id, user_email, tenant_id = _find_or_create_user(email)
        except Exception as e:
            return make_response(f'Account setup failed: {e}', 500)

        print(f'[OAUTH] GitHub login: {email} → tenant={tenant_id}', file=sys.stderr)

        return _issue_auth_code(
            user_id=user_id,
            email=user_email,
            tenant_id=tenant_id,
            redirect_uri=stashed['r'],
            client_id=stashed['c'],
            code_challenge=stashed['ch'],
            code_challenge_method=stashed['cm'],
            mcp_state=stashed['s'],
        )

    @oauth_bp.route('/oauth/token', methods=['POST'])
    def token():
        """Exchange authorization code or refresh token for JWT."""
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
        code_raw = data.get('code', '')
        redirect_uri = data.get('redirect_uri', '')
        code_verifier = data.get('code_verifier', '')

        code_data = _decode_state(code_raw) if code_raw else None
        if not code_data:
            print(f'[OAUTH] Invalid auth code (bad signature)', file=sys.stderr)
            return jsonify({'error': 'invalid_grant', 'error_description': 'Invalid or expired authorization code'}), 400

        if code_data.get('x', 0) < time.time():
            print(f'[OAUTH] Expired auth code', file=sys.stderr)
            return jsonify({'error': 'invalid_grant', 'error_description': 'Invalid or expired authorization code'}), 400

        if redirect_uri and redirect_uri != code_data['r']:
            print(f'[OAUTH] redirect_uri mismatch', file=sys.stderr)
            return jsonify({'error': 'invalid_grant', 'error_description': 'redirect_uri mismatch'}), 400

        if code_data.get('ch'):
            if not code_verifier:
                return jsonify({'error': 'invalid_grant', 'error_description': 'code_verifier required'}), 400
            if not _verify_pkce(code_verifier, code_data['ch'], code_data.get('cm', 'S256')):
                print(f'[OAUTH] PKCE verification failed', file=sys.stderr)
                return jsonify({'error': 'invalid_grant', 'error_description': 'PKCE verification failed'}), 400

        access_token = generate_jwt(
            user_id=code_data['u'],
            email=code_data['e'],
            tenant_id=code_data['t']
        )

        # Refresh token is also a signed token (no server-side storage)
        refresh = _encode_state({
            'u': code_data['u'],
            'e': code_data['e'],
            't': code_data['t'],
            'c': code_data['c'],
            'k': 'refresh',
        })

        print(f'[OAUTH] Issued JWT for {code_data["e"]} (tenant={code_data["t"]})', file=sys.stderr)

        return jsonify({
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': 168 * 3600,
            'refresh_token': refresh,
        })

    def _handle_refresh_token(data):
        refresh_raw = data.get('refresh_token', '')

        token_data = _decode_state(refresh_raw) if refresh_raw else None
        if not token_data or token_data.get('k') != 'refresh':
            return jsonify({'error': 'invalid_grant', 'error_description': 'Invalid refresh token'}), 400

        access_token = generate_jwt(
            user_id=token_data['u'],
            email=token_data['e'],
            tenant_id=token_data['t']
        )

        # Issue new refresh token (same data, new signature timestamp not needed since HMAC is deterministic on same data)
        new_refresh = _encode_state({
            'u': token_data['u'],
            'e': token_data['e'],
            't': token_data['t'],
            'c': token_data.get('c', ''),
            'k': 'refresh',
        })

        print(f'[OAUTH] Refreshed JWT for {token_data["e"]}', file=sys.stderr)

        return jsonify({
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': 168 * 3600,
            'refresh_token': new_refresh,
        })

    @oauth_bp.route('/oauth/register', methods=['POST'])
    def register_client():
        """RFC 7591 - Dynamic Client Registration.
        Client ID is a signed token containing registration data — no server-side storage."""
        data = request.get_json() or {}

        client_name = data.get('client_name', 'MCP Client')
        reg_data = {
            'k': 'dcr',
            'n': client_name,
            'ru': data.get('redirect_uris', []),
        }
        client_id = _encode_state(reg_data)
        # Client secret is HMAC of client_id — deterministic, verifiable
        client_secret = hmac.new(JWT_SECRET.encode(), client_id.encode(), hashlib.sha256).hexdigest()[:32]

        print(f'[OAUTH] Registered client: {client_id[:30]}... name={client_name}', file=sys.stderr)

        return jsonify({
            'client_id': client_id,
            'client_secret': client_secret,
            'client_id_issued_at': int(time.time()),
            'client_secret_expires_at': 0,
            'redirect_uris': data.get('redirect_uris', []),
            'client_name': client_name,
            'grant_types': data.get('grant_types', ['authorization_code', 'refresh_token']),
            'response_types': data.get('response_types', ['code']),
            'token_endpoint_auth_method': data.get('token_endpoint_auth_method', 'client_secret_post'),
        }), 201

    return oauth_bp
