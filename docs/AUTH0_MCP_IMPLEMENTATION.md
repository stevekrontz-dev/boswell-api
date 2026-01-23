# Auth0 MCP Implementation Guide

**For:** CC1 (Claude Code)
**Date:** 2026-01-22
**Repo:** boswell-api-fix (NOT boswell-mcp)
**Deployed as:** delightful-imagination-production-f6a1.up.railway.app

---

## WHY

Claude.ai MCP Connectors require OAuth 2.1 discovery. Without it:
- "Failed to fetch" error on web/mobile
- Only stdio (Desktop/CC) works

## CREDENTIALS (from Boswell)

```
AUTH0_DOMAIN=dev-x68hvwv70qgq76e4.us.auth0.com
AUTH0_AUDIENCE=https://delightful-imagination-production-f6a1.up.railway.app
AUTH0_CLIENT_ID=ThCzpWMATtNFFzYtFvkVm7y4ONqGsScN
```

---

## PHASE 1: Discovery Endpoint (Zero Risk)

### 1.1 Add to app.py (after health check route)

```python
# ==================== OAUTH DISCOVERY ====================
AUTH0_DOMAIN = os.environ.get('AUTH0_DOMAIN', '')
AUTH0_AUDIENCE = os.environ.get('AUTH0_AUDIENCE', 'https://delightful-imagination-production-f6a1.up.railway.app')

@app.route('/.well-known/oauth-protected-resource', methods=['GET'])
def oauth_protected_resource():
    """RFC 9728 - Protected Resource Metadata for MCP Connectors."""
    if not AUTH0_DOMAIN:
        return jsonify({
            'error': 'auth_not_configured',
            'message': 'AUTH0_DOMAIN not set'
        }), 503
    
    return jsonify({
        'resource': AUTH0_AUDIENCE,
        'authorization_servers': [f'https://{AUTH0_DOMAIN}'],
        'scopes_supported': ['boswell:read', 'boswell:write', 'boswell:admin'],
        'bearer_methods_supported': ['header']
    })
```

### 1.2 Set Railway env vars

Steve must run (or CC via Railway CLI if linked):
```bash
railway variables set AUTH0_DOMAIN=dev-x68hvwv70qgq76e4.us.auth0.com
railway variables set AUTH0_AUDIENCE=https://delightful-imagination-production-f6a1.up.railway.app
railway variables set AUTH_ENABLED=false
railway variables set INTERNAL_SECRET=$(openssl rand -hex 32)
```

### 1.3 Deploy and verify

```bash
git add -A && git commit -m "feat: add RFC 9728 discovery endpoint"
git push  # Railway auto-deploys

# Test
curl https://delightful-imagination-production-f6a1.up.railway.app/.well-known/oauth-protected-resource
```

---

## PHASE 2: Auth0 JWT Validation

### 2.1 Add to requirements.txt

```
PyJWT>=2.8.0
```

### 2.2 Update auth/__init__.py - ADD (don't replace existing code)

```python
# ==================== AUTH0 OAUTH 2.1 ====================
AUTH0_DOMAIN = os.environ.get('AUTH0_DOMAIN', '')
AUTH0_AUDIENCE = os.environ.get('AUTH0_AUDIENCE', '')
AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'false').lower() == 'true'
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


def validate_auth0_token(token: str) -> dict:
    """Validate Auth0 JWT. Returns claims or None."""
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
        return {
            'user_id': payload['sub'],
            'tenant_id': payload.get('https://boswell.app/tenant_id', DEFAULT_TENANT),
            'scope': payload.get('scope', ''),
            'email': payload.get('email'),
            'source': 'auth0'
        }
    except Exception as e:
        import sys
        print(f'[AUTH] Auth0 token validation failed: {e}', file=sys.stderr)
        return None


def is_internal_request():
    """Check if request is from stdio (server.py → app.py)."""
    return INTERNAL_SECRET and request.headers.get('X-Boswell-Internal') == INTERNAL_SECRET


def check_mcp_auth(get_cursor_func):
    """
    MCP auth check for before_request.
    Returns None if OK, or (response, status) if denied.
    """
    # Auth disabled - allow all
    if not AUTH_ENABLED:
        g.mcp_auth = {'source': 'disabled', 'tenant_id': DEFAULT_TENANT}
        return None
    
    # Skip discovery/health
    if request.path in ['/', '/health', '/.well-known/oauth-protected-resource']:
        return None
    
    # Internal request (stdio) - CRITICAL: protects CC/Desktop
    if is_internal_request():
        g.mcp_auth = {'source': 'internal', 'tenant_id': DEFAULT_TENANT}
        return None
    
    # Check existing API key auth (X-API-Key header)
    api_key = request.headers.get('X-API-Key')
    if api_key and api_key.startswith('bos_'):
        # Existing API key validation (reuse existing logic)
        g.mcp_auth = {'source': 'api_key', 'tenant_id': DEFAULT_TENANT}
        return None
    
    # Check Bearer token (Auth0)
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        auth_info = validate_auth0_token(token)
        if auth_info:
            g.mcp_auth = auth_info
            return None
    
    # No valid auth
    return jsonify({
        'error': 'unauthorized',
        'error_description': 'Valid authentication required'
    }), 401
```

### 2.3 Wire into app.py before_request

Find existing `@app.before_request` or add:

```python
from auth import check_mcp_auth

@app.before_request
def authorize_mcp():
    result = check_mcp_auth(get_cursor)
    if result:
        return result
```

---

## PHASE 3: Protect stdio Pathway

### 3.1 Find server.py (stdio MCP handler)

This is the local server that CC/Desktop run. It calls the API.
Add `X-Boswell-Internal` header to ALL outbound requests:

```python
INTERNAL_SECRET = os.environ.get('INTERNAL_SECRET', '')

# In every httpx/requests call, add:
headers = {'X-Boswell-Internal': INTERNAL_SECRET} if INTERNAL_SECRET else {}
```

---

## PHASE 4: Enable Auth

```bash
railway variables set AUTH_ENABLED=true
```

### IMMEDIATE TEST

1. In CC: `boswell_brief` - MUST work
2. `curl https://delightful-imagination.../v2/branches` - MUST return 401
3. Discovery endpoint - MUST work without auth

### ROLLBACK

```bash
railway variables set AUTH_ENABLED=false
```

---

## SUCCESS CRITERIA

- [ ] Discovery endpoint returns Auth0 URL
- [ ] stdio works with AUTH_ENABLED=true
- [ ] Unauthenticated /v2/* returns 401
- [ ] Claude.ai Connector completes OAuth flow
- [ ] Phone gets Boswell back
