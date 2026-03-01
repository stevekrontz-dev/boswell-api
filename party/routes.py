"""
Party Beta Launch — Boswell Pro for Sunday Guests
Owner: CC1

GET  /party              — Landing page (QR code destination)
POST /party/provision    — Direct API key signup (no GitHub needed)
GET  /party/success      — Post-OAuth success page with API key
"""

import os
import re
import uuid
import time
import sys
from collections import defaultdict
from datetime import datetime
from string import Template

from flask import Blueprint, request, jsonify, make_response

from billing.provisioning import provision_tenant

party_bp = Blueprint('party', __name__)

# Rate limiting
_party_rate = defaultdict(list)
PARTY_RATE_LIMIT = 10
PARTY_RATE_WINDOW = 3600


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    window_start = now - PARTY_RATE_WINDOW
    _party_rate[ip] = [t for t in _party_rate[ip] if t > window_start]
    if len(_party_rate[ip]) >= PARTY_RATE_LIMIT:
        return True
    _party_rate[ip].append(now)
    return False


def _validate_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def _get_base_url():
    domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
    if domain:
        return f'https://{domain}'
    return 'http://localhost:8080'


# ============================================================
# Landing Page HTML
# ============================================================

PARTY_HTML = Template(r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Boswell — Memory for AI</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'DM Sans', system-ui, sans-serif;
    background: #0c0a09;
    color: #f5f5f4;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }
  .container {
    max-width: 420px;
    margin: 0 auto;
    padding: 3rem 1.5rem 4rem;
  }
  .logo-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  .logo-row img {
    width: 32px;
    height: 32px;
  }
  .logo {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 300;
    font-size: 1.5rem;
    color: #f5f5f4;
    margin-bottom: 0.25rem;
  }
  .tagline {
    font-size: 0.85rem;
    color: hsla(20,6%,90%,.5);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 2.5rem;
  }
  h1 {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 300;
    font-size: 2rem;
    line-height: 1.2;
    margin-bottom: 1rem;
    letter-spacing: -0.02em;
  }
  h1 em {
    font-style: italic;
    color: #f97316;
  }
  .subtitle {
    color: hsla(20,6%,90%,.6);
    font-size: 1rem;
    line-height: 1.6;
    margin-bottom: 2rem;
  }
  .card {
    background: linear-gradient(180deg, rgba(41,37,36,.5), rgba(28,25,23,.3));
    border: 1px solid hsla(60,5%,96%,.06);
    border-radius: 1rem;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }
  .gh-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    width: 100%;
    padding: 0.75rem 1rem;
    background: #f97316;
    color: #0c0a09;
    border: none;
    border-radius: 0.5rem;
    font-size: 1rem;
    font-weight: 500;
    cursor: pointer;
    text-decoration: none;
    transition: background 0.2s;
  }
  .gh-btn:hover { background: #fb923c; }
  .gh-btn svg { width: 22px; height: 22px; fill: #0c0a09; }
  .divider {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin: 1.5rem 0;
    color: hsla(20,6%,90%,.3);
    font-size: 0.8rem;
  }
  .divider::before, .divider::after {
    content: "";
    flex: 1;
    border-top: 1px solid hsla(60,5%,96%,.08);
  }
  label {
    display: block;
    font-size: 0.8rem;
    color: hsla(20,6%,90%,.5);
    margin-bottom: 0.3rem;
  }
  input[type=email] {
    width: 100%;
    padding: 0.65rem 0.75rem;
    background: rgba(12,10,9,.8);
    border: 1px solid hsla(60,5%,96%,.1);
    border-radius: 0.5rem;
    color: #f5f5f4;
    font-size: 1rem;
    font-family: inherit;
    margin-bottom: 1rem;
  }
  input[type=email]:focus {
    outline: none;
    border-color: rgba(249,115,22,.5);
  }
  input[type=email]::placeholder { color: hsla(20,6%,90%,.3); }
  .submit-btn {
    width: 100%;
    padding: 0.7rem 1rem;
    background: transparent;
    color: #f97316;
    border: 1px solid rgba(249,115,22,.4);
    border-radius: 0.5rem;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    font-family: inherit;
  }
  .submit-btn:hover {
    background: rgba(249,115,22,.1);
    border-color: #f97316;
  }
  .submit-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Success section (hidden by default) */
  #success-section { display: none; }
  #success-section.visible { display: block; }
  .success-title {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 300;
    font-size: 1.3rem;
    color: #4ade80;
    margin-bottom: 1rem;
  }
  .key-display {
    background: rgba(12,10,9,.8);
    border: 1px solid hsla(60,5%,96%,.1);
    border-radius: 0.5rem;
    padding: 0.75rem;
    font-family: ui-monospace, 'Cascadia Code', monospace;
    font-size: 0.85rem;
    color: #f97316;
    word-break: break-all;
    margin-bottom: 1rem;
  }
  .setup-label {
    font-size: 0.85rem;
    color: hsla(20,6%,90%,.6);
    margin-bottom: 0.5rem;
  }
  .setup-cmd {
    background: rgba(12,10,9,.8);
    border: 1px solid hsla(60,5%,96%,.1);
    border-radius: 0.5rem;
    padding: 0.75rem;
    font-family: ui-monospace, 'Cascadia Code', monospace;
    font-size: 0.75rem;
    color: #f5f5f4;
    line-height: 1.6;
    word-break: break-all;
    white-space: pre-wrap;
    margin-bottom: 0.75rem;
    position: relative;
  }
  .copy-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.75rem;
    background: rgba(249,115,22,.1);
    color: #f97316;
    border: 1px solid rgba(249,115,22,.3);
    border-radius: 0.4rem;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s;
    font-family: inherit;
  }
  .copy-btn:hover { background: rgba(249,115,22,.2); }

  .error-msg {
    background: rgba(239,68,68,.1);
    border: 1px solid rgba(239,68,68,.3);
    color: #f87171;
    font-size: 0.85rem;
    padding: 0.6rem 0.75rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
    display: none;
  }
  .error-msg.visible { display: block; }

  .closed-msg {
    text-align: center;
    color: hsla(20,6%,90%,.5);
    font-size: 1rem;
    padding: 4rem 1rem;
  }
  .closed-msg h2 {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 300;
    font-size: 1.5rem;
    color: #f5f5f4;
    margin-bottom: 0.75rem;
  }

  .invalid-msg {
    text-align: center;
    padding: 4rem 1rem;
  }
  .invalid-msg h2 {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 300;
    font-size: 1.5rem;
    color: #f87171;
    margin-bottom: 0.75rem;
  }
  .invalid-msg p { color: hsla(20,6%,90%,.5); }

  .features {
    margin-top: 2rem;
    padding-top: 1.5rem;
    border-top: 1px solid hsla(60,5%,96%,.06);
  }
  .feature {
    display: flex;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .feature-icon {
    flex-shrink: 0;
    width: 2rem;
    height: 2rem;
    background: rgba(249,115,22,.1);
    border-radius: 0.4rem;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
  }
  .feature-text h3 {
    font-size: 0.9rem;
    font-weight: 500;
    margin-bottom: 0.15rem;
  }
  .feature-text p {
    font-size: 0.8rem;
    color: hsla(20,6%,90%,.5);
    line-height: 1.4;
  }
</style>
</head><body>
<div class="container">
  <div class="logo-row">
    <img src="/boswell-logo-dark.svg" alt="Boswell">
    <div class="logo">Boswell</div>
  </div>
  <div class="tagline">Memory for AI</div>

  $body

</div>
</body></html>""")


PARTY_BODY_ACTIVE = Template(r"""
  <h1>Your AI forgets everything.<br><em>Boswell fixes that.</em></h1>
  <p class="subtitle">
    Persistent memory that follows your AI across every conversation.
    Decisions, context, preferences — remembered forever.
  </p>

  <div class="card">
    <a href="$github_url" class="gh-btn">
      <svg viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
      Continue with GitHub
    </a>

    <div class="divider">or get an API key directly</div>

    <div id="error-msg" class="error-msg"></div>

    <form id="provision-form" onsubmit="return handleProvision(event)">
      <label for="email">Email address</label>
      <input type="email" id="email" name="email" placeholder="you@example.com" required>
      <button type="submit" class="submit-btn" id="submit-btn">Get My API Key</button>
    </form>
  </div>

  <div id="success-section" class="card">
    <div class="success-title">You're in.</div>
    <p class="setup-label">Your API key:</p>
    <div class="key-display" id="api-key-display"></div>
    <p class="setup-label">Run this in your terminal to connect Claude:</p>
    <div class="setup-cmd" id="setup-cmd"></div>
    <button class="copy-btn" onclick="copySetup()">Copy command</button>
  </div>

  <div class="features">
    <div class="feature">
      <div class="feature-icon">&#x1f9e0;</div>
      <div class="feature-text">
        <h3>Persistent Memory</h3>
        <p>Decisions, preferences, and context survive across every conversation.</p>
      </div>
    </div>
    <div class="feature">
      <div class="feature-icon">&#x1f512;</div>
      <div class="feature-text">
        <h3>Tenant Isolated</h3>
        <p>Your memories are yours alone. Fully isolated data, encrypted at rest.</p>
      </div>
    </div>
    <div class="feature">
      <div class="feature-icon">&#x26a1;</div>
      <div class="feature-text">
        <h3>Works with Claude Code</h3>
        <p>One command to connect. Works instantly with Claude Desktop and Claude Code.</p>
      </div>
    </div>
  </div>

<script>
const INVITE_CODE = '$invite_code';
const BASE_URL = '$base_url';

async function handleProvision(e) {
  e.preventDefault();
  const btn = document.getElementById('submit-btn');
  const errEl = document.getElementById('error-msg');
  const email = document.getElementById('email').value.trim();

  btn.disabled = true;
  btn.textContent = 'Setting up...';
  errEl.classList.remove('visible');

  try {
    const resp = await fetch('/party/provision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, code: INVITE_CODE })
    });
    const data = await resp.json();

    if (!resp.ok) {
      errEl.textContent = data.error || 'Something went wrong.';
      errEl.classList.add('visible');
      btn.disabled = false;
      btn.textContent = 'Get My API Key';
      return false;
    }

    // Success
    document.getElementById('api-key-display').textContent = data.api_key;
    const cmd = 'claude mcp add boswell \\\n  --transport sse \\\n  --url ' + BASE_URL + '/v2/mcp \\\n  --header "X-API-Key: ' + data.api_key + '"';
    document.getElementById('setup-cmd').textContent = cmd;
    document.getElementById('success-section').classList.add('visible');
    document.getElementById('provision-form').style.display = 'none';

  } catch (err) {
    errEl.textContent = 'Network error. Please try again.';
    errEl.classList.add('visible');
    btn.disabled = false;
    btn.textContent = 'Get My API Key';
  }
  return false;
}

function copySetup() {
  const cmd = document.getElementById('setup-cmd').textContent;
  navigator.clipboard.writeText(cmd).then(() => {
    const btn = document.querySelector('.copy-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = 'Copy command'; }, 2000);
  });
}
</script>
""")

PARTY_BODY_CLOSED = """
  <div class="closed-msg">
    <h2>Boswell</h2>
    <p>Invitations are currently closed.</p>
    <p style="margin-top: 1rem;"><a href="https://askboswell.com" style="color: #f97316;">Learn more at askboswell.com</a></p>
  </div>
"""

PARTY_BODY_INVALID = """
  <div class="invalid-msg">
    <h2>Invalid Invite</h2>
    <p>This invite code isn't valid. Check the link you were given.</p>
  </div>
"""


# ============================================================
# Success page HTML (post-GitHub-OAuth)
# ============================================================

SUCCESS_HTML = Template(r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Welcome to Boswell</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'DM Sans', system-ui, sans-serif;
    background: #0c0a09;
    color: #f5f5f4;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }
  .container { max-width: 420px; margin: 0 auto; padding: 3rem 1.5rem 4rem; }
  .logo-row { display: flex; align-items: center; gap: 0.6rem; }
  .logo-row img { width: 32px; height: 32px; }
  .logo { font-family: 'Fraunces', Georgia, serif; font-weight: 300; font-size: 1.5rem; margin-bottom: 0.25rem; }
  .tagline { font-size: 0.85rem; color: hsla(20,6%,90%,.5); letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 2.5rem; }
  .card {
    background: linear-gradient(180deg, rgba(41,37,36,.5), rgba(28,25,23,.3));
    border: 1px solid hsla(60,5%,96%,.06);
    border-radius: 1rem;
    padding: 1.5rem;
  }
  .success-title { font-family: 'Fraunces', Georgia, serif; font-weight: 300; font-size: 1.3rem; color: #4ade80; margin-bottom: 1rem; }
  .setup-label { font-size: 0.85rem; color: hsla(20,6%,90%,.6); margin-bottom: 0.5rem; }
  .key-display {
    background: rgba(12,10,9,.8);
    border: 1px solid hsla(60,5%,96%,.1);
    border-radius: 0.5rem;
    padding: 0.75rem;
    font-family: ui-monospace, 'Cascadia Code', monospace;
    font-size: 0.85rem;
    color: #f97316;
    word-break: break-all;
    margin-bottom: 1rem;
  }
  .setup-cmd {
    background: rgba(12,10,9,.8);
    border: 1px solid hsla(60,5%,96%,.1);
    border-radius: 0.5rem;
    padding: 0.75rem;
    font-family: ui-monospace, 'Cascadia Code', monospace;
    font-size: 0.75rem;
    color: #f5f5f4;
    line-height: 1.6;
    word-break: break-all;
    white-space: pre-wrap;
    margin-bottom: 0.75rem;
  }
  .copy-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.75rem;
    background: rgba(249,115,22,.1);
    color: #f97316;
    border: 1px solid rgba(249,115,22,.3);
    border-radius: 0.4rem;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s;
    font-family: inherit;
  }
  .copy-btn:hover { background: rgba(249,115,22,.2); }
</style>
</head><body>
<div class="container">
  <div class="logo-row">
    <img src="/boswell-logo-dark.svg" alt="Boswell">
    <div class="logo">Boswell</div>
  </div>
  <div class="tagline">Memory for AI</div>
  <div class="card">
    <div class="success-title">Welcome to Boswell Pro.</div>
    <p class="setup-label">Your API key:</p>
    <div class="key-display">$api_key</div>
    <p class="setup-label">Run this in your terminal to connect Claude:</p>
    <div class="setup-cmd" id="setup-cmd">$setup_cmd</div>
    <button class="copy-btn" onclick="copySetup()">Copy command</button>
  </div>
</div>
<script>
function copySetup() {
  const cmd = document.getElementById('setup-cmd').textContent;
  navigator.clipboard.writeText(cmd).then(() => {
    const btn = document.querySelector('.copy-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = 'Copy command'; }, 2000);
  });
}
</script>
</body></html>""")


# ============================================================
# Blueprint init
# ============================================================

def init_party(get_db, get_cursor):
    """Initialize party blueprint with database access."""

    GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', '')
    PARTY_INVITE_CODE = os.environ.get('PARTY_INVITE_CODE', '')

    # ------------------------------------------------------------------
    # GET /party — Landing page
    # ------------------------------------------------------------------
    @party_bp.route('/party', methods=['GET'])
    def party_landing():
        code = request.args.get('code', '')

        # No invite code env var = invitations closed
        if not PARTY_INVITE_CODE:
            html = PARTY_HTML.safe_substitute(body=PARTY_BODY_CLOSED)
            return make_response(html, 200, {'Content-Type': 'text/html'})

        # No code param or wrong code
        if not code:
            html = PARTY_HTML.safe_substitute(body=PARTY_BODY_INVALID)
            return make_response(html, 403, {'Content-Type': 'text/html'})

        if code != PARTY_INVITE_CODE:
            html = PARTY_HTML.safe_substitute(body=PARTY_BODY_INVALID)
            return make_response(html, 403, {'Content-Type': 'text/html'})

        # Valid invite code — render the signup page
        base_url = _get_base_url()

        # Build GitHub OAuth URL with invite code threaded through
        if GITHUB_CLIENT_ID:
            from auth.oauth_server import _encode_state
            from urllib.parse import urlencode

            # State carries the invite code + redirect back to party success
            gh_state = _encode_state({
                'ic': code,
                'party': True,
            })
            callback_url = base_url + '/oauth/callback/github'
            github_url = (
                f'https://github.com/login/oauth/authorize?'
                f'{urlencode({"client_id": GITHUB_CLIENT_ID, "redirect_uri": callback_url, "scope": "user:email", "state": gh_state})}'
            )
        else:
            github_url = '#'

        body = PARTY_BODY_ACTIVE.safe_substitute(
            invite_code=code,
            base_url=base_url,
            github_url=github_url,
        )
        html = PARTY_HTML.safe_substitute(body=body)
        return make_response(html, 200, {'Content-Type': 'text/html'})

    # ------------------------------------------------------------------
    # POST /party/provision — Direct API key signup
    # ------------------------------------------------------------------
    @party_bp.route('/party/provision', methods=['POST'])
    def party_provision():
        # Rate limit
        client_ip = request.remote_addr or 'unknown'
        if _is_rate_limited(client_ip):
            return jsonify({'error': 'Rate limit exceeded. Try again later.'}), 429

        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        code = data.get('code', '')

        # Validate invite code
        if not PARTY_INVITE_CODE:
            return jsonify({'error': 'Invitations are currently closed.'}), 403

        if code != PARTY_INVITE_CODE:
            return jsonify({'error': 'Invalid invite code.'}), 403

        # Validate email
        if not email:
            return jsonify({'error': 'Email is required.'}), 400
        if not _validate_email(email):
            return jsonify({'error': 'Invalid email format.'}), 400

        db = get_db()
        cur = get_cursor()

        try:
            # Check if email already exists
            cur.execute('SELECT id FROM users WHERE email = %s', (email,))
            if cur.fetchone():
                cur.close()
                return jsonify({'error': 'This email is already registered. If you need your API key, contact Steve.'}), 409

            # Create user with Pro plan (no password — party guest)
            user_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat() + 'Z'

            cur.execute(
                '''INSERT INTO users (id, email, password_hash, status, plan, created_at)
                   VALUES (%s, %s, %s, 'active', 'pro', %s)''',
                (user_id, email, '', now)
            )

            # Provision tenant, branches, API key
            result = provision_tenant(cur, email, user_id=user_id)

            # Link tenant + encrypted key to user
            cur.execute(
                '''UPDATE users SET tenant_id = %s, api_key_encrypted = %s, updated_at = %s WHERE id = %s''',
                (result['tenant_id'], result['api_key_encrypted'], now, user_id)
            )

            db.commit()

            base_url = _get_base_url()
            setup_cmd = (
                f'claude mcp add boswell \\\n'
                f'  --transport sse \\\n'
                f'  --url {base_url}/v2/mcp \\\n'
                f'  --header "X-API-Key: {result["api_key"]}"'
            )

            print(f'[PARTY] Provisioned {email}: user={user_id} tenant={result["tenant_id"]} plan=pro', file=sys.stderr)

            return jsonify({
                'api_key': result['api_key'],
                'setup_command': setup_cmd,
                'tenant_id': result['tenant_id'],
                'branches': result['branches'],
                'message': 'Welcome to Boswell Pro! Save your API key — you won\'t see it again.'
            }), 201

        except Exception as e:
            db.rollback()
            print(f'[PARTY] Provision failed for {email}: {e}', file=sys.stderr)
            return jsonify({'error': f'Setup failed: {str(e)}'}), 500
        finally:
            cur.close()

    # ------------------------------------------------------------------
    # GET /party/success — Post-OAuth success page
    # ------------------------------------------------------------------
    @party_bp.route('/party/success', methods=['GET'])
    def party_success():
        from auth.oauth_server import _decode_state

        state_raw = request.args.get('s', '')
        if not state_raw:
            return make_response('Missing state parameter.', 400)

        state = _decode_state(state_raw)
        if not state:
            return make_response('Invalid or expired link.', 400)

        api_key = state.get('ak', '')
        if not api_key:
            return make_response('No API key in state.', 400)

        base_url = _get_base_url()
        setup_cmd = (
            f'claude mcp add boswell \\\n'
            f'  --transport sse \\\n'
            f'  --url {base_url}/v2/mcp \\\n'
            f'  --header "X-API-Key: {api_key}"'
        )

        html = SUCCESS_HTML.safe_substitute(
            api_key=api_key,
            setup_cmd=setup_cmd,
        )
        return make_response(html, 200, {'Content-Type': 'text/html'})

    return party_bp
