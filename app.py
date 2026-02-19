#!/usr/bin/env python3
"""
Boswell v2 API - Git-Style Memory Architecture
PostgreSQL version with multi-tenant support + Encryption (Phase 2)
"""

import psycopg2
import psycopg2.extras
try:
    from pgvector.psycopg2 import register_vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    register_vector = None
import hashlib
import json
import os
from datetime import datetime
from flask import Flask, request, jsonify, g, send_from_directory, has_request_context
from flask_cors import CORS
import time
import math
import threading
import numpy as np

# OpenAI for embeddings (v3)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
openai_client = None

def get_openai_client():
    """Lazy init OpenAI client."""
    global openai_client
    api_key = os.environ.get('OPENAI_API_KEY')
    if openai_client is None and api_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=api_key)
    return openai_client

def generate_embedding(text: str) -> list:
    """Generate embedding using OpenAI text-embedding-3-small."""
    client = get_openai_client()
    if not client:
        print(f"[EMBEDDING] No client - OPENAI_API_KEY set: {bool(OPENAI_API_KEY)}", file=sys.stderr)
        return None
    try:
        if len(text) > 30000:
            text = text[:30000]
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            dimensions=1536
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"[EMBEDDING] Error: {e}")
        return None

app = Flask(__name__)
CORS(app)

# Hippocampal memory staging (v4.0)
HIPPOCAMPAL_ENABLED = os.environ.get('HIPPOCAMPAL_ENABLED', 'true').lower() == 'true'

# Encryption support (Phase 2)
ENCRYPTION_ENABLED = os.environ.get('ENCRYPTION_ENABLED', 'false').lower() == 'true'
CREDENTIALS_PATH = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-key.json')

# Auth0 OAuth 2.1 Configuration
AUTH0_DOMAIN = os.environ.get('AUTH0_DOMAIN', '')
AUTH0_AUDIENCE = os.environ.get('AUTH0_AUDIENCE', 'https://delightful-imagination-production-f6a1.up.railway.app')

_encryption_service = None
_active_dek = None  # (key_id, wrapped_dek)

def get_encryption_service():
    """Get or initialize the encryption service."""
    global _encryption_service
    if _encryption_service is None and ENCRYPTION_ENABLED:
        try:
            from encryption_service import get_encryption_service as init_service
            _encryption_service = init_service(CREDENTIALS_PATH)
            print(f"[STARTUP] Encryption service initialized", file=sys.stderr)
        except Exception as e:
            print(f"[STARTUP] WARNING: Encryption service failed to initialize: {e}", file=sys.stderr)
    return _encryption_service

def get_active_dek():
    """Get the active DEK for the current tenant."""
    global _active_dek
    if _active_dek is None and ENCRYPTION_ENABLED:
        cur = get_cursor()
        cur.execute(
            "SELECT key_id, wrapped_key FROM data_encryption_keys WHERE tenant_id = %s AND status = 'active' LIMIT 1",
            (get_tenant_id(),)
        )
        row = cur.fetchone()
        cur.close()
        if row:
            _active_dek = (row['key_id'], bytes(row['wrapped_key']))
    return _active_dek

# Database URL from environment (Railway provides this)
DATABASE_URL = os.environ.get('DATABASE_URL')

# Startup logging for debugging
import sys
print(f"[STARTUP] DATABASE_URL set: {bool(DATABASE_URL)}", file=sys.stderr)
if DATABASE_URL:
    # Log sanitized URL (hide password)
    from urllib.parse import urlparse
    parsed = urlparse(DATABASE_URL)
    safe_url = f"{parsed.scheme}://{parsed.username}:***@{parsed.hostname}:{parsed.port}{parsed.path}"
    print(f"[STARTUP] Database host: {parsed.hostname}:{parsed.port}", file=sys.stderr)

# Default tenant for single-tenant mode (Steve Krontz)
DEFAULT_TENANT = '00000000-0000-0000-0000-000000000001'

_tenant_override = threading.local()

def get_tenant_id():
    """Get the active tenant ID. Checks (in order):
    1. Thread-local override stack (set by invoke_view/nightly_maintenance)
    2. g.mcp_auth['tenant_id'] (set by before_request auth)
    3. DEFAULT_TENANT fallback
    """
    stack = getattr(_tenant_override, 'stack', None)
    if stack:
        return stack[-1]
    auth = getattr(g, 'mcp_auth', None)
    if auth and auth.get('tenant_id'):
        return auth['tenant_id']
    return DEFAULT_TENANT

def push_tenant_override(tenant_id):
    """Push tenant onto thread-local stack. Always pair with pop."""
    if not hasattr(_tenant_override, 'stack'):
        _tenant_override.stack = []
    _tenant_override.stack.append(tenant_id)

def pop_tenant_override():
    """Pop tenant from thread-local stack. Safe if stack is empty."""
    stack = getattr(_tenant_override, 'stack', None)
    if stack:
        stack.pop()

# Project to branch mapping for auto-routing
PROJECT_BRANCH_MAP = {
    'tint-atlanta': 'tint-atlanta',
    'tint-empire': 'tint-empire',
    'iris': 'iris',
    'family': 'family',
    'command-center': 'command-center',
    'boswell': 'boswell',
    'default': 'command-center'
}

def get_db():
    """Get database connection for current request context."""
    if 'db' not in g:
        if not DATABASE_URL:
            raise Exception("DATABASE_URL environment variable not set")
        # Add connection timeout to prevent hanging
        g.db = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        g.db.autocommit = False
        # Register pgvector for embedding queries (if available)
        if PGVECTOR_AVAILABLE and register_vector:
            try:
                register_vector(g.db)
            except Exception:
                pass  # pgvector extension not in DB, skip
        # Set tenant context for RLS
        cur = g.db.cursor()
        cur.execute("SELECT set_config('app.current_tenant', %s, true)", (get_tenant_id(),))
        cur.close()
    return g.db

def get_cursor():
    """Get a cursor with dict-like row access."""
    db = get_db()
    return db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

@app.teardown_appcontext
def close_db(exception):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Phase 3: Audit Logging
AUDIT_ENABLED = os.environ.get('AUDIT_ENABLED', 'true').lower() == 'true'

@app.before_request
def before_request():
    """Start timing for audit logging + MCP auth check + co-access tracking."""
    g.audit_start = time.time()
    g.accessed_blobs = set()  # Auto-trail: track blobs touched in this request

    # MCP Auth check (OAuth 2.1 / internal / API key)
    from auth import check_mcp_auth
    result = check_mcp_auth(get_cursor, get_db)
    if result:
        return result

def _record_co_access_trails():
    """Auto-trail: create/strengthen trails between blobs co-accessed in this request."""
    blobs = getattr(g, 'accessed_blobs', set())
    if len(blobs) < 2:
        return

    # Cap at 10 blobs to avoid O(n^2) explosion
    blob_list = list(blobs)[:10]
    try:
        db = get_db()
        cur = get_cursor()
        for i in range(len(blob_list)):
            for j in range(i + 1, len(blob_list)):
                cur.execute('''
                    INSERT INTO trails (tenant_id, source_blob, target_blob,
                                        traversal_count, last_traversed, strength)
                    VALUES (%s, %s, %s, 1, NOW(), 1.0)
                    ON CONFLICT (tenant_id, source_blob, target_blob) DO UPDATE
                    SET traversal_count = trails.traversal_count + 1,
                        last_traversed = NOW(),
                        strength = LEAST(trails.strength * 1.1, 10.0)
                ''', (get_tenant_id(), blob_list[i], blob_list[j]))
        db.commit()
        cur.close()
    except Exception as e:
        print(f"[AUTO-TRAIL] Error recording co-access trails: {e}", file=sys.stderr)

@app.after_request
def after_request(response):
    """Log request to audit trail + auto-trail co-accessed blobs."""
    # Auto-trail: record co-access trails for successful non-health requests
    if (response.status_code >= 200 and response.status_code < 300
            and request.path not in ('/', '/health', '/favicon.ico', '/v2/', '/v2/health', '/v2/health/daemon')
            and not request.path.startswith('/v2/trails/')):
        try:
            _record_co_access_trails()
        except Exception as e:
            print(f"[AUTO-TRAIL] after_request error: {e}", file=sys.stderr)

    if not AUDIT_ENABLED:
        return response
    # Skip health checks and static
    if request.path in ('/', '/health', '/favicon.ico', '/v2/', '/v2/health', '/v2/health/daemon'):
        return response
    try:
        from audit_service import log_audit, parse_request_action
        duration_ms = int((time.time() - getattr(g, 'audit_start', time.time())) * 1000)
        action, resource_type, resource_id = parse_request_action(request)

        cur = get_cursor()
        log_audit(
            cursor=cur,
            tenant_id=get_tenant_id(),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            response_status=response.status_code,
            duration_ms=duration_ms,
            extra_metadata={'response_size_bytes': response.content_length or 0}
        )
        cur.connection.commit()
        cur.close()
    except Exception as e:
        print(f"[AUDIT] Error: {e}", file=sys.stderr)
    return response

def compute_hash(content):
    """Compute SHA-256 hash for content-addressable storage."""
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()

def get_current_head(branch='command-center'):
    """Get the current HEAD commit for a branch."""
    cur = get_cursor()
    cur.execute(
        'SELECT head_commit FROM branches WHERE name = %s AND tenant_id = %s',
        (branch, get_tenant_id())
    )
    row = cur.fetchone()
    cur.close()
    return row['head_commit'] if row else None

def get_branch_for_project(project):
    """Map project name to cognitive branch."""
    if project in PROJECT_BRANCH_MAP:
        return PROJECT_BRANCH_MAP[project]
    for key in PROJECT_BRANCH_MAP:
        if key in project.lower():
            return PROJECT_BRANCH_MAP[key]
    return PROJECT_BRANCH_MAP['default']

# ==================== API ENDPOINTS ====================

@app.route('/api/health', methods=['GET'])
@app.route('/v2/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        cur = get_cursor()
        cur.execute('SELECT COUNT(*) as count FROM branches WHERE tenant_id = %s', (get_tenant_id(),))
        branch_count = cur.fetchone()['count']
        cur.execute('SELECT COUNT(*) as count FROM commits WHERE tenant_id = %s', (get_tenant_id(),))
        commit_count = cur.fetchone()['count']
        cur.close()
        # Check encryption status
        encryption_status = 'disabled'
        if ENCRYPTION_ENABLED:
            encryption_status = 'enabled'
            if get_active_dek():
                encryption_status = 'active'

        # Debug: Check runtime env var
        runtime_key = os.environ.get('OPENAI_API_KEY', '')
        openai_keys = [k for k in os.environ.keys() if 'OPENAI' in k.upper()]

        return jsonify({
            'status': 'ok',
            'service': 'boswell-v2',
            'version': '3.1.0-connectome',
            'platform': 'railway',
            'database': 'postgres',
            'encryption': encryption_status,
            'embeddings': 'enabled' if runtime_key else 'disabled',
            'openai_key_set': bool(runtime_key),
            'openai_key_prefix': runtime_key[:10] + '...' if runtime_key else None,
            'openai_env_vars': openai_keys,
            'audit': 'enabled' if AUDIT_ENABLED else 'disabled',
            'branches': branch_count,
            'commits': commit_count,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


# ==================== HEALTH DAEMON ====================

import psutil

def check_postgres():
    """Check PostgreSQL connectivity and measure latency."""
    start = time.time()
    try:
        cur = get_cursor()
        cur.execute('SELECT 1')
        cur.fetchone()
        cur.close()
        latency_ms = (time.time() - start) * 1000

        if latency_ms < 500:
            status = 'pass'
            message = 'Connection OK'
        elif latency_ms < 2000:
            status = 'degraded'
            message = f'Slow connection ({latency_ms:.0f}ms)'
        else:
            status = 'fail'
            message = f'Very slow connection ({latency_ms:.0f}ms)'

        return {
            'check': 'postgres',
            'status': status,
            'latency_ms': round(latency_ms, 1),
            'message': message
        }
    except Exception as e:
        return {
            'check': 'postgres',
            'status': 'fail',
            'latency_ms': round((time.time() - start) * 1000, 1),
            'message': f'Connection failed: {str(e)}'
        }


def check_mcp():
    """Check MCP endpoint health via internal call."""
    start = time.time()
    try:
        # Internal call to mcp_health view function (no HTTP overhead)
        with app.test_request_context():
            response = mcp_health()
            latency_ms = (time.time() - start) * 1000

            if hasattr(response, 'json'):
                data = response.json
            else:
                data = response.get_json() if hasattr(response, 'get_json') else {}

            if data.get('status') == 'ok':
                return {
                    'check': 'mcp',
                    'status': 'pass',
                    'latency_ms': round(latency_ms, 1),
                    'message': 'MCP endpoint OK'
                }
            else:
                return {
                    'check': 'mcp',
                    'status': 'fail',
                    'latency_ms': round(latency_ms, 1),
                    'message': f'MCP returned status: {data.get("status", "unknown")}'
                }
    except Exception as e:
        return {
            'check': 'mcp',
            'status': 'fail',
            'latency_ms': round((time.time() - start) * 1000, 1),
            'message': f'MCP check failed: {str(e)}'
        }


def check_system_resources():
    """Check system resources using psutil."""
    start = time.time()
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu = psutil.cpu_percent(interval=0.1)

        latency_ms = (time.time() - start) * 1000

        return {
            'check': 'system',
            'status': 'pass',
            'latency_ms': round(latency_ms, 1),
            'details': {
                'memory_percent': round(memory.percent, 1),
                'memory_available_mb': round(memory.available / (1024 * 1024), 1),
                'disk_percent': round(disk.percent, 1),
                'disk_free_gb': round(disk.free / (1024 * 1024 * 1024), 2),
                'cpu_percent': round(cpu, 1)
            }
        }
    except Exception as e:
        return {
            'check': 'system',
            'status': 'fail',
            'latency_ms': round((time.time() - start) * 1000, 1),
            'message': f'System check failed: {str(e)}'
        }


def check_openai():
    """Check if OpenAI API key is configured (no API call)."""
    start = time.time()
    api_key = os.environ.get('OPENAI_API_KEY')
    latency_ms = (time.time() - start) * 1000

    if api_key:
        return {
            'check': 'openai',
            'status': 'pass',
            'latency_ms': round(latency_ms, 1),
            'message': 'API key configured'
        }
    else:
        return {
            'check': 'openai',
            'status': 'fail',
            'latency_ms': round(latency_ms, 1),
            'message': 'OPENAI_API_KEY not set'
        }


def get_current_alerts_internal():
    """Get current alerts via internal call to admin_alerts."""
    try:
        with app.test_request_context():
            response = admin_alerts()
            if hasattr(response, 'json'):
                return response.json
            elif isinstance(response, tuple):
                return response[0].get_json() if hasattr(response[0], 'get_json') else {}
            else:
                return response.get_json() if hasattr(response, 'get_json') else {}
    except Exception as e:
        return {'alerts': [], 'count': 0, 'critical_count': 0, 'warning_count': 0, 'error': str(e)}


def commit_health_snapshot(snapshot):
    """Commit health snapshot to health-status branch (best-effort).
    
    DISABLED: This was committing every 5 minutes (288/day), each generating 
    an embedding. Bleeding Railway costs. See conversation 2026-01-25.
    TODO: Reimplement with change-detection (only commit on state transitions).
    """
    return {'committed': False, 'reason': 'disabled - cost optimization'}
    
    # Original implementation below (disabled)
    try:
        db = get_db()
        cur = get_cursor()
        now = datetime.utcnow().isoformat() + 'Z'
        branch = 'health-status'

        content_str = json.dumps(snapshot)
        blob_hash = compute_hash(content_str)

        # Insert blob
        cur.execute(
            '''INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (blob_hash) DO NOTHING''',
            (blob_hash, get_tenant_id(), content_str, 'health_snapshot', now, len(content_str))
        )

        # Create tree entry
        tree_hash = compute_hash(f"{branch}:{blob_hash}:{now}")
        status = snapshot.get('overall_status', 'unknown')
        passed = snapshot.get('summary', {}).get('checks_passed', 0)
        total = snapshot.get('summary', {}).get('checks_total', 0)
        message = f"Health snapshot: {status} - {passed}/{total} checks passed"

        cur.execute(
            '''INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
               VALUES (%s, %s, %s, %s, %s)''',
            (get_tenant_id(), tree_hash, message[:100], blob_hash, 'health_snapshot')
        )

        # Check if branch exists
        cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', (branch, get_tenant_id()))
        branch_row = cur.fetchone()
        if branch_row:
            parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
        else:
            # Auto-create branch
            cur.execute(
                '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
                   VALUES (%s, %s, %s, %s)''',
                (get_tenant_id(), branch, 'GENESIS', now)
            )
            parent_hash = None

        # Create commit
        commit_data = f"{tree_hash}:{parent_hash}:{message}:{now}"
        commit_hash = compute_hash(commit_data)

        cur.execute(
            '''INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (commit_hash, get_tenant_id(), tree_hash, parent_hash, 'health-daemon', message, now)
        )

        # Update branch head
        cur.execute(
            'UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s',
            (commit_hash, branch, get_tenant_id())
        )

        db.commit()
        cur.close()

        return {'committed': True, 'blob_hash': blob_hash, 'commit_hash': commit_hash}
    except Exception as e:
        print(f"[HEALTH] Failed to commit snapshot: {e}", file=sys.stderr)
        return {'committed': False, 'error': str(e)}


@app.route('/v2/health/daemon', methods=['GET'])
def health_daemon():
    """Comprehensive health check endpoint for monitoring daemon."""
    timestamp = datetime.utcnow().isoformat() + 'Z'

    # Run all health checks (isolated, continue on failure)
    checks = []
    for check_fn in [check_postgres, check_mcp, check_system_resources, check_openai]:
        try:
            checks.append(check_fn())
        except Exception as e:
            checks.append({
                'check': check_fn.__name__.replace('check_', ''),
                'status': 'fail',
                'latency_ms': 0,
                'message': f'Check threw exception: {str(e)}'
            })

    # Fetch alerts internally
    alerts_data = get_current_alerts_internal()

    # Compute overall status
    checks_failed = sum(1 for c in checks if c['status'] == 'fail')
    checks_degraded = sum(1 for c in checks if c['status'] == 'degraded')
    critical_alerts = alerts_data.get('critical_count', 0)
    warning_alerts = alerts_data.get('warning_count', 0)

    if checks_failed > 0 or critical_alerts > 0:
        overall_status = 'unhealthy'
    elif checks_degraded > 0 or warning_alerts > 0:
        overall_status = 'degraded'
    else:
        overall_status = 'healthy'

    # Build summary
    summary = {
        'checks_total': len(checks),
        'checks_passed': sum(1 for c in checks if c['status'] == 'pass'),
        'checks_degraded': checks_degraded,
        'checks_failed': checks_failed,
        'alerts_critical': critical_alerts,
        'alerts_warning': warning_alerts
    }

    # Build snapshot for commit
    snapshot = {
        'type': 'health_snapshot',
        'timestamp': timestamp,
        'overall_status': overall_status,
        'checks': checks,
        'alerts': alerts_data.get('alerts', []),
        'summary': summary
    }

    # Commit to health-status branch (best-effort)
    commit_result = commit_health_snapshot(snapshot)

    # Build response
    response = {
        'status': overall_status,
        'checks': checks,
        'alerts': {
            'items': alerts_data.get('alerts', []),
            'count': alerts_data.get('count', 0),
            'critical_count': critical_alerts,
            'warning_count': warning_alerts
        },
        'summary': summary,
        'commit': commit_result,
        'timestamp': timestamp
    }

    # Return appropriate HTTP status
    if overall_status == 'unhealthy':
        return jsonify(response), 503
    else:
        return jsonify(response), 200


# ==================== OAUTH DISCOVERY ====================

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

@app.route('/v2/head', methods=['GET'])
def get_head():
    """Get current HEAD state for a branch."""
    branch = request.args.get('branch', 'command-center')
    cur = get_cursor()

    cur.execute('SELECT * FROM branches WHERE name = %s AND tenant_id = %s', (branch, get_tenant_id()))
    branch_info = cur.fetchone()

    if not branch_info:
        cur.close()
        return jsonify({'error': f'Branch {branch} not found'}), 404

    head_commit = branch_info['head_commit']
    commit_info = None
    if head_commit and head_commit != 'GENESIS':
        cur.execute('SELECT * FROM commits WHERE commit_hash = %s AND tenant_id = %s', (head_commit, get_tenant_id()))
        commit_row = cur.fetchone()
        if commit_row:
            commit_info = dict(commit_row)

    cur.close()
    return jsonify({
        'branch': branch,
        'head_commit': head_commit,
        'commit': commit_info,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

@app.route('/v2/checkout', methods=['POST'])
def checkout_branch():
    """Switch to a different branch."""
    data = request.get_json() or {}
    branch = data.get('branch')

    if not branch:
        return jsonify({'error': 'Branch name required'}), 400

    cur = get_cursor()
    cur.execute('SELECT * FROM branches WHERE name = %s AND tenant_id = %s', (branch, get_tenant_id()))
    branch_info = cur.fetchone()
    cur.close()

    if not branch_info:
        return jsonify({'error': f'Branch {branch} not found'}), 404

    return jsonify({
        'status': 'checked_out',
        'branch': branch,
        'head_commit': branch_info['head_commit']
    })

@app.route('/v2/branches', methods=['GET'])
def list_branches():
    """List all cognitive branches for the authenticated user."""
    tenant_id = get_tenant_id()

    try:
        cur = get_cursor()
        # Get branches
        cur.execute('SELECT * FROM branches WHERE tenant_id = %s ORDER BY name', (tenant_id,))
        branches = []
        for row in cur.fetchall():
            branch = dict(row)
            branch_name = branch.get('name')
            # Convert UUID and datetime to strings for JSON serialization
            if branch.get('tenant_id'):
                branch['tenant_id'] = str(branch['tenant_id'])
            if branch.get('created_at'):
                branch['created_at'] = str(branch['created_at'])

            # Count commits by walking the chain from head_commit
            commit_count = 0
            head = branch.get('head_commit')
            if head and head != 'GENESIS':
                # Walk commit chain to count
                cur.execute('''
                    WITH RECURSIVE commit_chain AS (
                        SELECT commit_hash, parent_hash, 1 as depth
                        FROM commits WHERE commit_hash = %s AND tenant_id = %s
                        UNION ALL
                        SELECT c.commit_hash, c.parent_hash, cc.depth + 1
                        FROM commits c
                        JOIN commit_chain cc ON c.commit_hash = cc.parent_hash
                        WHERE c.tenant_id = %s AND cc.depth < 10000
                    )
                    SELECT COUNT(*) as cnt, MAX(depth) as max_depth FROM commit_chain
                ''', (head, tenant_id, tenant_id))
                count_row = cur.fetchone()
                commit_count = count_row['cnt'] if count_row else 0

            branch['commits'] = commit_count
            branch['last_activity'] = str(branch.get('updated_at') or branch.get('created_at') or '')
            branches.append(branch)
        cur.close()
        return jsonify({'branches': branches, 'count': len(branches)})
    except Exception as e:
        return jsonify({'error': str(e), 'branches': [], 'count': 0}), 500

@app.route('/v2/branch', methods=['POST'])
def create_branch():
    """Create a new cognitive branch."""
    data = request.get_json() or {}
    name = data.get('name')
    from_branch = data.get('from', 'command-center')

    if not name:
        return jsonify({'error': 'Branch name required'}), 400

    tenant_id = get_tenant_id()

    # W2P4: Check branch limit before creating
    from billing.enforce import enforce_branch_limit
    limit_cur = get_cursor()
    limit_error = enforce_branch_limit(limit_cur, tenant_id)
    limit_cur.close()
    if limit_error:
        return limit_error

    db = get_db()
    cur = get_cursor()

    cur.execute('SELECT name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', (name, tenant_id))
    existing = cur.fetchone()
    if existing:
        cur.close()
        existing_name = existing['name']
        if existing_name == name:
            return jsonify({'error': f'Branch {name} already exists'}), 409
        else:
            return jsonify({'error': f'Branch name conflicts with existing branch \'{existing_name}\' (case-insensitive match)'}), 409

    cur.execute('SELECT head_commit FROM branches WHERE name = %s AND tenant_id = %s', (from_branch, tenant_id))
    source = cur.fetchone()
    head_commit = source['head_commit'] if source else 'GENESIS'

    now = datetime.utcnow().isoformat() + 'Z'
    cur.execute(
        '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
           VALUES (%s, %s, %s, %s)''',
        (tenant_id, name, head_commit, now)
    )
    db.commit()
    cur.close()

    return jsonify({
        'status': 'created',
        'branch': name,
        'from': from_branch,
        'head_commit': head_commit
    }), 201

@app.route('/v2/branch/<name>', methods=['DELETE'])
def delete_branch(name):
    """Delete a cognitive branch."""
    if not name:
        return jsonify({'error': 'Branch name required'}), 400

    # Prevent deleting core branches
    protected_branches = ['main', 'command-center']
    if name in protected_branches:
        return jsonify({'error': f'Cannot delete protected branch: {name}'}), 403

    tenant_id = get_tenant_id()

    db = get_db()
    cur = get_cursor()

    # Check branch exists and belongs to tenant
    cur.execute('SELECT name FROM branches WHERE name = %s AND tenant_id = %s', (name, tenant_id))
    if not cur.fetchone():
        cur.close()
        return jsonify({'error': f'Branch {name} not found'}), 404

    # Delete the branch
    cur.execute('DELETE FROM branches WHERE name = %s AND tenant_id = %s', (name, tenant_id))
    db.commit()
    cur.close()

    return jsonify({
        'status': 'deleted',
        'branch': name
    }), 200

@app.route('/v2/commit', methods=['POST'])
def create_commit():
    """Commit a memory to the repository."""
    data = request.get_json() or {}
    content = data.get('content')
    message = data.get('message', 'Memory commit')
    branch = data.get('branch', 'command-center')
    author = data.get('author', 'claude')
    memory_type = data.get('type', 'memory')
    tags = data.get('tags', [])

    if not content:
        return jsonify({'error': 'Content required'}), 400

    # Validate content_type='plan' requirements
    if memory_type == 'plan':
        if not isinstance(content, dict):
            return jsonify({'error': 'Plan content must be a JSON object'}), 400
        if not content.get('title') or not isinstance(content.get('title'), str):
            return jsonify({'error': 'Plan content requires a "title" string field'}), 400
        valid_plan_statuses = ['active', 'completed', 'paused', 'abandoned']
        plan_status = content.get('status')
        if not plan_status or plan_status not in valid_plan_statuses:
            return jsonify({'error': f'Plan content requires "status" field, one of: {valid_plan_statuses}'}), 400

    # Phase 4: Check routing suggestion (warn but don't block)
    force_branch = data.get('force_branch', False)
    routing_warning = None
    try:
        content_str_check = json.dumps(content) if isinstance(content, dict) else str(content)
        embedding_check = generate_embedding(content_str_check)
        if embedding_check:
            check_cur = get_cursor()
            check_cur.execute("""
                SELECT branch_name, centroid, commit_count
                FROM branch_fingerprints
                WHERE tenant_id = %s AND centroid IS NOT NULL
            """, (get_tenant_id(),))
            scores = []
            for row in check_cur.fetchall():
                if row['centroid'] is not None:
                    sim = cosine_similarity(embedding_check, row['centroid'])
                    scores.append({'branch': row['branch_name'], 'similarity': sim})
            check_cur.close()
            if scores:
                scores.sort(key=lambda x: x['similarity'], reverse=True)
                best = scores[0]
                if best['branch'].lower() != branch.lower() and best['similarity'] > 0.4:
                    routing_warning = {
                        'suggested_branch': best['branch'],
                        'requested_branch': branch,
                        'confidence': round(best['similarity'], 4),
                        'message': f"Content may belong on '{best['branch']}' (confidence: {best['similarity']:.1%})"
                    }
    except Exception as e:
        print(f"[ROUTING CHECK] Non-fatal error: {e}", file=sys.stderr)

    # W2P4: Check commit limit before creating
    from billing.enforce import enforce_commit_limit
    tenant_id = request.headers.get('X-Tenant-ID', get_tenant_id())
    limit_cur = get_cursor()
    limit_error = enforce_commit_limit(limit_cur, tenant_id)
    limit_cur.close()
    if limit_error:
        return limit_error

    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'

    try:
        content_str = json.dumps(content) if isinstance(content, dict) else str(content)
        blob_hash = compute_hash(content_str)

        # Insert blob with encryption if enabled
        encryption_service = get_encryption_service()
        dek_info = get_active_dek()

        if ENCRYPTION_ENABLED and encryption_service and dek_info:
            # Encrypt the content
            key_id, wrapped_dek = dek_info
            plaintext_dek = encryption_service.unwrap_dek(key_id, wrapped_dek)
            ciphertext, nonce = encryption_service.encrypt(content_str, plaintext_dek)

            cur.execute(
                '''INSERT INTO blobs (blob_hash, tenant_id, content, content_encrypted, nonce, encryption_key_id, content_type, created_at, byte_size)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (blob_hash) DO NOTHING''',
                (blob_hash, get_tenant_id(), content_str, psycopg2.Binary(ciphertext), psycopg2.Binary(nonce), key_id, memory_type, now, len(content_str))
            )
        else:
            # Fallback: store unencrypted
            cur.execute(
                '''INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (blob_hash) DO NOTHING''',
                (blob_hash, get_tenant_id(), content_str, memory_type, now, len(content_str))
            )

        # Generate and store embedding for semantic search
        embedding = generate_embedding(content_str)
        if embedding:
            try:
                cur.execute(
                    '''UPDATE blobs SET embedding = %s WHERE blob_hash = %s AND tenant_id = %s''',
                    (embedding, blob_hash, get_tenant_id())
                )
            except Exception as e:
                print(f"[EMBEDDING] Failed to store embedding: {e}", file=sys.stderr)

        # Phase 4: Check routing against branch fingerprints
        routing_suggestion = None
        force_branch = data.get('force_branch', False)
        if embedding and not force_branch:
            try:
                fp_cur = get_cursor()
                fp_cur.execute("""
                    SELECT branch_name, centroid, commit_count
                    FROM branch_fingerprints
                    WHERE tenant_id = %s AND centroid IS NOT NULL
                """, (get_tenant_id(),))
                
                scores = []
                for row in fp_cur.fetchall():
                    if row['centroid'] is not None:
                        similarity = cosine_similarity(embedding, row['centroid'])
                        scores.append({
                            'branch': row['branch_name'],
                            'similarity': round(similarity, 4)
                        })
                fp_cur.close()
                
                if scores:
                    scores.sort(key=lambda x: x['similarity'], reverse=True)
                    best_match = scores[0]
                    if best_match['branch'].lower() != branch.lower() and best_match['similarity'] > 0.15:
                        routing_suggestion = {
                            'suggested_branch': best_match['branch'],
                            'confidence': best_match['similarity'],
                            'requested_branch': branch,
                            'message': f"Content looks like it belongs on '{best_match['branch']}' (confidence: {best_match['similarity']:.0%})"
                        }
            except Exception as e:
                print(f"[ROUTING] Failed to check routing: {e}", file=sys.stderr)

        tree_hash = compute_hash(f"{branch}:{blob_hash}:{now}")
        cur.execute(
            '''INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
               VALUES (%s, %s, %s, %s, %s)''',
            (get_tenant_id(), tree_hash, message[:100], blob_hash, memory_type)
        )

        cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', (branch, get_tenant_id()))
        branch_row = cur.fetchone()
        if branch_row:
            branch = branch_row['name']  # Use canonical casing
            parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
        else:
            # Auto-create branch on first commit
            cur.execute(
                '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
                   VALUES (%s, %s, %s, %s)''',
                (get_tenant_id(), branch, 'GENESIS', now)
            )
            parent_hash = None

        commit_data = f"{tree_hash}:{parent_hash}:{message}:{now}"
        commit_hash = compute_hash(commit_data)

        cur.execute(
            '''INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (commit_hash, get_tenant_id(), tree_hash, parent_hash, author, message, now)
        )

        cur.execute(
            'UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s',
            (commit_hash, branch, get_tenant_id())
        )

        for tag in tags:
            tag_str = tag if isinstance(tag, str) else str(tag)
            try:
                cur.execute(
                    '''INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
                       VALUES (%s, %s, %s, %s)''',
                    (get_tenant_id(), blob_hash, tag_str, now)
                )
            except Exception:
                # Tag already exists, ignore duplicate
                pass

        db.commit()

        # Auto-trail: track newly committed blob
        g.accessed_blobs.add(blob_hash)

        cur.close()

        response = {
            'status': 'committed',
            'commit_hash': commit_hash,
            'blob_hash': blob_hash,
            'tree_hash': tree_hash,
            'branch': branch,
            'message': message
        }
        if routing_suggestion:
            response['routing_suggestion'] = routing_suggestion
        return jsonify(response), 201

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': f'Commit failed: {str(e)}'}), 500


@app.route('/v2/commit/cherry-pick', methods=['POST'])
def cherry_pick_commit():
    """Copy a commit's content to a new commit on a different branch.
    
    Does NOT delete the original - use deprecate endpoint separately.
    """
    data = request.get_json() or {}
    source_hash = data.get('source_hash')
    target_branch = data.get('target_branch')
    
    if not source_hash:
        return jsonify({'error': 'source_hash required'}), 400
    if not target_branch:
        return jsonify({'error': 'target_branch required'}), 400
    
    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'
    
    try:
        # 1. Get the source commit
        cur.execute(
            'SELECT * FROM commits WHERE commit_hash = %s AND tenant_id = %s',
            (source_hash, get_tenant_id())
        )
        source_commit = cur.fetchone()
        
        if not source_commit:
            cur.close()
            return jsonify({'error': 'Source commit not found'}), 404
        
        # 2. Get the blob via tree_entry
        cur.execute(
            'SELECT blob_hash, name, mode FROM tree_entries WHERE tree_hash = %s AND tenant_id = %s',
            (source_commit['tree_hash'], get_tenant_id())
        )
        tree_entry = cur.fetchone()
        
        if not tree_entry:
            cur.close()
            return jsonify({'error': 'Source commit has no tree entry'}), 404
        
        blob_hash = tree_entry['blob_hash']
        original_message = tree_entry['name']  # commit message stored here
        memory_type = tree_entry['mode']
        
        # 3. Create new tree entry for target branch
        new_tree_hash = compute_hash(f"{target_branch}:{blob_hash}:{now}")
        cur.execute(
            '''INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
               VALUES (%s, %s, %s, %s, %s)''',
            (get_tenant_id(), new_tree_hash, f"[cherry-pick] {original_message}", blob_hash, memory_type)
        )
        
        # 4. Get or create target branch
        cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', 
                    (target_branch, get_tenant_id()))
        branch_row = cur.fetchone()
        
        if branch_row:
            target_branch = branch_row['name']  # canonical casing
            parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
        else:
            # Auto-create branch
            cur.execute(
                '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
                   VALUES (%s, %s, %s, %s)''',
                (get_tenant_id(), target_branch, 'GENESIS', now)
            )
            parent_hash = None
        
        # 5. Create new commit
        cherry_pick_message = f"[cherry-pick from {source_hash[:8]}] {original_message}"
        commit_data = f"{new_tree_hash}:{parent_hash}:{cherry_pick_message}:{now}"
        new_commit_hash = compute_hash(commit_data)
        
        cur.execute(
            '''INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (new_commit_hash, get_tenant_id(), new_tree_hash, parent_hash, 'claude', cherry_pick_message, now)
        )
        
        # 6. Update target branch head
        cur.execute(
            'UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s',
            (new_commit_hash, target_branch, get_tenant_id())
        )
        
        db.commit()
        cur.close()
        
        return jsonify({
            'status': 'cherry_picked',
            'source_hash': source_hash,
            'new_commit_hash': new_commit_hash,
            'target_branch': target_branch,
            'blob_hash': blob_hash
        }), 201
        
    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': f'Cherry-pick failed: {str(e)}'}), 500


def ensure_deprecated_commits_table():
    """Create deprecated_commits table if it doesn't exist."""
    cur = get_cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS deprecated_commits (
            commit_hash VARCHAR(64) PRIMARY KEY,
            tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
            reason TEXT,
            deprecated_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')
    get_db().commit()
    cur.close()


@app.route('/v2/commit/<commit_hash>/deprecate', methods=['POST'])
def deprecate_commit(commit_hash):
    """Soft-mark a commit as deprecated.
    
    Deprecated commits are excluded from search, log, and reflect.
    Use after cherry-picking to mark the misplaced original.
    """
    data = request.get_json() or {}
    reason = data.get('reason', 'deprecated')
    
    db = get_db()
    cur = get_cursor()
    
    try:
        # Verify commit exists
        cur.execute(
            'SELECT * FROM commits WHERE commit_hash = %s AND tenant_id = %s',
            (commit_hash, get_tenant_id())
        )
        commit = cur.fetchone()
        
        if not commit:
            cur.close()
            return jsonify({'error': 'Commit not found'}), 404
        
        # Store deprecation in a separate table (cleaner than altering commits)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS deprecated_commits (
                commit_hash VARCHAR(64) PRIMARY KEY,
                tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
                reason TEXT,
                deprecated_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')
        
        cur.execute(
            '''INSERT INTO deprecated_commits (commit_hash, tenant_id, reason)
               VALUES (%s, %s, %s)
               ON CONFLICT (commit_hash) DO UPDATE SET reason = %s, deprecated_at = NOW()''',
            (commit_hash, get_tenant_id(), reason, reason)
        )
        
        db.commit()
        cur.close()
        
        return jsonify({
            'status': 'deprecated',
            'commit_hash': commit_hash,
            'reason': reason
        })
        
    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': f'Deprecate failed: {str(e)}'}), 500


@app.route('/v2/log', methods=['GET'])
def get_log():
    """Get commit history for a branch."""
    branch = request.args.get('branch', 'command-center')
    limit = request.args.get('limit', 20, type=int)

    try:
        ensure_deprecated_commits_table()
        cur = get_cursor()
        cur.execute('SELECT head_commit FROM branches WHERE name = %s AND tenant_id = %s', (branch, get_tenant_id()))
        branch_row = cur.fetchone()

        if not branch_row:
            cur.close()
            return jsonify({'branch': branch, 'commits': [], 'count': 0})

        head_commit = branch_row['head_commit']
        if head_commit == 'GENESIS':
            cur.close()
            return jsonify({'branch': branch, 'head': 'GENESIS', 'commits': [], 'count': 0})

        commits = []
        current_hash = head_commit

        while current_hash and len(commits) < limit:
            cur.execute('SELECT * FROM commits WHERE commit_hash = %s AND tenant_id = %s', (current_hash, get_tenant_id()))
            commit = cur.fetchone()
            if not commit:
                break
            
            # Check if deprecated
            cur.execute('SELECT 1 FROM deprecated_commits WHERE commit_hash = %s', (current_hash,))
            if not cur.fetchone():
                commits.append(dict(commit))
            
            current_hash = commit['parent_hash']

        cur.close()
        return jsonify({'branch': branch, 'commits': commits, 'count': len(commits)})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/v2/search', methods=['GET'])
def search_memories():
    """Search memories across branches."""
    if HIPPOCAMPAL_ENABLED:
        ensure_hippocampal_tables()
    query = request.args.get('q', '')
    memory_type = request.args.get('type')
    limit = request.args.get('limit', 20, type=int)

    if not query:
        return jsonify({'error': 'Search query required'}), 400

    ensure_deprecated_commits_table()
    cur = get_cursor()

    sql = '''
        SELECT DISTINCT b.blob_hash, b.content, b.content_type, b.created_at,
               c.commit_hash, c.message, c.author
        FROM blobs b
        JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
        JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
        LEFT JOIN deprecated_commits dc ON c.commit_hash = dc.commit_hash
        WHERE b.content LIKE %s AND b.tenant_id = %s AND dc.commit_hash IS NULL
    '''
    params = [f'%{query}%', get_tenant_id()]

    if memory_type:
        sql += ' AND b.content_type = %s'
        params.append(memory_type)

    sql += ' ORDER BY b.created_at DESC LIMIT %s'
    params.append(limit)

    cur.execute(sql, params)
    results = []

    for row in cur.fetchall():
        content = row['content']
        results.append({
            'blob_hash': row['blob_hash'],
            'content': content[:500] + '...' if len(content) > 500 else content,
            'content_type': row['content_type'],
            'created_at': str(row['created_at']) if row['created_at'] else None,
            'commit_hash': row['commit_hash'],
            'message': row['message'],
            'author': row['author'],
            'source': 'permanent'
        })

    # v4: Also search candidate_memories (RAM) if enabled
    if HIPPOCAMPAL_ENABLED:
        try:
            remaining = limit - len(results)
            if remaining > 0:
                cur.execute("""
                    SELECT id, branch, summary, content, message, source_instance,
                           created_at
                    FROM candidate_memories
                    WHERE tenant_id = %s AND status IN ('active', 'cooling')
                      AND (summary ILIKE %s OR content::text ILIKE %s)
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (get_tenant_id(), f'%{query}%', f'%{query}%', remaining))

                for row in cur.fetchall():
                    content = row['summary']
                    if row['content']:
                        content_str = json.dumps(row['content'], default=str) if isinstance(row['content'], dict) else str(row['content'])
                        content = f"{row['summary']}\n{content_str}"
                    results.append({
                        'blob_hash': str(row['id']),
                        'content': content[:500] + '...' if len(content) > 500 else content,
                        'content_type': 'staged',
                        'created_at': str(row['created_at']) if row['created_at'] else None,
                        'commit_hash': None,
                        'message': row['message'],
                        'author': row['source_instance'],
                        'source': 'staged'
                    })
        except Exception as e:
            print(f"[SEARCH] Candidate search error: {e}", file=sys.stderr)

    # Auto-trail: track top 3 result blob hashes
    for r in results[:3]:
        if r.get('blob_hash') and r.get('source') != 'staged':
            g.accessed_blobs.add(r['blob_hash'])

    cur.close()
    return jsonify({'query': query, 'results': results, 'count': len(results)})


@app.route('/v2/semantic-search', methods=['GET'])
def semantic_search():
    """Semantic search using vector embeddings.

    Query params:
    - q: Search query (required)
    - limit: Max results (default: 10)
    """
    if HIPPOCAMPAL_ENABLED:
        ensure_hippocampal_tables()

    query = request.args.get('q', '')
    limit = request.args.get('limit', 10, type=int)

    if not query:
        return jsonify({'error': 'Search query required'}), 400

    if not OPENAI_API_KEY:
        return jsonify({'error': 'Semantic search not available - OpenAI not configured'}), 503

    # Generate embedding for the query
    query_embedding = generate_embedding(query)
    if not query_embedding:
        return jsonify({'error': 'Failed to generate query embedding'}), 500

    ensure_deprecated_commits_table()
    cur = get_cursor()

    if HIPPOCAMPAL_ENABLED:
        # v4: UNION permanent memories with staged candidates (recency-boosted)
        cur.execute("""
            SELECT * FROM (
                SELECT b.blob_hash, b.content, b.content_type, b.created_at,
                       c.commit_hash, c.message, c.author,
                       b.embedding <=> %s::vector AS distance,
                       'permanent' as source
                FROM blobs b
                JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
                JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
                LEFT JOIN deprecated_commits dc ON c.commit_hash = dc.commit_hash
                WHERE b.embedding IS NOT NULL AND b.tenant_id = %s AND dc.commit_hash IS NULL

                UNION ALL

                SELECT cm.id::text as blob_hash, cm.summary as content, 'staged' as content_type,
                       cm.created_at, NULL as commit_hash, cm.message,
                       cm.source_instance as author,
                       (cm.embedding <=> %s::vector) -
                         CASE WHEN cm.created_at > NOW() - INTERVAL '24 hours' THEN 0.1
                              WHEN cm.created_at > NOW() - INTERVAL '72 hours' THEN 0.05
                              ELSE 0 END AS distance,
                       'staged' as source
                FROM candidate_memories cm
                WHERE cm.embedding IS NOT NULL AND cm.tenant_id = %s
                  AND cm.status IN ('active', 'cooling')
            ) combined
            ORDER BY distance
            LIMIT %s
        """, (query_embedding, get_tenant_id(), query_embedding, get_tenant_id(), limit))
    else:
        # Legacy: permanent memories only
        cur.execute("""
            SELECT b.blob_hash, b.content, b.content_type, b.created_at,
                   c.commit_hash, c.message, c.author,
                   b.embedding <=> %s::vector AS distance,
                   'permanent' as source
            FROM blobs b
            JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
            JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
            LEFT JOIN deprecated_commits dc ON c.commit_hash = dc.commit_hash
            WHERE b.embedding IS NOT NULL AND b.tenant_id = %s AND dc.commit_hash IS NULL
            ORDER BY distance
            LIMIT %s
        """, (query_embedding, get_tenant_id(), limit))

    results = []
    staged_in_top3 = []  # Track staged candidates for auto-replay
    for idx, row in enumerate(cur.fetchall()):
        content = row['content']
        source = row.get('source', 'permanent') if isinstance(row, dict) else 'permanent'
        try:
            source = row['source']
        except (KeyError, TypeError):
            source = 'permanent'

        result_entry = {
            'blob_hash': row['blob_hash'],
            'content': content[:500] + '...' if len(content) > 500 else content,
            'content_type': row['content_type'],
            'created_at': str(row['created_at']) if row['created_at'] else None,
            'commit_hash': row['commit_hash'],
            'message': row['message'],
            'author': row['author'],
            'distance': float(row['distance']),
            'source': source
        }
        results.append(result_entry)

        # Collect staged candidates in top 3 for auto-replay
        if HIPPOCAMPAL_ENABLED and source == 'staged' and idx < 3:
            staged_in_top3.append(row['blob_hash'])  # This is the candidate UUID

    # Auto-replay: fire replay for staged candidates in top 3 if context is different
    if HIPPOCAMPAL_ENABLED and staged_in_top3:
        import uuid as uuid_mod
        for cand_id in staged_in_top3:
            try:
                cur.execute("""
                    SELECT id, context_embedding, embedding, replay_count, expires_at
                    FROM candidate_memories
                    WHERE id = %s AND tenant_id = %s
                """, (cand_id, get_tenant_id()))
                cand = cur.fetchone()
                if not cand:
                    continue

                # Determine threshold and which embedding to compare
                if cand['context_embedding'] is not None:
                    # Compare query vs context_embedding (0.3 threshold)
                    cur.execute("SELECT %s::vector <=> %s::vector AS ctx_distance",
                                (query_embedding, cand['context_embedding']))
                    dist_row = cur.fetchone()
                    ctx_distance = float(dist_row['ctx_distance'])
                    threshold = 0.3
                    context_type = 'context_embedding'
                else:
                    # Fallback: compare query vs content embedding (0.5 stricter threshold)
                    cur.execute("SELECT %s::vector <=> %s::vector AS ctx_distance",
                                (query_embedding, cand['embedding']))
                    dist_row = cur.fetchone()
                    ctx_distance = float(dist_row['ctx_distance'])
                    threshold = 0.5
                    context_type = 'content_fallback'

                if ctx_distance > threshold:
                    # Cooldown: max one replay per candidate per hour
                    cur.execute("""
                        SELECT 1 FROM replay_events
                        WHERE candidate_id = %s AND fired = true
                          AND created_at > NOW() - INTERVAL '1 hour'
                        LIMIT 1
                    """, (cand_id,))
                    if cur.fetchone():
                        continue  # Already replayed recently, skip

                    # Different context — fire replay
                    cur.execute("UPDATE candidate_memories SET replay_count = replay_count + 1 WHERE id = %s",
                                (cand_id,))
                    # Near-expiry rescue
                    cur.execute("""
                        UPDATE candidate_memories
                        SET expires_at = expires_at + INTERVAL '3 days'
                        WHERE id = %s AND replay_count >= 3
                          AND expires_at < NOW() + INTERVAL '48 hours'
                          AND expires_at > NOW()
                    """, (cand_id,))
                    cur.execute("""
                        INSERT INTO replay_events (id, tenant_id, candidate_id, session_id,
                                                   replay_context, similarity_score, fired,
                                                   threshold_used, context_type)
                        VALUES (%s, %s, %s, NULL, %s, %s, true, %s, %s)
                    """, (str(uuid_mod.uuid4()), get_tenant_id(), cand_id,
                          query[:200], ctx_distance, threshold, context_type))
                elif ctx_distance > (threshold - 0.1):
                    # Near-miss — log for tuning but don't fire
                    cur.execute("""
                        INSERT INTO replay_events (id, tenant_id, candidate_id, session_id,
                                                   replay_context, similarity_score, fired,
                                                   threshold_used, context_type)
                        VALUES (%s, %s, %s, NULL, %s, %s, false, %s, %s)
                    """, (str(uuid_mod.uuid4()), get_tenant_id(), cand_id,
                          query[:200], ctx_distance, threshold, context_type))
            except Exception as e:
                print(f"[AUTO-REPLAY] Error for candidate {cand_id}: {e}", file=sys.stderr)

        try:
            get_db().commit()
        except Exception:
            pass

    # Auto-trail: track top 3 result blob hashes
    for r in results[:3]:
        if r.get('blob_hash') and r.get('source') != 'staged':
            g.accessed_blobs.add(r['blob_hash'])

    cur.close()
    return jsonify({'query': query, 'results': results, 'count': len(results)})


def decrypt_blob_content(blob):
    """Decrypt blob content if encrypted, otherwise return plaintext."""
    # Check if blob has encrypted content
    if blob.get('content_encrypted') and blob.get('nonce') and blob.get('encryption_key_id'):
        encryption_service = get_encryption_service()
        if encryption_service:
            # Get the DEK for this blob
            cur = get_cursor()
            cur.execute(
                "SELECT wrapped_key FROM data_encryption_keys WHERE key_id = %s",
                (blob['encryption_key_id'],)
            )
            dek_row = cur.fetchone()
            cur.close()

            if dek_row:
                wrapped_dek = bytes(dek_row['wrapped_key'])
                ciphertext = bytes(blob['content_encrypted'])
                nonce = bytes(blob['nonce'])
                return encryption_service.decrypt_with_wrapped_dek(
                    ciphertext, nonce, blob['encryption_key_id'], wrapped_dek
                )
    # Fallback to plaintext content
    return blob.get('content', '')


@app.route('/v2/recall', methods=['GET'])
def recall_memory():
    """Recall a specific memory by hash."""
    blob_hash = request.args.get('hash')
    commit_hash = request.args.get('commit')

    cur = get_cursor()

    if blob_hash:
        cur.execute('SELECT * FROM blobs WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, get_tenant_id()))
        blob = cur.fetchone()
        if not blob:
            cur.close()
            return jsonify({'error': 'Memory not found'}), 404

        # Auto-trail: track recalled blob
        g.accessed_blobs.add(blob['blob_hash'])

        # Semantic neighbors: find k=5 nearest blobs via pgvector
        neighbors = []
        if blob.get('embedding') is not None:
            try:
                cur.execute('''
                    SELECT b.blob_hash,
                           SUBSTRING(b.content, 1, 200) as preview,
                           c.message as commit_message,
                           COALESCE(br.name, 'unknown') as branch,
                           b.embedding <=> %s::vector AS distance
                    FROM blobs b
                    JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
                    JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
                    LEFT JOIN branches br ON br.head_commit = c.commit_hash AND br.tenant_id = c.tenant_id
                    WHERE b.tenant_id = %s
                      AND b.blob_hash != %s
                      AND b.embedding IS NOT NULL
                    ORDER BY distance ASC
                    LIMIT 5
                ''', (blob['embedding'], get_tenant_id(), blob_hash))
                for row in cur.fetchall():
                    neighbors.append({
                        'blob_hash': row['blob_hash'],
                        'preview': row['preview'],
                        'commit_message': row['commit_message'],
                        'branch': row['branch'],
                        'distance': float(row['distance'])
                    })
                    # Auto-trail: add neighbors to co-access set
                    g.accessed_blobs.add(row['blob_hash'])
            except Exception as e:
                print(f"[RECALL] Semantic neighbors error: {e}", file=sys.stderr)

        cur.close()

        # Decrypt content if needed
        content = decrypt_blob_content(dict(blob))

        response_data = {
            'blob_hash': blob['blob_hash'],
            'content': content,
            'content_type': blob['content_type'],
            'created_at': str(blob['created_at']) if blob['created_at'] else None,
            'byte_size': blob['byte_size'],
            'encrypted': bool(blob.get('content_encrypted'))
        }
        if neighbors:
            response_data['semantic_neighbors'] = neighbors
        return jsonify(response_data)

    elif commit_hash:
        cur.execute(
            '''SELECT c.*, b.blob_hash as resolved_blob_hash, b.content, b.content_type, b.content_encrypted, b.nonce, b.encryption_key_id
               FROM commits c
               JOIN tree_entries t ON c.tree_hash = t.tree_hash AND c.tenant_id = t.tenant_id
               JOIN blobs b ON t.blob_hash = b.blob_hash AND t.tenant_id = b.tenant_id
               WHERE c.commit_hash = %s AND c.tenant_id = %s''',
            (commit_hash, get_tenant_id())
        )
        commit = cur.fetchone()
        cur.close()
        if not commit:
            return jsonify({'error': 'Commit not found'}), 404
        result = dict(commit)

        # Auto-trail: track recalled blob
        if result.get('resolved_blob_hash'):
            g.accessed_blobs.add(result['resolved_blob_hash'])

        # Decrypt content if needed
        result['content'] = decrypt_blob_content(result)
        result['encrypted'] = bool(result.get('content_encrypted'))

        # Clean up internal fields from response
        result.pop('content_encrypted', None)
        result.pop('nonce', None)
        result.pop('encryption_key_id', None)
        result.pop('resolved_blob_hash', None)

        if result.get('created_at'):
            result['created_at'] = str(result['created_at'])
        return jsonify(result)

    return jsonify({'error': 'Hash or commit required'}), 400

@app.route('/v2/quick-brief', methods=['GET'])
def quick_brief():
    """Get a context brief for current state."""
    branch = request.args.get('branch', 'command-center')

    cur = get_cursor()
    cur.execute('SELECT * FROM branches WHERE name = %s AND tenant_id = %s', (branch, get_tenant_id()))
    branch_info = cur.fetchone()

    if not branch_info:
        cur.close()
        return jsonify({'error': f'Branch {branch} not found'}), 404

    cur.execute(
        '''SELECT commit_hash, message, created_at, author
           FROM commits WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 5''',
        (get_tenant_id(),)
    )
    recent_commits = []
    for row in cur.fetchall():
        r = dict(row)
        if r.get('created_at'):
            r['created_at'] = str(r['created_at'])
        recent_commits.append(r)

    cur.execute(
        '''SELECT session_id, branch, summary, synced_at
           FROM sessions WHERE tenant_id = %s ORDER BY synced_at DESC LIMIT 5''',
        (get_tenant_id(),)
    )
    pending_sessions = []
    for row in cur.fetchall():
        r = dict(row)
        if r.get('synced_at'):
            r['synced_at'] = str(r['synced_at'])
        pending_sessions.append(r)

    cur.execute('SELECT name FROM branches WHERE tenant_id = %s', (get_tenant_id(),))
    branches = [dict(row) for row in cur.fetchall()]

    cur.close()
    return jsonify({
        'current_branch': branch,
        'head_commit': branch_info['head_commit'],
        'recent_commits': recent_commits,
        'pending_sessions': pending_sessions,
        'branches': branches,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


@app.route('/v2/startup', methods=['GET'])
def semantic_startup():
    """v3 semantic startup - pull contextually relevant memories.

    Uses semantic search to find the most relevant memories for the
    current conversation context, rather than hardcoded lookups.

    If HIPPOCAMPAL_ENABLED, also returns recent bookmarks from working memory.

    Query params:
    - context: Optional context string to search for relevant memories
    - k: Number of relevant memories to return (default: 5)
    - agent_id: Optional agent ID to filter tasks assigned to this agent
    - verbosity: minimal | normal | full (default: normal)
      - minimal: sacred_manifest + top 3 tasks (slim) + local_time
      - normal: sacred_manifest + tasks (5) + relevant_memories (3) - no tool_registry
      - full: everything including tool_registry and hot_memories
    """
    context = request.args.get('context', 'important decisions and active commitments')
    k = request.args.get('k', 5, type=int)
    agent_id = request.args.get('agent_id')  # Filter tasks for specific agent
    verbosity = request.args.get('verbosity', 'normal')  # minimal, normal, full

    cur = get_cursor()

    # Always include sacred commitments via literal search
    sacred_manifest = None
    tool_registry = None

    # Fetch sacred_manifest
    cur.execute("""
        SELECT b.content FROM blobs b
        WHERE b.content LIKE %s AND b.tenant_id = %s
        ORDER BY b.created_at DESC LIMIT 1
    """, ('%"type": "sacred_manifest"%', get_tenant_id()))
    row = cur.fetchone()
    if row:
        try:
            sacred_manifest = json.loads(row['content'])
        except:
            pass

    # Fetch tool_registry
    cur.execute("""
        SELECT b.content FROM blobs b
        WHERE b.content LIKE %s AND b.tenant_id = %s
        ORDER BY b.created_at DESC LIMIT 1
    """, ('%"type": "tool_registry"%', get_tenant_id()))
    row = cur.fetchone()
    if row:
        try:
            tool_registry = json.loads(row['content'])
        except:
            pass

    # Semantic search for contextually relevant memories
    relevant_memories = []
    if OPENAI_API_KEY:
        query_embedding = generate_embedding(context)
        if query_embedding:
            cur.execute("""
                SELECT b.blob_hash, substring(b.content, 1, 300) as preview,
                       c.message, b.content_type, b.embedding <=> %s::vector AS distance
                FROM blobs b
                JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
                JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
                WHERE b.embedding IS NOT NULL AND b.tenant_id = %s
                ORDER BY distance LIMIT %s
            """, (query_embedding, get_tenant_id(), k))
            for row in cur.fetchall():
                relevant_memories.append({
                    'blob_hash': row['blob_hash'],
                    'preview': row['preview'],
                    'message': row['message'],
                    'content_type': row.get('content_type', 'memory'),
                    'distance': float(row['distance'])
                })
                # Auto-trail: track startup relevant memories
                g.accessed_blobs.add(row['blob_hash'])

    # Boost semantic scores by trail strength (hot paths surface higher)
    hot_memories = []
    try:
        # Get trail strength for each blob in relevant_memories
        if relevant_memories:
            blob_hashes = [m['blob_hash'] for m in relevant_memories]
            placeholders = ','.join(['%s'] * len(blob_hashes))
            cur.execute(f"""
                SELECT blob_hash, SUM(strength) as total_strength
                FROM (
                    SELECT source_blob as blob_hash, strength FROM trails
                    WHERE tenant_id = %s AND source_blob IN ({placeholders})
                    UNION ALL
                    SELECT target_blob as blob_hash, strength FROM trails
                    WHERE tenant_id = %s AND target_blob IN ({placeholders})
                ) t
                GROUP BY blob_hash
            """, (get_tenant_id(), *blob_hashes, get_tenant_id(), *blob_hashes))

            trail_strengths = {row['blob_hash']: float(row['total_strength']) for row in cur.fetchall()}

            # Boost scores: lower distance = higher relevance
            # Formula: adjusted = distance * (1 / (1 + log(1 + strength)))
            for mem in relevant_memories:
                strength = trail_strengths.get(mem['blob_hash'], 0)
                if strength > 0:
                    boost_factor = 1 / (1 + math.log(1 + strength))
                    mem['original_distance'] = mem['distance']
                    mem['distance'] = mem['distance'] * boost_factor
                    mem['trail_strength'] = strength
                    mem['boosted'] = True

            # Re-sort by adjusted distance
            relevant_memories.sort(key=lambda m: m['distance'])

        # Get hot memories (most traversed, independent of semantic search)
        cur.execute("""
            SELECT blob_hash, SUM(strength) as total_strength, SUM(traversal_count) as total_traversals
            FROM (
                SELECT source_blob as blob_hash, strength, traversal_count FROM trails WHERE tenant_id = %s
                UNION ALL
                SELECT target_blob as blob_hash, strength, traversal_count FROM trails WHERE tenant_id = %s
            ) t
            GROUP BY blob_hash
            ORDER BY total_strength DESC
            LIMIT 5
        """, (get_tenant_id(), get_tenant_id()))

        hot_blob_hashes = []
        hot_strengths = {}
        for row in cur.fetchall():
            hot_blob_hashes.append(row['blob_hash'])
            hot_strengths[row['blob_hash']] = {
                'strength': float(row['total_strength']),
                'traversals': int(row['total_traversals'])
            }

        # Fetch memory details for hot blobs
        if hot_blob_hashes:
            placeholders = ','.join(['%s'] * len(hot_blob_hashes))
            cur.execute(f"""
                SELECT b.blob_hash, substring(b.content, 1, 300) as preview, c.message
                FROM blobs b
                JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
                JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
                WHERE b.tenant_id = %s AND b.blob_hash IN ({placeholders})
            """, (get_tenant_id(), *hot_blob_hashes))

            blob_details = {row['blob_hash']: row for row in cur.fetchall()}

            for blob_hash in hot_blob_hashes:
                if blob_hash in blob_details:
                    row = blob_details[blob_hash]
                    hot_memories.append({
                        'blob_hash': blob_hash,
                        'preview': row['preview'],
                        'message': row['message'],
                        'trail_strength': hot_strengths[blob_hash]['strength'],
                        'traversal_count': hot_strengths[blob_hash]['traversals']
                    })
    except Exception as e:
        # trails table might not exist - that's ok
        pass

    # Discovery blobs — orphaned memories worth connecting
    discovery_blobs = []
    try:
        ensure_discovery_queue_table()
        cur_disc = get_cursor()
        cur_disc.execute('''
            SELECT blob_hash, preview, commit_message, branch,
                   orphan_score, value_score
            FROM discovery_queue
            WHERE tenant_id = %s AND status = 'pending'
            ORDER BY value_score DESC
            LIMIT 3
        ''', (get_tenant_id(),))
        discovery_blobs = [dict(row) for row in cur_disc.fetchall()]

        # Mark as consumed
        if discovery_blobs:
            consumed_hashes = [d['blob_hash'] for d in discovery_blobs]
            cur_disc.execute('''
                UPDATE discovery_queue
                SET status = 'consumed', consumed_at = NOW(),
                    consumed_by = %s
                WHERE tenant_id = %s AND blob_hash = ANY(%s)
            ''', (request.args.get('instance_id', 'unknown'),
                  get_tenant_id(), consumed_hashes))
            get_db().commit()

            # Auto-trail: seed discovered blobs into co-access set
            for d in discovery_blobs:
                g.accessed_blobs.add(d['blob_hash'])
                # Convert Decimal/float for JSON serialization
                d['orphan_score'] = float(d['orphan_score'])
                d['value_score'] = float(d['value_score'])
        cur_disc.close()
    except Exception:
        pass  # Non-critical — don't break startup

    # Work Landscape: branches as projects, plans with progress, orphan backlog
    work_landscape = {}
    backlog = []
    my_tasks = []
    open_tasks = []  # Kept for backward compat in minimal/normal verbosity
    try:
        # Get active plans (blobs with content_type='plan')
        cur.execute("""
            SELECT DISTINCT b.blob_hash, b.content, b.created_at
            FROM blobs b
            WHERE b.tenant_id = %s AND b.content_type = 'plan'
              AND (b.content::jsonb->>'status') IN ('active', 'paused')
            ORDER BY b.created_at DESC
        """, (get_tenant_id(),))
        plan_rows = cur.fetchall()

        plans_by_branch = {}
        for row in plan_rows:
            content = row['content']
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    content = {}
            blob_hash = row['blob_hash']
            plan_title = content.get('title', 'Untitled Plan')
            plan_status = content.get('status', 'active')

            # Get branch from commit chain
            cur.execute("""
                SELECT br.name
                FROM tree_entries te
                JOIN commits co ON co.tree_hash = te.tree_hash AND co.tenant_id = te.tenant_id
                JOIN branches br ON br.tenant_id = co.tenant_id
                WHERE te.blob_hash = %s AND te.tenant_id = %s
                LIMIT 1
            """, (blob_hash, get_tenant_id()))
            branch_row = cur.fetchone()
            plan_branch = branch_row['name'] if branch_row else 'unknown'

            # Count tasks under this plan
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE status = 'done') as done
                FROM tasks
                WHERE tenant_id = %s AND plan_blob_hash = %s AND status != 'deleted'
            """, (get_tenant_id(), blob_hash))
            counts = cur.fetchone()
            task_count = counts['total'] if counts else 0
            done_count = counts['done'] if counts else 0

            if plan_branch not in plans_by_branch:
                plans_by_branch[plan_branch] = []
            plans_by_branch[plan_branch].append({
                'title': plan_title,
                'status': plan_status,
                'blob_hash': blob_hash,
                'progress': f"{done_count}/{task_count}",
                'task_count': task_count,
                'done_count': done_count
            })

        # Build landscape with health scores
        for branch_name, plans in plans_by_branch.items():
            total_tasks = sum(p['task_count'] for p in plans)
            done_tasks = sum(p['done_count'] for p in plans)
            health = f"{round(done_tasks / total_tasks * 100)}%" if total_tasks > 0 else "no tasks"
            work_landscape[branch_name] = {
                'plans': plans,
                'health': health
            }

        # Orphan backlog: tasks not under any plan
        cur.execute("""
            SELECT id, title, description, branch, priority, assigned_to, status
            FROM tasks
            WHERE tenant_id = %s AND (plan_blob_hash IS NULL)
              AND status IN ('open', 'claimed', 'blocked')
            ORDER BY priority ASC, created_at ASC
            LIMIT 20
        """, (get_tenant_id(),))
        for row in cur.fetchall():
            task_entry = {
                'id': str(row['id']),
                'title': row.get('title') or (row['description'][:80] if row['description'] else ''),
                'branch': row['branch'],
                'priority': row['priority'],
                'assigned_to': row['assigned_to']
            }
            backlog.append(task_entry)
            # Also populate open_tasks for backward compat
            open_tasks.append({
                'id': str(row['id']),
                'description': row.get('title') or row['description'],
                'branch': row['branch'],
                'priority': row['priority'],
                'assigned_to': row['assigned_to']
            })

        # Agent-specific tasks
        if agent_id:
            cur.execute("""
                SELECT id, title, description, branch, assigned_to, priority, created_at
                FROM tasks
                WHERE tenant_id = %s AND status = 'open' AND assigned_to = %s
                ORDER BY priority ASC, created_at ASC
            """, (get_tenant_id(), agent_id))
            for row in cur.fetchall():
                my_tasks.append({
                    'id': str(row['id']),
                    'title': row.get('title'),
                    'description': row['description'],
                    'branch': row['branch'],
                    'assigned_to': row['assigned_to'],
                    'priority': row['priority'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None
                })
    except Exception as e:
        # tasks table or columns might not exist yet - that's ok
        print(f"[STARTUP] Work landscape query error (non-fatal): {e}", file=sys.stderr)
        pass

    # v4: Recent bookmarks (working memory / RAM)
    recent_bookmarks = []
    if HIPPOCAMPAL_ENABLED:
        ensure_hippocampal_tables()
        try:
            cur.execute("""
                SELECT id, branch, summary, salience, replay_count, created_at, expires_at
                FROM candidate_memories
                WHERE tenant_id = %s AND status IN ('active', 'cooling')
                  AND created_at > NOW() - INTERVAL '48 hours'
                ORDER BY created_at DESC
                LIMIT 10
            """, (get_tenant_id(),))
            for row in cur.fetchall():
                recent_bookmarks.append({
                    'id': str(row['id']),
                    'branch': row['branch'],
                    'summary': row['summary'],
                    'salience': row['salience'],
                    'replay_count': row['replay_count'],
                    'created_at': str(row['created_at']) if row['created_at'] else None,
                    'expires_at': str(row['expires_at']) if row['expires_at'] else None
                })
        except Exception as e:
            print(f"[STARTUP] Bookmark fetch error: {e}", file=sys.stderr)

    cur.close()

    # Build timestamp first - this orients the AI temporally
    now_utc = datetime.utcnow()
    timestamp_utc = now_utc.isoformat() + 'Z'

    # Convert to Steve's local time (America/New_York)
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo('America/New_York')
    now_local = now_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(eastern)
    local_time = now_local.strftime('%A, %B %d, %Y at %I:%M %p %Z')

    # Build response based on verbosity level
    if verbosity == 'minimal':
        # Bare essentials: sacred manifest + slim backlog
        slim_backlog = [{
            'id': t['id'],
            'title': t.get('title', t.get('description', '')[:80]),
            'priority': t['priority']
        } for t in backlog[:3]]

        response = {
            'local_time': local_time,
            'sacred_manifest': sacred_manifest,
            'open_tasks': slim_backlog,
            'verbosity': 'minimal'
        }
    elif verbosity == 'full':
        # Everything for debugging — full landscape
        response = {
            'timestamp': timestamp_utc,
            'local_time': local_time,
            'sacred_manifest': sacred_manifest,
            'tool_registry': tool_registry,
            'relevant_memories': relevant_memories,
            'hot_memories': hot_memories,
            'work_landscape': work_landscape,
            'backlog': backlog,
            'open_tasks': open_tasks,
            'context_used': context,
            'verbosity': 'full'
        }
    else:
        # normal (default): balanced payload with landscape
        trimmed_memories = [{
            'blob_hash': m['blob_hash'],
            'message': m['message'],
            'content_type': m.get('content_type', 'memory'),
            'distance': m.get('distance')
        } for m in relevant_memories[:3]]

        response = {
            'timestamp': timestamp_utc,
            'local_time': local_time,
            'sacred_manifest': sacred_manifest,
            'relevant_memories': trimmed_memories,
            'work_landscape': work_landscape,
            'backlog': backlog,
            'open_tasks': open_tasks,
            'context_used': context,
            'verbosity': 'normal'
        }

    # v4: Add recent bookmarks if available
    if HIPPOCAMPAL_ENABLED and recent_bookmarks:
        response['recent_bookmarks'] = recent_bookmarks

    # v5: Discovery blobs — orphaned memories surfaced for reconnection
    if discovery_blobs and verbosity != 'minimal':
        response['discovery_blobs'] = discovery_blobs

    # v6: Skills loaded — behavioral instructions surfaced via semantic search
    source_memories = relevant_memories if verbosity == 'full' else trimmed_memories if verbosity != 'minimal' else []
    loaded_skills = [m for m in source_memories if m.get('content_type') == 'skill']
    if loaded_skills:
        response['skills_loaded'] = [{
            'blob_hash': s['blob_hash'],
            'message': s['message'],
            'hint': 'Behavioral skill - recall full content and follow as instructions'
        } for s in loaded_skills]

    # If agent_id provided, add their specific tasks
    if agent_id:
        response['agent_id'] = agent_id
        response['my_tasks'] = my_tasks

    # Surface quarantine alert if there are quarantined memories
    try:
        quarantine_count = get_quarantine_count()
        if quarantine_count > 0:
            response['quarantine_alert'] = {
                'count': quarantine_count,
                'message': f"{quarantine_count} memories quarantined - run boswell_quarantine_list to review"
            }
    except Exception:
        pass  # immune system tables might not exist yet

    return jsonify(response)


# ==================== CROSS-REFERENCES ====================

@app.route('/v2/link', methods=['POST'])
def create_link():
    """Create a resonance link between two memories."""
    data = request.get_json() or {}
    source_blob = data.get('source_blob')
    target_blob = data.get('target_blob')
    source_branch = data.get('source_branch')
    target_branch = data.get('target_branch')
    link_type = data.get('link_type', 'resonance')
    weight = data.get('weight', 1.0)
    reasoning = data.get('reasoning', '')

    if not all([source_blob, target_blob, source_branch, target_branch]):
        return jsonify({'error': 'source_blob, target_blob, source_branch, target_branch required'}), 400

    valid_types = ['resonance', 'causal', 'contradiction', 'elaboration', 'application']
    if link_type not in valid_types:
        return jsonify({'error': f'Invalid link_type. Must be one of: {valid_types}'}), 400

    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'

    try:
        cur.execute(
            '''INSERT INTO cross_references
               (tenant_id, source_blob, target_blob, source_branch, target_branch,
                link_type, weight, reasoning, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (get_tenant_id(), source_blob, target_blob, source_branch, target_branch,
             link_type, weight, reasoning, now)
        )
        db.commit()
        cur.close()

        return jsonify({
            'status': 'linked',
            'source_blob': source_blob,
            'target_blob': target_blob,
            'link_type': link_type,
            'created_at': now
        }), 201

    except psycopg2.IntegrityError as e:
        db.rollback()
        cur.close()
        if 'unique' in str(e).lower():
            return jsonify({'error': 'Link already exists between these blobs'}), 409
        return jsonify({'error': str(e)}), 400

@app.route('/v2/links', methods=['GET'])
def list_links():
    """List cross-references with optional filtering."""
    blob = request.args.get('blob')
    branch = request.args.get('branch')
    link_type = request.args.get('type')
    limit = request.args.get('limit', 50, type=int)

    cur = get_cursor()

    sql = 'SELECT * FROM cross_references WHERE tenant_id = %s'
    params = [get_tenant_id()]

    if blob:
        sql += ' AND (source_blob = %s OR target_blob = %s)'
        params.extend([blob, blob])

    if branch:
        sql += ' AND (source_branch = %s OR target_branch = %s)'
        params.extend([branch, branch])

    if link_type:
        sql += ' AND link_type = %s'
        params.append(link_type)

    sql += ' ORDER BY created_at DESC LIMIT %s'
    params.append(limit)

    cur.execute(sql, params)
    links = []
    for row in cur.fetchall():
        r = dict(row)
        if r.get('created_at'):
            r['created_at'] = str(r['created_at'])
        links.append(r)

    cur.close()
    return jsonify({'links': links, 'count': len(links)})

@app.route('/v2/graph', methods=['GET'])
def get_graph():
    """Get graph representation for visualization."""
    branch = request.args.get('branch')
    limit = request.args.get('limit', 100, type=int)

    cur = get_cursor()

    if branch:
        nodes_sql = '''
            SELECT DISTINCT b.blob_hash, b.content_type, b.created_at,
                   b.content as preview
            FROM blobs b
            JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
            JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
            JOIN branches br ON (c.commit_hash = br.head_commit OR c.parent_hash IS NOT NULL) AND br.tenant_id = c.tenant_id
            WHERE br.name = %s AND b.tenant_id = %s
            LIMIT %s
        '''
        cur.execute(nodes_sql, (branch, get_tenant_id(), limit))
    else:
        nodes_sql = '''
            SELECT blob_hash, content_type, created_at,
                   content as preview
            FROM blobs WHERE tenant_id = %s ORDER BY created_at DESC LIMIT %s
        '''
        cur.execute(nodes_sql, (get_tenant_id(), limit))

    rows = cur.fetchall()

    # Batch lookup branches for all blobs (O(1) queries instead of O(N))
    blob_hashes = [row['blob_hash'] for row in rows]
    branch_map = get_blob_branches_batch(cur, blob_hashes, get_tenant_id())

    nodes = []
    for row in rows:
        nodes.append({
            'id': row['blob_hash'],
            'type': row['content_type'],
            'created_at': str(row['created_at']) if row['created_at'] else None,
            'preview': row['preview'],
            'branch': branch_map.get(row['blob_hash'], 'unknown')
        })

    if branch:
        edges_sql = '''
            SELECT * FROM cross_references
            WHERE (source_branch = %s OR target_branch = %s) AND tenant_id = %s LIMIT %s
        '''
        cur.execute(edges_sql, (branch, branch, get_tenant_id(), limit))
    else:
        edges_sql = 'SELECT * FROM cross_references WHERE tenant_id = %s LIMIT %s'
        cur.execute(edges_sql, (get_tenant_id(), limit))

    edges = []
    for row in cur.fetchall():
        edges.append({
            'source': row['source_blob'],
            'target': row['target_blob'],
            'type': row['link_type'],
            'weight': row['weight'],
            'reasoning': row['reasoning']
        })

    cur.close()
    return jsonify({
        'nodes': nodes,
        'edges': edges,
        'node_count': len(nodes),
        'edge_count': len(edges)
    })

@app.route('/v2/reflect', methods=['GET'])
def reflect():
    """Surface latent insights by cross-branch link density."""
    min_links = request.args.get('min_links', 2, type=int)
    limit = request.args.get('limit', 20, type=int)

    cur = get_cursor()

    # Postgres version - wrap in subquery to filter by computed column
    sql = '''
        SELECT * FROM (
            SELECT b.blob_hash, b.content_type, b.content as preview,
                   (SELECT COUNT(*) FROM cross_references cr
                    WHERE (cr.source_blob = b.blob_hash OR cr.target_blob = b.blob_hash)
                    AND cr.tenant_id = %s) as link_count
            FROM blobs b
            WHERE b.tenant_id = %s
        ) subquery
        WHERE link_count >= %s
        ORDER BY link_count DESC
        LIMIT %s
    '''

    cur.execute(sql, (get_tenant_id(), get_tenant_id(), min_links, limit))
    insights = []

    for row in cur.fetchall():
        insights.append({
            'blob_hash': row['blob_hash'],
            'link_count': row['link_count'],
            'content_type': row['content_type'],
            'preview': row['preview']
        })

    cross_branch_sql = '''
        SELECT cr.*,
               substring(b1.content, 1, 200) as source_preview,
               substring(b2.content, 1, 200) as target_preview
        FROM cross_references cr
        JOIN blobs b1 ON cr.source_blob = b1.blob_hash AND cr.tenant_id = b1.tenant_id
        JOIN blobs b2 ON cr.target_blob = b2.blob_hash AND cr.tenant_id = b2.tenant_id
        WHERE cr.source_branch != cr.target_branch AND cr.tenant_id = %s
        ORDER BY cr.weight DESC, cr.created_at DESC
        LIMIT %s
    '''
    cur.execute(cross_branch_sql, (get_tenant_id(), limit))
    cross_branch_links = []
    for row in cur.fetchall():
        r = dict(row)
        if r.get('created_at'):
            r['created_at'] = str(r['created_at'])
        cross_branch_links.append(r)

    cur.close()
    return jsonify({
        'highly_connected': insights,
        'cross_branch_links': cross_branch_links,
        'insight': 'Memories with high link counts represent conceptual hubs. Cross-branch links reveal how ideas flow between cognitive domains.',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

# ==================== CONNECTOME ANALYSIS ====================

# Domain classification markers for content analysis
DOMAIN_MARKERS = {
    'thalamus': ['browser', 'automation', 'screenshot', 'perception', 'chrome', 'tab', 'click', 'navigate', 'mcp', 'claude-in-chrome'],
    'infrastructure': ['deploy', 'railway', 'api', 'endpoint', 'migration', 'schema', 'database', 'postgres', 'redis', 'docker', 'server'],
    'business': ['tint', 'crm', 'customer', 'franchise', 'atlanta', 'empire', 'square', 'payment', 'invoice', 'booking'],
    'research': ['iris', 'bci', 'neural', 'research', 'embedding', 'vector', 'semantic', 'ml', 'model'],
    'personal': ['family', 'diego', 'lineage', 'personal'],
    'boswell': ['memory', 'commit', 'branch', 'graph', 'connectome', 'recall', 'startup', 'trail']
}

# Common stopwords to exclude from shared word analysis
STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
    'that', 'this', 'these', 'those', 'it', 'its', 'they', 'them', 'their', 'he', 'she',
    'his', 'her', 'we', 'our', 'you', 'your', 'i', 'my', 'me', 'not', 'no', 'yes',
    'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such',
    'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'also', 'now', 'here',
    'there', 'when', 'where', 'why', 'how', 'what', 'which', 'who', 'whom', 'whose',
    'if', 'then', 'else', 'because', 'while', 'although', 'though', 'after', 'before',
    'true', 'false', 'null', 'none', 'type', 'date', 'time', 'status', 'data', 'value',
    'new', 'get', 'set', 'add', 'update', 'delete', 'create', 'read', 'write'
}


@app.route('/v2/analyze/debug', methods=['GET'])
def analyze_debug():
    """Debug endpoint to test numpy and embedding loading."""
    try:
        import numpy as np
        numpy_version = np.__version__

        cur = get_cursor()

        # Test 1: Can we query blobs?
        cur.execute('SELECT COUNT(*) as cnt FROM blobs WHERE tenant_id = %s', (get_tenant_id(),))
        blob_count = cur.fetchone()['cnt']

        # Test 2: Can we get embeddings?
        cur.execute('''
            SELECT blob_hash, embedding
            FROM blobs
            WHERE embedding IS NOT NULL AND tenant_id = %s
            LIMIT 1
        ''', (get_tenant_id(),))
        row = cur.fetchone()

        embedding_info = None
        if row:
            emb = row['embedding']
            embedding_info = {
                'type': str(type(emb)),
                'has_data': emb is not None,
            }
            # Try to convert to numpy
            try:
                arr = np.array(emb)
                embedding_info['numpy_shape'] = str(arr.shape)
                embedding_info['numpy_dtype'] = str(arr.dtype)
            except Exception as e:
                embedding_info['numpy_error'] = str(e)

        cur.close()

        return jsonify({
            'numpy_version': numpy_version,
            'blob_count': blob_count,
            'embedding_info': embedding_info,
            'status': 'ok'
        })

    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


def classify_content(content: str) -> list:
    """Classify content into semantic domains based on keyword markers."""
    if not content:
        return ['general']
    content_lower = content.lower()
    domains = []
    for domain, markers in DOMAIN_MARKERS.items():
        if any(marker in content_lower for marker in markers):
            domains.append(domain)
    return domains or ['general']


def generate_link_reasoning(content_a: str, content_b: str, distance: float) -> str:
    """Generate reasoning for why two memories are linked."""
    domains_a = classify_content(content_a)
    domains_b = classify_content(content_b)
    shared_domains = set(domains_a) & set(domains_b)

    if shared_domains:
        return f"Both relate to: {', '.join(sorted(shared_domains))}"

    # Extract key terms (words > 4 chars, not stopwords)
    words_a = set(w for w in content_a.lower().split() if len(w) > 4 and w not in STOPWORDS)
    words_b = set(w for w in content_b.lower().split() if len(w) > 4 and w not in STOPWORDS)
    shared_words = words_a & words_b

    if len(shared_words) >= 3:
        top_shared = sorted(shared_words, key=lambda w: len(w), reverse=True)[:5]
        return f"Shared concepts: {', '.join(top_shared)}"

    return f"Semantic similarity (distance: {distance:.3f})"


def get_blob_branch(cur, blob_hash: str, tenant_id: str) -> str:
    """Get the branch a blob belongs to by walking commit chains from HEAD."""
    # First, find the commit that contains this blob
    cur.execute('''
        SELECT c.commit_hash
        FROM tree_entries t
        JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
        WHERE t.blob_hash = %s AND t.tenant_id = %s
        LIMIT 1
    ''', (blob_hash, tenant_id))
    commit_row = cur.fetchone()
    if not commit_row:
        # Fallback: check blob content for known patterns (orphaned bulk imports)
        cur.execute('SELECT content FROM blobs WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, tenant_id))
        blob_row = cur.fetchone()
        if blob_row and blob_row['content']:
            content_lower = blob_row['content'].lower()
            # Iris research data patterns
            if any(p in content_lower for p in ['institution', 'faculty', 'neuroscience', 'professor', 'research']):
                return 'iris'
        return 'unknown'

    target_commit = commit_row['commit_hash']

    # Now find which branch contains this commit by walking from each HEAD
    cur.execute('''
        WITH RECURSIVE commit_chain AS (
            -- Start from all branch heads
            SELECT br.name as branch_name, c.commit_hash, c.parent_hash, 1 as depth
            FROM branches br
            JOIN commits c ON br.head_commit = c.commit_hash AND br.tenant_id = c.tenant_id
            WHERE br.tenant_id = %s AND br.head_commit != 'GENESIS'

            UNION ALL

            -- Walk backwards through parent commits
            SELECT cc.branch_name, c.commit_hash, c.parent_hash, cc.depth + 1
            FROM commit_chain cc
            JOIN commits c ON cc.parent_hash = c.commit_hash
            WHERE c.tenant_id = %s AND cc.depth < 500
        )
        SELECT branch_name FROM commit_chain
        WHERE commit_hash = %s
        LIMIT 1
    ''', (tenant_id, tenant_id, target_commit))

    row = cur.fetchone()
    return row['branch_name'] if row else 'unknown'


def get_blob_branches_batch(cur, blob_hashes: list, tenant_id: str) -> dict:
    """Get branches for multiple blobs in one query. Returns {blob_hash: branch_name}."""
    if not blob_hashes:
        return {}

    result = {}

    # Build commit chain CTE once, then join all blobs
    # This is O(1) queries instead of O(N)
    cur.execute('''
        WITH RECURSIVE commit_chain AS (
            SELECT br.name as branch_name, c.commit_hash, c.parent_hash, 1 as depth
            FROM branches br
            JOIN commits c ON br.head_commit = c.commit_hash AND br.tenant_id = c.tenant_id
            WHERE br.tenant_id = %s AND br.head_commit != 'GENESIS'
            UNION ALL
            SELECT cc.branch_name, c.commit_hash, c.parent_hash, cc.depth + 1
            FROM commit_chain cc
            JOIN commits c ON cc.parent_hash = c.commit_hash
            WHERE c.tenant_id = %s AND cc.depth < 500
        )
        SELECT DISTINCT t.blob_hash, cc.branch_name
        FROM tree_entries t
        JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
        JOIN commit_chain cc ON c.commit_hash = cc.commit_hash
        WHERE t.blob_hash = ANY(%s) AND t.tenant_id = %s
    ''', (tenant_id, tenant_id, blob_hashes, tenant_id))

    for row in cur.fetchall():
        result[row['blob_hash']] = row['branch_name']

    # Handle orphaned blobs (no tree_entries) with content-based fallback
    missing = [h for h in blob_hashes if h not in result]
    if missing:
        cur.execute('''
            SELECT blob_hash, content FROM blobs
            WHERE blob_hash = ANY(%s) AND tenant_id = %s
        ''', (missing, tenant_id))
        for row in cur.fetchall():
            content_lower = (row['content'] or '').lower()
            if any(p in content_lower for p in ['institution', 'faculty', 'neuroscience', 'professor', 'research']):
                result[row['blob_hash']] = 'iris'
            else:
                result[row['blob_hash']] = 'unknown'

    return result


@app.route('/v2/analyze', methods=['POST'])
def analyze_connectome():
    """
    Analyze the memory graph and discover semantic relationships.

    Request body (JSON):
    - similarity_threshold: float (default 0.25) - max cosine distance for linking
    - min_weight: float (default 0.5) - minimum link weight to create
    - dry_run: bool (default True) - if True, return analysis without creating links
    - propagate_tags: bool (default False) - if True, propagate tags to similar blobs
    - tag_threshold: float (default 0.3) - max distance for tag propagation
    - limit: int (default 100) - max number of links to create/preview

    Returns:
    - stats: analysis statistics
    - links_preview: proposed or created links
    - tags_preview: proposed tag propagations (if propagate_tags=True)
    - cross_branch_insights: summary of cross-branch connections
    """
    try:
        return _analyze_connectome_impl()
    except Exception as e:
        import traceback
        print(f"[ANALYZE] Error: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


def _analyze_connectome_impl():
    """Internal implementation of analyze_connectome."""
    data = request.get_json() or {}
    similarity_threshold = data.get('similarity_threshold', 0.25)
    min_weight = data.get('min_weight', 0.5)
    dry_run = data.get('dry_run', True)
    propagate_tags = data.get('propagate_tags', False)
    tag_threshold = data.get('tag_threshold', 0.3)
    limit = min(data.get('limit', 100), 500)  # Cap at 500

    if not OPENAI_API_KEY:
        return jsonify({'error': 'Semantic analysis not available - OpenAI not configured'}), 503

    cur = get_cursor()
    db = get_db()

    # 1. Load all blobs with embeddings
    cur.execute('''
        SELECT blob_hash, content, embedding
        FROM blobs
        WHERE embedding IS NOT NULL AND tenant_id = %s
    ''', (get_tenant_id(),))

    blobs = []
    for row in cur.fetchall():
        blobs.append({
            'hash': row['blob_hash'],
            'content': row['content'] or '',
            'embedding': row['embedding']
        })

    # 2. Load existing links to avoid duplicates
    cur.execute('''
        SELECT source_blob || '-' || target_blob as link_key
        FROM cross_references
        WHERE tenant_id = %s
    ''', (get_tenant_id(),))
    existing_links = set(row['link_key'] for row in cur.fetchall())

    # Also add reverse keys
    cur.execute('''
        SELECT target_blob || '-' || source_blob as link_key
        FROM cross_references
        WHERE tenant_id = %s
    ''', (get_tenant_id(),))
    existing_links.update(row['link_key'] for row in cur.fetchall())

    # 3. Compute pairwise similarities for blobs with embeddings
    proposed_links = []
    cross_branch_stats = {}

    for i, blob_a in enumerate(blobs):
        if len(proposed_links) >= limit:
            break

        for blob_b in blobs[i+1:]:
            if len(proposed_links) >= limit:
                break

            # Check if link already exists
            link_key = f"{blob_a['hash']}-{blob_b['hash']}"
            reverse_key = f"{blob_b['hash']}-{blob_a['hash']}"
            if link_key in existing_links or reverse_key in existing_links:
                continue

            # Compute cosine distance
            try:
                emb_a = np.array(blob_a['embedding'])
                emb_b = np.array(blob_b['embedding'])
                # Cosine distance = 1 - cosine_similarity
                cos_sim = np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b))
                distance = 1 - cos_sim
            except Exception:
                continue

            if distance < similarity_threshold:
                weight = min(1 / (distance + 0.1), 5.0)  # Cap at 5.0 to prevent visual dominance
                if weight >= min_weight:
                    # Get branches for both blobs
                    source_branch = get_blob_branch(cur, blob_a['hash'], get_tenant_id())
                    target_branch = get_blob_branch(cur, blob_b['hash'], get_tenant_id())

                    # Skip orphan blobs (not in any commit chain)
                    if source_branch == 'unknown' or target_branch == 'unknown':
                        continue

                    reasoning = generate_link_reasoning(
                        blob_a['content'][:1000],
                        blob_b['content'][:1000],
                        distance
                    )

                    proposed_links.append({
                        'source': blob_a['hash'],
                        'target': blob_b['hash'],
                        'source_branch': source_branch,
                        'target_branch': target_branch,
                        'distance': float(round(distance, 4)),
                        'weight': float(round(weight, 2)),
                        'reasoning': reasoning,
                        'cross_branch': source_branch != target_branch
                    })

                    # Track cross-branch stats
                    if source_branch != target_branch:
                        key = tuple(sorted([source_branch, target_branch]))
                        if key not in cross_branch_stats:
                            cross_branch_stats[key] = {'count': 0, 'total_weight': 0}
                        cross_branch_stats[key]['count'] += 1
                        cross_branch_stats[key]['total_weight'] += weight

    # 4. Tag propagation (if requested)
    proposed_tags = []
    if propagate_tags:
        # Get all unique tags
        cur.execute('SELECT DISTINCT tag FROM tags WHERE tenant_id = %s', (get_tenant_id(),))
        all_tags = [row['tag'] for row in cur.fetchall()]

        for tag in all_tags[:20]:  # Limit to 20 tags
            # Get blobs with this tag
            cur.execute('''
                SELECT b.blob_hash, b.embedding
                FROM blobs b
                JOIN tags t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
                WHERE t.tag = %s AND b.embedding IS NOT NULL AND b.tenant_id = %s
            ''', (tag, get_tenant_id()))
            tagged_blobs = [{'hash': r['blob_hash'], 'embedding': r['embedding']} for r in cur.fetchall()]

            if not tagged_blobs:
                continue

            # Get blobs without this tag
            cur.execute('''
                SELECT blob_hash, embedding
                FROM blobs
                WHERE embedding IS NOT NULL AND tenant_id = %s
                AND blob_hash NOT IN (SELECT blob_hash FROM tags WHERE tag = %s AND tenant_id = %s)
                LIMIT 100
            ''', (get_tenant_id(), tag, get_tenant_id()))
            untagged_blobs = [{'hash': r['blob_hash'], 'embedding': r['embedding']} for r in cur.fetchall()]

            for untagged in untagged_blobs:
                if len(proposed_tags) >= 50:  # Cap tag propagations
                    break
                for tagged in tagged_blobs:
                    try:
                        emb_a = np.array(tagged['embedding'])
                        emb_b = np.array(untagged['embedding'])
                        cos_sim = np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b))
                        distance = 1 - cos_sim
                    except Exception:
                        continue

                    if distance < tag_threshold:
                        proposed_tags.append({
                            'tag': tag,
                            'blob_hash': untagged['hash'],
                            'distance': float(round(distance, 4)),
                            'reason': f"Similar to {tagged['hash'][:8]}..."
                        })
                        break  # One match is enough

    # 5. Execute if not dry_run
    created_links = 0
    created_tags = 0

    if not dry_run:
        now = datetime.utcnow().isoformat() + 'Z'

        for link in proposed_links:
            try:
                cur.execute('''
                    INSERT INTO cross_references
                    (tenant_id, source_blob, target_blob, source_branch, target_branch,
                     link_type, weight, reasoning, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    get_tenant_id(), link['source'], link['target'],
                    link['source_branch'], link['target_branch'],
                    'resonance', link['weight'], link['reasoning'], now
                ))
                created_links += 1
            except Exception as e:
                print(f"[ANALYZE] Link creation failed: {e}", file=sys.stderr)
                continue

        for tag_prop in proposed_tags:
            try:
                cur.execute('''
                    INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
                    VALUES (%s, %s, %s, %s)
                ''', (get_tenant_id(), tag_prop['blob_hash'], tag_prop['tag'], now))
                created_tags += 1
            except Exception:
                continue  # Tag might already exist

        db.commit()

    cur.close()

    # Format cross-branch insights
    cross_branch_insights = [
        {
            'branches': list(key),
            'link_count': stats['count'],
            'avg_weight': float(round(stats['total_weight'] / stats['count'], 2))
        }
        for key, stats in sorted(cross_branch_stats.items(), key=lambda x: x[1]['count'], reverse=True)
    ]

    return jsonify({
        'status': 'executed' if not dry_run else 'analyzed',
        'dry_run': dry_run,
        'stats': {
            'total_blobs': len(blobs),
            'blobs_with_embeddings': len(blobs),
            'existing_links': len(existing_links) // 2,  # Divide by 2 since we added both directions
            'proposed_links': len(proposed_links),
            'created_links': created_links,
            'proposed_tags': len(proposed_tags),
            'created_tags': created_tags
        },
        'links_preview': proposed_links[:50],  # Preview first 50
        'tags_preview': proposed_tags[:20] if propagate_tags else [],
        'cross_branch_insights': cross_branch_insights,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


@app.route('/v2/links/cleanup', methods=['POST'])
def cleanup_links():
    """
    Delete links with 'unknown' branches created by analyzer bug.

    Request body (JSON):
    - dry_run: bool (default True) - if True, preview what would be deleted
    """
    data = request.get_json() or {}
    dry_run = data.get('dry_run', True)

    db = get_db()
    cur = get_cursor()

    # Count links to delete
    cur.execute('''
        SELECT COUNT(*) as count FROM cross_references
        WHERE (source_branch = 'unknown' OR target_branch = 'unknown')
        AND tenant_id = %s
    ''', (get_tenant_id(),))
    count = cur.fetchone()['count']

    deleted = 0
    if not dry_run and count > 0:
        cur.execute('''
            DELETE FROM cross_references
            WHERE (source_branch = 'unknown' OR target_branch = 'unknown')
            AND tenant_id = %s
        ''', (get_tenant_id(),))
        deleted = cur.rowcount
        db.commit()

    cur.close()

    return jsonify({
        'status': 'executed' if not dry_run else 'preview',
        'dry_run': dry_run,
        'unknown_links_found': count,
        'deleted': deleted,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


@app.route('/v2/links/debug-branch', methods=['POST'])
def debug_branch_detection():
    """Debug branch detection for a specific blob."""
    data = request.get_json() or {}
    blob_hash = data.get('blob_hash')

    if not blob_hash:
        # Pick a random blob with embedding
        cur = get_cursor()
        cur.execute('''
            SELECT blob_hash FROM blobs
            WHERE embedding IS NOT NULL AND tenant_id = %s
            LIMIT 1
        ''', (get_tenant_id(),))
        row = cur.fetchone()
        blob_hash = row['blob_hash'] if row else None
        cur.close()

    if not blob_hash:
        return jsonify({'error': 'No blob found'}), 404

    cur = get_cursor()
    debug_info = {'blob_hash': blob_hash}

    # Step 1: Check if blob exists
    cur.execute('SELECT blob_hash FROM blobs WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, get_tenant_id()))
    debug_info['blob_exists'] = cur.fetchone() is not None

    # Step 2: Check tree_entries for this blob
    cur.execute('SELECT tree_hash, name FROM tree_entries WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, get_tenant_id()))
    tree_entries = cur.fetchall()
    debug_info['tree_entries'] = [{'tree_hash': r['tree_hash'], 'name': r['name']} for r in tree_entries]

    # Step 3: For each tree_entry, find the commit
    commits_found = []
    for te in tree_entries:
        cur.execute('SELECT commit_hash, message FROM commits WHERE tree_hash = %s AND tenant_id = %s', (te['tree_hash'], get_tenant_id()))
        commits = cur.fetchall()
        for c in commits:
            commits_found.append({'tree_hash': te['tree_hash'], 'commit_hash': c['commit_hash'], 'message': c['message'][:50]})
    debug_info['commits_found'] = commits_found

    # Step 4: Check branch heads
    cur.execute('SELECT name, head_commit FROM branches WHERE tenant_id = %s', (get_tenant_id(),))
    branches = [{'name': r['name'], 'head_commit': r['head_commit']} for r in cur.fetchall()]
    debug_info['branches'] = branches

    # Step 5: Run the actual get_blob_branch function
    debug_info['detected_branch'] = get_blob_branch(cur, blob_hash, get_tenant_id())

    cur.close()
    return jsonify(debug_info)


# ==================== EMBEDDINGS ====================

@app.route('/v2/embeddings/backfill', methods=['POST'])
def backfill_embeddings():
    """Generate embeddings for all blobs that don't have them."""
    if not OPENAI_API_KEY:
        return jsonify({'error': 'OpenAI API key not configured'}), 500
    
    limit = request.args.get('limit', 100, type=int)
    db = get_db()
    cur = get_cursor()
    
    # Find blobs without embeddings
    cur.execute('''
        SELECT blob_hash, content FROM blobs 
        WHERE tenant_id = %s AND embedding IS NULL
        LIMIT %s
    ''', (get_tenant_id(), limit))
    
    blobs = cur.fetchall()
    processed = 0
    failed = 0
    errors = []
    
    for blob in blobs:
        blob_hash = blob['blob_hash']
        content = blob['content']
        
        embedding = generate_embedding(content)
        if embedding:
            try:
                cur.execute(
                    '''UPDATE blobs SET embedding = %s WHERE blob_hash = %s AND tenant_id = %s''',
                    (embedding, blob_hash, get_tenant_id())
                )
                processed += 1
            except Exception as e:
                print(f"[BACKFILL] Failed to store embedding for {blob_hash}: {e}", file=sys.stderr)
                errors.append(f"store:{blob_hash[:8]}:{str(e)[:50]}")
                failed += 1
        else:
            errors.append(f"generate:{blob_hash[:8]}:embedding returned None")
            failed += 1
    
    db.commit()
    cur.close()
    
    # Check how many still need processing
    cur2 = get_cursor()
    cur2.execute('SELECT COUNT(*) as remaining FROM blobs WHERE tenant_id = %s AND embedding IS NULL', (get_tenant_id(),))
    remaining = cur2.fetchone()['remaining']
    cur2.close()
    
    return jsonify({
        'status': 'completed',
        'processed': processed,
        'failed': failed,
        'remaining': remaining,
        'errors': errors[:10],
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

@app.route('/v2/embeddings/status', methods=['GET'])
def embeddings_status():
    """Check embedding coverage."""
    cur = get_cursor()
    cur.execute('''
        SELECT 
            COUNT(*) as total_blobs,
            COUNT(embedding) as with_embedding,
            COUNT(*) - COUNT(embedding) as without_embedding
        FROM blobs WHERE tenant_id = %s
    ''', (get_tenant_id(),))
    row = cur.fetchone()
    cur.close()
    
    return jsonify({
        'total_blobs': row['total_blobs'],
        'with_embedding': row['with_embedding'],
        'without_embedding': row['without_embedding'],
        'coverage_pct': round(100 * row['with_embedding'] / row['total_blobs'], 2) if row['total_blobs'] > 0 else 0,
        'openai_configured': bool(OPENAI_API_KEY),
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

# ==================== SESSIONS ====================

@app.route('/v2/sync', methods=['POST'])
def sync_session():
    """Session sync from Command Center (v1 compatible)."""
    data = request.get_json() or {}
    session_id = data.get('session_id')
    project = data.get('project', 'command-center')
    content = data.get('content', {})
    summary = data.get('summary', '')

    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400

    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'
    branch = get_branch_for_project(project)
    content_str = json.dumps(content) if isinstance(content, dict) else str(content)

    # Upsert session
    cur.execute(
        '''INSERT INTO sessions (session_id, tenant_id, branch, content, summary, synced_at, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (session_id) DO UPDATE SET
               content = EXCLUDED.content,
               summary = EXCLUDED.summary,
               synced_at = EXCLUDED.synced_at,
               status = EXCLUDED.status''',
        (session_id, get_tenant_id(), branch, content_str, summary, now, 'synced')
    )
    db.commit()
    cur.close()

    return jsonify({
        'status': 'synced',
        'session_id': session_id,
        'branch': branch,
        'synced_at': now
    })

@app.route('/v2/sessions', methods=['GET'])
def list_sessions():
    """List synced sessions."""
    branch = request.args.get('branch')
    status = request.args.get('status')
    limit = request.args.get('limit', 20, type=int)

    cur = get_cursor()

    sql = 'SELECT * FROM sessions WHERE tenant_id = %s'
    params = [get_tenant_id()]

    if branch:
        sql += ' AND branch = %s'
        params.append(branch)

    if status:
        sql += ' AND status = %s'
        params.append(status)

    sql += ' ORDER BY synced_at DESC LIMIT %s'
    params.append(limit)

    cur.execute(sql, params)
    sessions = []
    for row in cur.fetchall():
        r = dict(row)
        if r.get('synced_at'):
            r['synced_at'] = str(r['synced_at'])
        sessions.append(r)

    cur.close()
    return jsonify({'sessions': sessions, 'count': len(sessions)})

# ==================== AUDIT LOGGING (Phase 3) ====================

@app.route('/v2/audit', methods=['GET'])
def query_audit():
    """Query audit logs with filtering."""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    action = request.args.get('action')
    resource_type = request.args.get('resource_type')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    status_min = request.args.get('status_min', type=int)

    cur = get_cursor()

    try:
        from audit_service import query_audit_logs
        filters = {}
        if action:
            filters['action'] = action
        if resource_type:
            filters['resource_type'] = resource_type
        if start_time:
            filters['start_time'] = start_time
        if end_time:
            filters['end_time'] = end_time
        if status_min:
            filters['status_min'] = status_min

        rows = query_audit_logs(cur, get_tenant_id(), filters, limit, offset)
        logs = []
        for row in rows:
            logs.append({
                'id': str(row['id']),
                'timestamp': str(row['timestamp']),
                'action': row['action'],
                'resource_type': row['resource_type'],
                'resource_id': row['resource_id'],
                'response_status': row['response_status'],
                'duration_ms': row['duration_ms'],
                'request_metadata': row['request_metadata']
            })
        cur.close()
        return jsonify({
            'logs': logs,
            'count': len(logs),
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500

@app.route('/v2/audit/stats', methods=['GET'])
def audit_stats():
    """Get audit statistics."""
    hours = request.args.get('hours', 24, type=int)

    cur = get_cursor()

    try:
        from audit_service import get_audit_stats
        stats = get_audit_stats(cur, get_tenant_id(), hours)
        cur.close()

        if stats:
            return jsonify({
                'period_hours': hours,
                'total_requests': stats['total_requests'] or 0,
                'error_count': stats['error_count'] or 0,
                'avg_duration_ms': stats['avg_duration_ms'] or 0,
                'max_duration_ms': stats['max_duration_ms'] or 0,
                'unique_actions': stats['unique_actions'] or 0,
                'error_rate': round((stats['error_count'] or 0) / max(stats['total_requests'] or 1, 1) * 100, 2)
            })
        return jsonify({
            'period_hours': hours,
            'total_requests': 0,
            'error_count': 0,
            'avg_duration_ms': 0,
            'max_duration_ms': 0,
            'unique_actions': 0,
            'error_rate': 0
        })
    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500

# ==================== ADMIN API (God Mode Dashboard) ====================

@app.route('/v2/admin/pulse', methods=['GET'])
def admin_pulse():
    """Get all stats for the Pulse view - system overview."""
    cur = get_cursor()

    try:
        # Count tenants
        cur.execute('SELECT COUNT(*) as count FROM tenants')
        tenant_count = cur.fetchone()['count']

        # Count commits
        cur.execute('SELECT COUNT(*) as count FROM commits WHERE tenant_id = %s', (get_tenant_id(),))
        commit_count = cur.fetchone()['count']

        # Count blobs
        cur.execute('SELECT COUNT(*) as count FROM blobs WHERE tenant_id = %s', (get_tenant_id(),))
        blob_count = cur.fetchone()['count']

        # Total storage
        cur.execute('SELECT COALESCE(SUM(byte_size), 0) as total FROM blobs WHERE tenant_id = %s', (get_tenant_id(),))
        total_storage = cur.fetchone()['total']

        # API calls in last 24h
        cur.execute('''
            SELECT COUNT(*) as count FROM audit_logs
            WHERE tenant_id = %s AND timestamp > NOW() - INTERVAL '24 hours'
        ''', (get_tenant_id(),))
        api_calls_24h = cur.fetchone()['count']

        # Request volume by day (last 7 days)
        cur.execute('''
            SELECT DATE(timestamp) as day, COUNT(*) as requests
            FROM audit_logs
            WHERE tenant_id = %s AND timestamp > NOW() - INTERVAL '7 days'
            GROUP BY DATE(timestamp)
            ORDER BY day
        ''', (get_tenant_id(),))
        request_volume = [{'day': str(row['day']), 'requests': row['requests']} for row in cur.fetchall()]

        # Error rate by day (last 7 days)
        cur.execute('''
            SELECT DATE(timestamp) as day,
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE response_status >= 400) as errors
            FROM audit_logs
            WHERE tenant_id = %s AND timestamp > NOW() - INTERVAL '7 days'
            GROUP BY DATE(timestamp)
            ORDER BY day
        ''', (get_tenant_id(),))
        error_rates = []
        for row in cur.fetchall():
            error_rate = round((row['errors'] / max(row['total'], 1)) * 100, 2)
            error_rates.append({'day': str(row['day']), 'error_rate': error_rate, 'errors': row['errors']})

        # Response time percentiles (last 24h)
        cur.execute('''
            SELECT
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms) as p50,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms) as p99,
                AVG(duration_ms) as avg
            FROM audit_logs
            WHERE tenant_id = %s AND timestamp > NOW() - INTERVAL '24 hours'
        ''', (get_tenant_id(),))
        perf_row = cur.fetchone()
        response_times = {
            'p50': round(perf_row['p50'] or 0, 1),
            'p95': round(perf_row['p95'] or 0, 1),
            'p99': round(perf_row['p99'] or 0, 1),
            'avg': round(perf_row['avg'] or 0, 1)
        }

        # System status
        cur.execute('SELECT COUNT(*) FILTER (WHERE response_status >= 500) as errors FROM audit_logs WHERE timestamp > NOW() - INTERVAL \'15 minutes\'')
        recent_500s = cur.fetchone()['errors']
        system_health = 'healthy' if recent_500s == 0 else 'degraded'

        cur.close()

        return jsonify({
            'cards': {
                'total_tenants': tenant_count,
                'total_commits': commit_count,
                'total_blobs': blob_count,
                'api_calls_24h': api_calls_24h,
                'total_storage_bytes': total_storage
            },
            'charts': {
                'request_volume': request_volume,
                'error_rates': error_rates,
                'response_times': response_times
            },
            'status': {
                'system_health': system_health,
                'recent_500_errors': recent_500s,
                'storage_bytes': total_storage,
                'encryption': 'enabled' if ENCRYPTION_ENABLED else 'disabled',
                'audit': 'enabled' if AUDIT_ENABLED else 'disabled'
            },
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/admin/tenants', methods=['GET'])
def admin_tenants():
    """List all tenants with aggregate stats."""
    cur = get_cursor()

    try:
        cur.execute('''
            SELECT
                t.id,
                t.name,
                t.created_at,
                (SELECT COUNT(*) FROM commits c WHERE c.tenant_id = t.id) as commit_count,
                (SELECT COUNT(*) FROM blobs b WHERE b.tenant_id = t.id) as blob_count,
                (SELECT COALESCE(SUM(byte_size), 0) FROM blobs b WHERE b.tenant_id = t.id) as storage_bytes,
                (SELECT COUNT(*) FROM audit_logs a WHERE a.tenant_id = t.id AND a.timestamp > NOW() - INTERVAL '7 days') as api_calls_7d,
                (SELECT MAX(timestamp) FROM audit_logs a WHERE a.tenant_id = t.id) as last_active
            FROM tenants t
            ORDER BY t.created_at DESC
        ''')

        tenants = []
        for row in cur.fetchall():
            tenants.append({
                'id': str(row['id']),
                'name': row['name'],
                'created_at': str(row['created_at']) if row['created_at'] else None,
                'commit_count': row['commit_count'],
                'blob_count': row['blob_count'],
                'storage_bytes': row['storage_bytes'],
                'api_calls_7d': row['api_calls_7d'],
                'last_active': str(row['last_active']) if row['last_active'] else None
            })

        cur.close()
        return jsonify({
            'tenants': tenants,
            'count': len(tenants)
        })

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/admin/tenants/<tenant_id>', methods=['GET'])
def admin_tenant_detail(tenant_id):
    """Get detailed stats for a specific tenant."""
    cur = get_cursor()

    try:
        # Basic tenant info
        cur.execute('SELECT * FROM tenants WHERE id = %s', (tenant_id,))
        tenant = cur.fetchone()
        if not tenant:
            cur.close()
            return jsonify({'error': 'Tenant not found'}), 404

        # Commits by branch
        cur.execute('''
            SELECT br.name as branch, COUNT(c.commit_hash) as commits
            FROM branches br
            LEFT JOIN commits c ON c.tenant_id = br.tenant_id
            WHERE br.tenant_id = %s
            GROUP BY br.name
            ORDER BY commits DESC
        ''', (tenant_id,))
        commits_by_branch = [{'branch': row['branch'], 'commits': row['commits']} for row in cur.fetchall()]

        # API calls by day (last 30 days)
        cur.execute('''
            SELECT DATE(timestamp) as day, COUNT(*) as requests
            FROM audit_logs
            WHERE tenant_id = %s AND timestamp > NOW() - INTERVAL '30 days'
            GROUP BY DATE(timestamp)
            ORDER BY day
        ''', (tenant_id,))
        api_calls_by_day = [{'day': str(row['day']), 'requests': row['requests']} for row in cur.fetchall()]

        # Top actions
        cur.execute('''
            SELECT action, COUNT(*) as count
            FROM audit_logs
            WHERE tenant_id = %s AND timestamp > NOW() - INTERVAL '7 days'
            GROUP BY action
            ORDER BY count DESC
            LIMIT 10
        ''', (tenant_id,))
        top_actions = [{'action': row['action'], 'count': row['count']} for row in cur.fetchall()]

        cur.close()
        return jsonify({
            'tenant': {
                'id': str(tenant['id']),
                'name': tenant['name'],
                'created_at': str(tenant['created_at']) if tenant['created_at'] else None
            },
            'charts': {
                'commits_by_branch': commits_by_branch,
                'api_calls_by_day': api_calls_by_day,
                'top_actions': top_actions
            }
        })

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/admin/create-tenant', methods=['POST'])
def admin_create_tenant():
    """
    Create a new tenant with auto-generated credentials.
    Secured with GODMODE_PASSWORD header.

    Request:
        Headers: X-Godmode-Password: <password>
        Body: { "name": "Tenant Name", "email": "contact@email.com" }

    Response:
        { "tenant_id": "uuid", "api_key": "key", "name": "...", "created_at": "..." }
    """
    import uuid
    import secrets

    # Security check
    godmode_password = os.environ.get('GODMODE_PASSWORD')
    provided_password = request.headers.get('X-Godmode-Password')

    if not godmode_password:
        return jsonify({'error': 'Server not configured for tenant provisioning'}), 503

    if not provided_password or provided_password != godmode_password:
        return jsonify({'error': 'Unauthorized'}), 401

    # Parse request
    data = request.get_json() or {}
    tenant_name = data.get('name')
    tenant_email = data.get('email')

    if not tenant_name:
        return jsonify({'error': 'name is required'}), 400

    # Generate credentials
    tenant_id = str(uuid.uuid4())
    api_key = f"bos_{secrets.token_urlsafe(32)}"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    db = get_db()
    cur = get_cursor()

    try:
        # Insert tenant
        cur.execute(
            '''INSERT INTO tenants (id, name, created_at)
               VALUES (%s, %s, NOW())
               RETURNING id, name, created_at''',
            (tenant_id, tenant_name)
        )
        tenant_row = cur.fetchone()

        # Store API key hash (we return the actual key only once)
        # Note: api_keys table may not exist yet - use savepoint to handle gracefully
        api_key_stored = False
        try:
            cur.execute('SAVEPOINT api_key_insert')
            cur.execute(
                '''INSERT INTO api_keys (tenant_id, key_hash, name, created_at)
                   VALUES (%s, %s, %s, NOW())''',
                (tenant_id, api_key_hash, f"Default key for {tenant_name}")
            )
            cur.execute('RELEASE SAVEPOINT api_key_insert')
            api_key_stored = True
        except Exception as key_err:
            # Table might not exist yet - rollback savepoint and continue
            cur.execute('ROLLBACK TO SAVEPOINT api_key_insert')
            print(f"[WARN] Could not store API key hash: {key_err}", file=sys.stderr)

        # Create default branches for new tenant
        default_branches = ['main', 'command-center']
        for branch_name in default_branches:
            cur.execute(
                '''INSERT INTO branches (tenant_id, name, head_commit)
                   VALUES (%s, %s, NULL)
                   ON CONFLICT DO NOTHING''',
                (tenant_id, branch_name)
            )

        db.commit()
        cur.close()

        return jsonify({
            'status': 'created',
            'tenant_id': tenant_id,
            'api_key': api_key,  # Only returned once!
            'name': tenant_row['name'],
            'email': tenant_email,
            'created_at': str(tenant_row['created_at']),
            'branches': default_branches,
            'warning': 'Save your API key now - it cannot be retrieved again!'
        }), 201

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/admin/alerts', methods=['GET'])
def admin_alerts():
    """Get computed alerts for the system."""
    cur = get_cursor()
    alerts = []

    try:
        # Alert 1: Error rate above 5% in last hour
        cur.execute('''
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE response_status >= 400) as errors
            FROM audit_logs
            WHERE timestamp > NOW() - INTERVAL '1 hour'
        ''')
        row = cur.fetchone()
        if row['total'] > 0:
            error_rate = (row['errors'] / row['total']) * 100
            if error_rate > 5:
                alerts.append({
                    'severity': 'warning',
                    'type': 'error_rate',
                    'message': f'Error rate is {error_rate:.1f}% in the last hour',
                    'details': {'total': row['total'], 'errors': row['errors'], 'rate': round(error_rate, 2)}
                })

        # Alert 2: Any 500 errors in last 15 minutes
        cur.execute('''
            SELECT COUNT(*) as count
            FROM audit_logs
            WHERE response_status >= 500 AND timestamp > NOW() - INTERVAL '15 minutes'
        ''')
        recent_500s = cur.fetchone()['count']
        if recent_500s > 0:
            alerts.append({
                'severity': 'critical',
                'type': 'server_errors',
                'message': f'{recent_500s} server errors in the last 15 minutes',
                'details': {'count': recent_500s}
            })

        # Alert 3: Tenant storage above 80% (need to define limits per tenant - using 100MB as example)
        storage_limit = 100 * 1024 * 1024  # 100MB
        cur.execute('''
            SELECT t.id, t.name, COALESCE(SUM(b.byte_size), 0) as storage
            FROM tenants t
            LEFT JOIN blobs b ON b.tenant_id = t.id
            GROUP BY t.id, t.name
            HAVING COALESCE(SUM(b.byte_size), 0) > %s
        ''', (storage_limit * 0.8,))
        for row in cur.fetchall():
            usage_pct = (row['storage'] / storage_limit) * 100
            alerts.append({
                'severity': 'warning',
                'type': 'storage_warning',
                'message': f'Tenant "{row["name"]}" using {usage_pct:.0f}% of storage limit',
                'details': {'tenant_id': str(row['id']), 'storage_bytes': row['storage'], 'limit_bytes': storage_limit}
            })

        # Alert 4: Tenants inactive 30+ days
        cur.execute('''
            SELECT t.id, t.name,
                   (SELECT MAX(timestamp) FROM audit_logs a WHERE a.tenant_id = t.id) as last_active
            FROM tenants t
            WHERE (SELECT MAX(timestamp) FROM audit_logs a WHERE a.tenant_id = t.id) < NOW() - INTERVAL '30 days'
               OR (SELECT MAX(timestamp) FROM audit_logs a WHERE a.tenant_id = t.id) IS NULL
        ''')
        for row in cur.fetchall():
            alerts.append({
                'severity': 'info',
                'type': 'inactive_tenant',
                'message': f'Tenant "{row["name"]}" inactive for 30+ days',
                'details': {'tenant_id': str(row['id']), 'last_active': str(row['last_active']) if row['last_active'] else 'never'}
            })

        # Alert 5: High response time (p95 > 500ms)
        cur.execute('''
            SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95
            FROM audit_logs
            WHERE timestamp > NOW() - INTERVAL '1 hour'
        ''')
        p95_row = cur.fetchone()
        if p95_row['p95'] and p95_row['p95'] > 500:
            alerts.append({
                'severity': 'warning',
                'type': 'slow_responses',
                'message': f'P95 response time is {p95_row["p95"]:.0f}ms (last hour)',
                'details': {'p95_ms': round(p95_row['p95'], 1)}
            })

        cur.close()

        # Sort by severity
        severity_order = {'critical': 0, 'warning': 1, 'info': 2}
        alerts.sort(key=lambda x: severity_order.get(x['severity'], 99))

        return jsonify({
            'alerts': alerts,
            'count': len(alerts),
            'critical_count': sum(1 for a in alerts if a['severity'] == 'critical'),
            'warning_count': sum(1 for a in alerts if a['severity'] == 'warning'),
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


# ==================== TASK QUEUE (Multi-Agent Coordination) ====================

@app.route('/v2/tasks', methods=['POST'])
def create_task():
    """Create a new task for agent coordination.
    
    Also creates a memory commit to make the task discoverable via semantic search.
    """
    data = request.get_json() or {}
    description = data.get('description')
    title = data.get('title')
    branch = data.get('branch', 'command-center')
    assigned_to = data.get('assigned_to')
    priority = data.get('priority', 5)
    deadline = data.get('deadline')
    metadata = data.get('metadata', {})
    plan_blob_hash = data.get('plan_blob_hash')

    if not description:
        return jsonify({'error': 'Description required'}), 400

    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'

    try:
        # Ensure work hierarchy columns exist (idempotent)
        try:
            cur.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS title VARCHAR(500)')
            cur.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS plan_blob_hash TEXT')
            db.commit()
        except Exception:
            db.rollback()

        # Validate plan_blob_hash references an existing blob
        if plan_blob_hash:
            cur.execute(
                'SELECT blob_hash FROM blobs WHERE blob_hash = %s AND tenant_id = %s',
                (plan_blob_hash, get_tenant_id())
            )
            if not cur.fetchone():
                cur.close()
                return jsonify({'error': f'plan_blob_hash {plan_blob_hash} does not reference an existing blob'}), 400

        # 1. Insert task into task queue
        cur.execute(
            '''INSERT INTO tasks (tenant_id, description, title, branch, assigned_to, status, priority, deadline, metadata, plan_blob_hash)
               VALUES (%s, %s, %s, %s, %s, 'open', %s, %s, %s, %s)
               RETURNING id, created_at''',
            (get_tenant_id(), description, title, branch, assigned_to, priority, deadline, json.dumps(metadata), plan_blob_hash)
        )
        row = cur.fetchone()
        task_id = str(row['id'])
        created_at = str(row['created_at'])

        # 2. Create memory commit for discoverability
        memory_content = {
            'type': 'task_created',
            'task_id': task_id,
            'title': title,
            'description': description,
            'branch': branch,
            'priority': priority,
            'assigned_to': assigned_to,
            'plan_blob_hash': plan_blob_hash,
            'metadata': metadata
        }
        content_str = json.dumps(memory_content)
        blob_hash = compute_hash(content_str)

        # Insert blob
        cur.execute(
            '''INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (blob_hash) DO NOTHING''',
            (blob_hash, get_tenant_id(), content_str, 'task', now, len(content_str))
        )

        # Link task to blob for unified lookup
        cur.execute(
            '''UPDATE tasks SET blob_hash = %s WHERE id = %s AND tenant_id = %s''',
            (blob_hash, task_id, get_tenant_id())
        )

        # Generate embedding for semantic search
        embedding = generate_embedding(content_str)
        if embedding:
            try:
                cur.execute(
                    '''UPDATE blobs SET embedding = %s WHERE blob_hash = %s AND tenant_id = %s''',
                    (embedding, blob_hash, get_tenant_id())
                )
            except Exception as e:
                print(f"[TASK] Failed to store embedding: {e}", file=sys.stderr)

        # Create tree entry
        tree_hash = compute_hash(f"{branch}:{blob_hash}:{now}")
        message = f"TASK: {description[:80]}{'...' if len(description) > 80 else ''}"
        cur.execute(
            '''INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
               VALUES (%s, %s, %s, %s, %s)''',
            (get_tenant_id(), tree_hash, message[:100], blob_hash, 'task')
        )

        # Get parent commit (case-insensitive branch lookup)
        cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', (branch, get_tenant_id()))
        branch_row = cur.fetchone()
        if branch_row:
            branch = branch_row['name']  # Use canonical casing
            parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
        else:
            # Auto-create branch
            cur.execute(
                '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
                   VALUES (%s, %s, %s, %s)''',
                (get_tenant_id(), branch, 'GENESIS', now)
            )
            parent_hash = None

        # Create commit
        commit_data = f"{tree_hash}:{parent_hash}:{message}:{now}"
        commit_hash = compute_hash(commit_data)

        cur.execute(
            '''INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (commit_hash, get_tenant_id(), tree_hash, parent_hash, 'task-system', message, now)
        )

        # Update branch head
        cur.execute(
            'UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s',
            (commit_hash, branch, get_tenant_id())
        )

        # Add task_id tag for easy lookup
        cur.execute(
            '''INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
               VALUES (%s, %s, %s, %s)''',
            (get_tenant_id(), blob_hash, f"task:{task_id}", now)
        )

        db.commit()
        cur.close()

        response = {
            'status': 'created',
            'task_id': task_id,
            'commit_hash': commit_hash,
            'blob_hash': blob_hash,
            'title': title,
            'description': description,
            'branch': branch,
            'assigned_to': assigned_to,
            'priority': priority,
            'created_at': created_at
        }
        if plan_blob_hash:
            response['plan_blob_hash'] = plan_blob_hash
        return jsonify(response), 201

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/tasks', methods=['GET'])
def list_tasks():
    """List tasks with optional filtering."""
    status = request.args.get('status')
    branch = request.args.get('branch')
    assigned_to = request.args.get('assigned_to')
    limit = request.args.get('limit', 50, type=int)

    cur = get_cursor()

    sql = 'SELECT * FROM tasks WHERE tenant_id = %s'
    params = [get_tenant_id()]

    if status:
        sql += ' AND status = %s'
        params.append(status)

    if branch:
        sql += ' AND branch = %s'
        params.append(branch)

    if assigned_to:
        sql += ' AND assigned_to = %s'
        params.append(assigned_to)

    sql += ' ORDER BY priority ASC, created_at ASC LIMIT %s'
    params.append(limit)

    cur.execute(sql, params)
    tasks = []
    for row in cur.fetchall():
        task = dict(row)
        task['id'] = str(task['id'])
        task['tenant_id'] = str(task['tenant_id'])
        if task.get('created_at'):
            task['created_at'] = str(task['created_at'])
        if task.get('updated_at'):
            task['updated_at'] = str(task['updated_at'])
        if task.get('deadline'):
            task['deadline'] = str(task['deadline'])
        tasks.append(task)

    cur.close()
    return jsonify({'tasks': tasks, 'count': len(tasks)})


@app.route('/v2/tasks/<task_id>', methods=['PATCH'])
def update_task(task_id):
    """Update a task's fields."""
    data = request.get_json() or {}

    # Allowed fields to update
    allowed_fields = ['description', 'title', 'branch', 'assigned_to', 'status', 'priority', 'deadline', 'metadata', 'plan_blob_hash']
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if not updates:
        return jsonify({'error': 'No valid fields to update'}), 400

    # Validate status if provided
    if 'status' in updates:
        valid_statuses = ['open', 'claimed', 'blocked', 'done']
        if updates['status'] not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {valid_statuses}'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        # Build dynamic UPDATE query
        set_clauses = []
        params = []
        for field, value in updates.items():
            if field == 'metadata':
                set_clauses.append(f'{field} = %s')
                params.append(json.dumps(value))
            else:
                set_clauses.append(f'{field} = %s')
                params.append(value)

        params.extend([task_id, get_tenant_id()])

        sql = f'''UPDATE tasks SET {', '.join(set_clauses)}
                  WHERE id = %s AND tenant_id = %s
                  RETURNING *'''

        cur.execute(sql, params)
        row = cur.fetchone()

        if not row:
            cur.close()
            return jsonify({'error': 'Task not found'}), 404

        # Auto-clear checkpoint when task is marked done
        if updates.get('status') == 'done':
            try:
                cur.execute(
                    'DELETE FROM session_checkpoints WHERE task_id = %s AND tenant_id = %s',
                    (task_id, get_tenant_id())
                )
            except Exception as e:
                # Table may not exist yet - non-fatal
                print(f"[CHECKPOINT] Auto-clear skipped: {e}", file=sys.stderr)

        db.commit()

        task = dict(row)
        task['id'] = str(task['id'])
        task['tenant_id'] = str(task['tenant_id'])
        if task.get('created_at'):
            task['created_at'] = str(task['created_at'])
        if task.get('updated_at'):
            task['updated_at'] = str(task['updated_at'])
        if task.get('deadline'):
            task['deadline'] = str(task['deadline'])

        cur.close()
        return jsonify({'status': 'updated', 'task': task})

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """Soft delete a task by setting status to 'deleted'."""
    db = get_db()
    cur = get_cursor()

    try:
        cur.execute(
            '''UPDATE tasks SET status = 'deleted'
               WHERE id = %s AND tenant_id = %s
               RETURNING id, description, status''',
            (task_id, get_tenant_id())
        )
        row = cur.fetchone()

        if not row:
            cur.close()
            return jsonify({'error': 'Task not found'}), 404

        db.commit()
        cur.close()

        return jsonify({
            'status': 'deleted',
            'task_id': str(row['id']),
            'description': row['description']
        })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/tasks/landscape', methods=['GET'])
def work_landscape():
    """Return the full work landscape — branches as projects, plans with progress,
    cascade health scores, and unorganized backlog.

    Query params:
      - branch: filter by branch (optional)
      - include_done: include completed plans (default: false)
    """
    filter_branch = request.args.get('branch')
    include_done = request.args.get('include_done', 'false').lower() == 'true'
    tenant_id = get_tenant_id()

    cur = get_cursor()
    landscape = {}
    backlog = []

    try:
        # 1. Get active plans (blobs with content_type='plan')
        plan_status_filter = "AND (b.content::jsonb->>'status') IN ('active', 'paused')"
        if include_done:
            plan_status_filter = ""

        plan_sql = f"""
            SELECT b.blob_hash, b.content, b.created_at,
                   c.message AS commit_message,
                   br.name AS branch_name
            FROM blobs b
            JOIN tree_entries te ON te.blob_hash = b.blob_hash AND te.tenant_id = b.tenant_id
            JOIN commits co ON co.tree_hash = te.tree_hash AND co.tenant_id = b.tenant_id
            JOIN branches br ON br.head_commit IS NOT NULL AND br.tenant_id = b.tenant_id
            WHERE b.tenant_id = %s
              AND b.content_type = 'plan'
              {plan_status_filter}
        """
        params = [tenant_id]
        if filter_branch:
            plan_sql += " AND LOWER(br.name) = LOWER(%s)"
            params.append(filter_branch)

        # Simpler approach: query plans from blobs directly, get branch from commit chain
        plan_sql = f"""
            SELECT DISTINCT b.blob_hash, b.content, b.created_at
            FROM blobs b
            WHERE b.tenant_id = %s
              AND b.content_type = 'plan'
              {plan_status_filter}
            ORDER BY b.created_at DESC
        """
        params = [tenant_id]
        cur.execute(plan_sql, params)
        plan_rows = cur.fetchall()

        plans_by_branch = {}
        plan_hashes = set()

        for row in plan_rows:
            content = row['content']
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    content = {}

            blob_hash = row['blob_hash']
            plan_hashes.add(blob_hash)
            plan_title = content.get('title', 'Untitled Plan')
            plan_status = content.get('status', 'active')

            # Get branch from the commit that contains this blob
            cur.execute("""
                SELECT br.name
                FROM tree_entries te
                JOIN commits co ON co.tree_hash = te.tree_hash AND co.tenant_id = te.tenant_id
                JOIN branches br ON br.tenant_id = co.tenant_id
                WHERE te.blob_hash = %s AND te.tenant_id = %s
                LIMIT 1
            """, (blob_hash, tenant_id))
            branch_row = cur.fetchone()
            plan_branch = branch_row['name'] if branch_row else 'unknown'

            if filter_branch and plan_branch.lower() != filter_branch.lower():
                continue

            # Count tasks under this plan
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE status = 'done') as done
                FROM tasks
                WHERE tenant_id = %s AND plan_blob_hash = %s
                  AND status != 'deleted'
            """, (tenant_id, blob_hash))
            counts = cur.fetchone()
            task_count = counts['total'] if counts else 0
            done_count = counts['done'] if counts else 0

            plan_entry = {
                'title': plan_title,
                'status': plan_status,
                'blob_hash': blob_hash,
                'progress': f"{done_count}/{task_count}",
                'task_count': task_count,
                'done_count': done_count
            }

            if plan_branch not in plans_by_branch:
                plans_by_branch[plan_branch] = []
            plans_by_branch[plan_branch].append(plan_entry)

        # 2. Build landscape with health scores per branch
        for branch_name, plans in plans_by_branch.items():
            total_tasks = sum(p['task_count'] for p in plans)
            done_tasks = sum(p['done_count'] for p in plans)
            health = f"{round(done_tasks / total_tasks * 100)}%" if total_tasks > 0 else "no tasks"

            landscape[branch_name] = {
                'plans': plans,
                'health': health
            }

        # 3. Orphan backlog: tasks not under any plan
        backlog_sql = """
            SELECT id, title, description, branch, priority, assigned_to, status, created_at
            FROM tasks
            WHERE tenant_id = %s
              AND (plan_blob_hash IS NULL)
              AND status IN ('open', 'claimed', 'blocked')
            ORDER BY priority ASC, created_at ASC
            LIMIT 50
        """
        backlog_params = [tenant_id]
        if filter_branch:
            backlog_sql = """
                SELECT id, title, description, branch, priority, assigned_to, status, created_at
                FROM tasks
                WHERE tenant_id = %s
                  AND (plan_blob_hash IS NULL)
                  AND status IN ('open', 'claimed', 'blocked')
                  AND LOWER(branch) = LOWER(%s)
                ORDER BY priority ASC, created_at ASC
                LIMIT 50
            """
            backlog_params.append(filter_branch)

        cur.execute(backlog_sql, backlog_params)
        for row in cur.fetchall():
            backlog.append({
                'id': str(row['id']),
                'title': row.get('title') or row['description'][:80],
                'description': row['description'][:200] if row['description'] else None,
                'branch': row['branch'],
                'priority': row['priority'],
                'assigned_to': row['assigned_to'],
                'status': row['status']
            })

        cur.close()
        return jsonify({
            'work_landscape': landscape,
            'backlog': backlog,
            'summary': {
                'total_plans': sum(len(p) for p in plans_by_branch.values()),
                'total_branches': len(landscape),
                'backlog_count': len(backlog)
            }
        })

    except Exception as e:
        cur.close()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Landscape query failed: {str(e)}'}), 500


def ensure_task_claims_table():
    """Create task_claims table if it doesn't exist."""
    cur = get_cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS task_claims (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
            task_id UUID NOT NULL,
            instance_id VARCHAR(100) NOT NULL,
            claimed_at TIMESTAMPTZ DEFAULT NOW(),
            released_at TIMESTAMPTZ,
            release_reason VARCHAR(50),
            UNIQUE(tenant_id, task_id, instance_id, claimed_at)
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_task_claims_task ON task_claims(task_id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_task_claims_instance ON task_claims(instance_id)')
    get_db().commit()
    cur.close()


@app.route('/v2/tasks/<task_id>/claim', methods=['POST'])
def claim_task(task_id):
    """Claim a task for an agent instance. Includes collision detection."""
    ensure_task_claims_table()
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')

    if not instance_id:
        return jsonify({'error': 'instance_id required'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        # Check if system is halted
        cur.execute('''
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'halt_state'
            )
        ''')
        row = cur.fetchone()
        if row and row.get('exists', False):
            cur.execute('SELECT halted, reason FROM halt_state WHERE tenant_id = %s', (get_tenant_id(),))
            halt_row = cur.fetchone()
            if halt_row and halt_row['halted']:
                cur.close()
                return jsonify({
                    'error': 'System is halted. No new claims allowed.',
                    'reason': halt_row['reason']
                }), 503

        # Check if task exists and is claimable
        cur.execute(
            'SELECT * FROM tasks WHERE id = %s AND tenant_id = %s',
            (task_id, get_tenant_id())
        )
        task = cur.fetchone()

        if not task:
            cur.close()
            return jsonify({'error': 'Task not found'}), 404

        if task['status'] == 'done':
            cur.close()
            return jsonify({'error': 'Task already completed'}), 409

        # Check for existing active claims (collision detection)
        cur.execute(
            '''SELECT * FROM task_claims
               WHERE task_id = %s AND tenant_id = %s AND released_at IS NULL''',
            (task_id, get_tenant_id())
        )
        existing_claim = cur.fetchone()

        if existing_claim:
            cur.close()
            return jsonify({
                'error': 'Task already claimed',
                'claimed_by': existing_claim['instance_id'],
                'claimed_at': str(existing_claim['claimed_at'])
            }), 409

        # Create the claim
        cur.execute(
            '''INSERT INTO task_claims (tenant_id, task_id, instance_id)
               VALUES (%s, %s, %s)
               RETURNING id, claimed_at''',
            (get_tenant_id(), task_id, instance_id)
        )
        claim_row = cur.fetchone()

        # Update task status
        cur.execute(
            '''UPDATE tasks SET status = 'claimed', assigned_to = %s
               WHERE id = %s AND tenant_id = %s''',
            (instance_id, task_id, get_tenant_id())
        )

        db.commit()
        cur.close()

        return jsonify({
            'status': 'claimed',
            'task_id': task_id,
            'instance_id': instance_id,
            'claim_id': str(claim_row['id']),
            'claimed_at': str(claim_row['claimed_at'])
        })

    except Exception as e:
        import traceback
        db.rollback()
        cur.close()
        return jsonify({'error': str(e), 'type': type(e).__name__, 'traceback': traceback.format_exc()}), 500


@app.route('/v2/tasks/<task_id>/release', methods=['POST'])
def release_task(task_id):
    """Release a task claim."""
    ensure_task_claims_table()
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    reason = data.get('reason', 'manual')  # completed, blocked, timeout, manual

    if not instance_id:
        return jsonify({'error': 'instance_id required'}), 400

    valid_reasons = ['completed', 'blocked', 'timeout', 'manual']
    if reason not in valid_reasons:
        return jsonify({'error': f'Invalid reason. Must be one of: {valid_reasons}'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        # Find active claim for this instance
        cur.execute(
            '''SELECT * FROM task_claims
               WHERE task_id = %s AND instance_id = %s AND tenant_id = %s AND released_at IS NULL''',
            (task_id, instance_id, get_tenant_id())
        )
        claim = cur.fetchone()

        if not claim:
            cur.close()
            return jsonify({'error': 'No active claim found for this instance'}), 404

        # Release the claim
        now = datetime.utcnow().isoformat() + 'Z'
        cur.execute(
            '''UPDATE task_claims SET released_at = %s, release_reason = %s
               WHERE id = %s''',
            (now, reason, claim['id'])
        )

        # Update task status based on reason
        new_status = 'done' if reason == 'completed' else ('blocked' if reason == 'blocked' else 'open')
        cur.execute(
            '''UPDATE tasks SET status = %s
               WHERE id = %s AND tenant_id = %s''',
            (new_status, task_id, get_tenant_id())
        )

        db.commit()
        cur.close()

        return jsonify({
            'status': 'released',
            'task_id': task_id,
            'instance_id': instance_id,
            'reason': reason,
            'new_task_status': new_status,
            'released_at': now
        })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/tasks/stale', methods=['GET'])
def get_stale_tasks():
    """Get stale tasks for cron monitoring. 
    
    Returns open tasks older than threshold (default 24h) and 
    claimed tasks older than threshold (default 4h).
    
    Can be called by Railway cron to alert about stuck work.
    """
    open_hours = request.args.get('open_hours', 24, type=int)
    claimed_hours = request.args.get('claimed_hours', 4, type=int)
    
    cur = get_cursor()
    
    # Open tasks older than threshold
    cur.execute("""
        SELECT id, description, branch, priority, created_at, metadata
        FROM tasks 
        WHERE tenant_id = %s AND status = 'open'
        AND created_at < NOW() - INTERVAL '%s hours'
        ORDER BY priority ASC, created_at ASC
    """, (get_tenant_id(), open_hours))
    
    stale_open = []
    for row in cur.fetchall():
        stale_open.append({
            'id': str(row['id']),
            'description': row['description'],
            'branch': row['branch'],
            'priority': row['priority'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'age_hours': round((datetime.utcnow() - row['created_at'].replace(tzinfo=None)).total_seconds() / 3600, 1) if row['created_at'] else None
        })
    
    # Claimed tasks older than threshold (might be stuck)
    cur.execute("""
        SELECT t.id, t.description, t.branch, t.assigned_to, tc.claimed_at
        FROM tasks t
        JOIN task_claims tc ON t.id = tc.task_id AND t.tenant_id = tc.tenant_id
        WHERE t.tenant_id = %s AND t.status = 'claimed'
        AND tc.released_at IS NULL
        AND tc.claimed_at < NOW() - INTERVAL '%s hours'
        ORDER BY tc.claimed_at ASC
    """, (get_tenant_id(), claimed_hours))
    
    stale_claimed = []
    for row in cur.fetchall():
        stale_claimed.append({
            'id': str(row['id']),
            'description': row['description'],
            'branch': row['branch'],
            'assigned_to': row['assigned_to'],
            'claimed_at': row['claimed_at'].isoformat() if row['claimed_at'] else None,
            'age_hours': round((datetime.utcnow() - row['claimed_at'].replace(tzinfo=None)).total_seconds() / 3600, 1) if row['claimed_at'] else None
        })
    
    cur.close()
    
    return jsonify({
        'stale_open_tasks': stale_open,
        'stale_claimed_tasks': stale_claimed,
        'thresholds': {
            'open_hours': open_hours,
            'claimed_hours': claimed_hours
        },
        'alert': len(stale_open) > 0 or len(stale_claimed) > 0,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


@app.route('/v2/tasks/halt', methods=['POST'])
def halt_tasks():
    """Emergency stop - halt all claimed tasks and prevent new claims."""
    data = request.get_json() or {}
    reason = data.get('reason', 'Manual emergency halt')

    db = get_db()
    cur = get_cursor()

    try:
        # Ensure halt_state table exists
        cur.execute('''
            CREATE TABLE IF NOT EXISTS halt_state (
                id SERIAL PRIMARY KEY,
                tenant_id VARCHAR(100) NOT NULL UNIQUE,
                halted BOOLEAN DEFAULT FALSE,
                halted_at TIMESTAMP,
                reason TEXT
            )
        ''')

        now = datetime.utcnow().isoformat() + 'Z'

        # Upsert halt state
        cur.execute('''
            INSERT INTO halt_state (tenant_id, halted, halted_at, reason)
            VALUES (%s, TRUE, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE
            SET halted = TRUE, halted_at = EXCLUDED.halted_at, reason = EXCLUDED.reason
        ''', (get_tenant_id(), now, reason))

        # Set all claimed tasks to blocked
        cur.execute('''
            UPDATE tasks SET status = 'blocked'
            WHERE tenant_id = %s AND status = 'claimed'
            RETURNING id
        ''', (get_tenant_id(),))
        affected_tasks = [str(row['id']) for row in cur.fetchall()]

        # Release all active claims with EMERGENCY_HALT reason
        cur.execute('''
            UPDATE task_claims SET released_at = %s, release_reason = 'EMERGENCY_HALT'
            WHERE tenant_id = %s AND released_at IS NULL
        ''', (now, get_tenant_id()))

        db.commit()
        cur.close()

        return jsonify({
            'status': 'halted',
            'affected_tasks': len(affected_tasks),
            'task_ids': affected_tasks,
            'halted_at': now,
            'reason': reason
        })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/tasks/resume', methods=['POST'])
def resume_tasks():
    """Release the halt - allow new task claims again."""
    db = get_db()
    cur = get_cursor()

    try:
        # Check if halt_state table exists
        cur.execute('''
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'halt_state'
            )
        ''')
        row = cur.fetchone()
        if not (row and row.get('exists', False)):
            cur.close()
            return jsonify({'status': 'not_halted', 'message': 'System was not halted'})

        # Clear halt state
        cur.execute('''
            UPDATE halt_state SET halted = FALSE
            WHERE tenant_id = %s
            RETURNING halted_at, reason
        ''', (get_tenant_id(),))
        row = cur.fetchone()

        db.commit()
        cur.close()

        if row:
            return jsonify({
                'status': 'resumed',
                'previous_halt_at': str(row['halted_at']) if row['halted_at'] else None,
                'previous_reason': row['reason'],
                'message': 'Task claims now allowed'
            })
        else:
            return jsonify({'status': 'not_halted', 'message': 'System was not halted'})

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/tasks/halt-status', methods=['GET'])
def halt_status():
    """Check if the task system is currently halted."""
    cur = get_cursor()

    try:
        cur.execute('''
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'halt_state'
            )
        ''')
        row = cur.fetchone()
        if not (row and row.get('exists', False)):
            cur.close()
            return jsonify({'halted': False})

        cur.execute('''
            SELECT halted, halted_at, reason FROM halt_state
            WHERE tenant_id = %s
        ''', (get_tenant_id(),))
        row = cur.fetchone()
        cur.close()

        if row and row['halted']:
            return jsonify({
                'halted': True,
                'halted_at': str(row['halted_at']) if row['halted_at'] else None,
                'reason': row['reason']
            })
        else:
            return jsonify({'halted': False})

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/tasks/backfill-memory', methods=['POST'])
def backfill_tasks_to_memory():
    """Backfill existing tasks into memory system for semantic search.
    
    Tasks created before dual-write are orphaned from semantic search.
    This creates memory commits for all tasks missing the task:{id} tag.
    Also ensures blob_hash column exists (Task Unification migration).
    """
    db = get_db()
    cur = get_cursor()
    
    # Ensure blob_hash column exists (idempotent migration)
    try:
        cur.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS blob_hash TEXT')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tasks_blob_hash ON tasks(blob_hash)')
        db.commit()
    except Exception as e:
        print(f"[BACKFILL] Migration note: {e}", file=sys.stderr)
        db.rollback()
    
    backfilled = 0
    skipped = 0
    errors = []
    
    try:
        # Get all tasks
        cur.execute('''
            SELECT id, description, branch, assigned_to, status, priority, metadata, created_at
            FROM tasks
            WHERE tenant_id = %s
            ORDER BY created_at ASC
        ''', (get_tenant_id(),))
        
        tasks = cur.fetchall()
        
        for task in tasks:
            task_id = str(task['id'])
            
            # Check if already has memory
            cur.execute('''
                SELECT 1 FROM tags 
                WHERE tenant_id = %s AND tag = %s
                LIMIT 1
            ''', (get_tenant_id(), f"task:{task_id}"))
            
            if cur.fetchone():
                skipped += 1
                continue
            
            try:
                branch = task['branch'] or 'command-center'
                # Handle timestamp - avoid double timezone suffix
                if task['created_at']:
                    ts = task['created_at']
                    if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                        created_at = ts.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
                    else:
                        created_at = ts.isoformat() + 'Z'
                else:
                    created_at = datetime.utcnow().isoformat() + 'Z'
                
                # Build memory content
                metadata = task['metadata'] if task['metadata'] else {}
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                    
                memory_content = {
                    'type': 'task_created',
                    'task_id': task_id,
                    'description': task['description'],
                    'branch': branch,
                    'priority': task['priority'],
                    'assigned_to': task['assigned_to'],
                    'status': task['status'],
                    'metadata': metadata
                }
                content_str = json.dumps(memory_content)
                blob_hash = compute_hash(content_str)
                
                # Insert blob
                cur.execute('''
                    INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (blob_hash) DO NOTHING
                ''', (blob_hash, get_tenant_id(), content_str, 'task', created_at, len(content_str)))
                
                # Generate and store embedding
                embedding = generate_embedding(content_str)
                if embedding:
                    cur.execute('''
                        UPDATE blobs SET embedding = %s WHERE blob_hash = %s AND tenant_id = %s
                    ''', (embedding, blob_hash, get_tenant_id()))
                
                # Create tree entry
                tree_hash = compute_hash(f"{branch}:{blob_hash}:{created_at}")
                message = f"TASK: {task['description'][:80]}{'...' if len(task['description']) > 80 else ''}"
                
                cur.execute('''
                    INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (get_tenant_id(), tree_hash, message[:100], blob_hash, 'task'))
                
                # Get branch head (case-insensitive)
                cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', (branch, get_tenant_id()))
                branch_row = cur.fetchone()
                
                if branch_row:
                    branch = branch_row['name']  # Use canonical casing
                    parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
                else:
                    cur.execute('''
                        INSERT INTO branches (tenant_id, name, head_commit, created_at)
                        VALUES (%s, %s, %s, %s)
                    ''', (get_tenant_id(), branch, 'GENESIS', created_at))
                    parent_hash = None
                
                # Create commit
                commit_data = f"{tree_hash}:{parent_hash}:{message}:{created_at}"
                commit_hash = compute_hash(commit_data)
                
                cur.execute('''
                    INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (commit_hash, get_tenant_id(), tree_hash, parent_hash, 'backfill', message, created_at))
                
                # Update branch head
                cur.execute('''
                    UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s
                ''', (commit_hash, branch, get_tenant_id()))
                
                # Add tag
                cur.execute('''
                    INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
                    VALUES (%s, %s, %s, %s)
                ''', (get_tenant_id(), blob_hash, f"task:{task_id}", created_at))
                
                # Link task to blob (Task Unification)
                cur.execute('''
                    UPDATE tasks SET blob_hash = %s WHERE id = %s AND tenant_id = %s
                ''', (blob_hash, task_id, get_tenant_id()))
                
                backfilled += 1
                db.commit()  # Commit each successful task
                
            except Exception as e:
                db.rollback()  # Rollback failed task
                errors.append({'task_id': task_id, 'error': str(e)})
        
        cur.close()
        
        return jsonify({
            'status': 'complete',
            'backfilled': backfilled,
            'skipped': skipped,
            'errors': errors,
            'total_tasks': len(tasks)
        })
        
    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/tasks/link-blobs', methods=['POST'])
def link_tasks_to_blobs():
    """Link existing tasks to their memory blobs via blob_hash column.
    
    Task Unification: finds tasks with existing task:{id} tags but missing blob_hash,
    and updates the task record to point to its blob.
    """
    db = get_db()
    cur = get_cursor()
    
    linked = 0
    already_linked = 0
    no_blob = 0
    errors = []
    
    try:
        # Get all tasks
        cur.execute('SELECT id FROM tasks WHERE tenant_id = %s', (get_tenant_id(),))
        tasks = cur.fetchall()
        
        for task in tasks:
            task_id = str(task['id'])
            
            # Check if already linked
            cur.execute('SELECT blob_hash FROM tasks WHERE id = %s AND tenant_id = %s', (task_id, get_tenant_id()))
            task_row = cur.fetchone()
            if task_row and task_row['blob_hash']:
                already_linked += 1
                continue
            
            # Find blob via tag
            cur.execute('''
                SELECT blob_hash FROM tags 
                WHERE tenant_id = %s AND tag = %s
                LIMIT 1
            ''', (get_tenant_id(), f"task:{task_id}"))
            
            tag_row = cur.fetchone()
            if not tag_row:
                no_blob += 1
                continue
            
            blob_hash = tag_row['blob_hash']
            
            # Link task to blob
            try:
                cur.execute('''
                    UPDATE tasks SET blob_hash = %s WHERE id = %s AND tenant_id = %s
                ''', (blob_hash, task_id, get_tenant_id()))
                linked += 1
            except Exception as e:
                errors.append({'task_id': task_id, 'error': str(e)})
        
        db.commit()
        cur.close()
        
        return jsonify({
            'status': 'complete',
            'linked': linked,
            'already_linked': already_linked,
            'no_blob_found': no_blob,
            'errors': errors,
            'total_tasks': len(tasks)
        })
        
    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


# ==================== SESSION CHECKPOINTS (Crash Recovery) ====================

@app.route('/v2/session/checkpoint', methods=['POST'])
def create_checkpoint():
    """Create or update a session checkpoint for crash recovery.

    Ephemeral state layer - captures WHERE the instance WAS, not WHAT happened (that's commits).
    UPSERT semantics: one checkpoint per task.
    """
    data = request.get_json() or {}
    task_id = data.get('task_id')
    instance_id = data.get('instance_id')
    progress = data.get('progress')
    next_step = data.get('next_step')
    context_snapshot = data.get('context_snapshot', {})
    expires_at = data.get('expires_at')  # Optional TTL

    if not task_id:
        return jsonify({'error': 'task_id required'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        # Verify task exists
        cur.execute('SELECT id FROM tasks WHERE id = %s AND tenant_id = %s', (task_id, get_tenant_id()))
        if not cur.fetchone():
            cur.close()
            return jsonify({'error': f'Task {task_id} not found'}), 404

        # UPSERT checkpoint
        cur.execute('''
            INSERT INTO session_checkpoints (task_id, tenant_id, instance_id, progress, next_step, context_snapshot, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (task_id) DO UPDATE SET
                instance_id = EXCLUDED.instance_id,
                progress = EXCLUDED.progress,
                next_step = EXCLUDED.next_step,
                context_snapshot = EXCLUDED.context_snapshot,
                expires_at = EXCLUDED.expires_at
            RETURNING checkpoint_at
        ''', (task_id, get_tenant_id(), instance_id, progress, next_step, json.dumps(context_snapshot), expires_at))

        row = cur.fetchone()
        checkpoint_at = str(row['checkpoint_at'])

        db.commit()
        cur.close()

        return jsonify({
            'status': 'checkpointed',
            'task_id': task_id,
            'instance_id': instance_id,
            'progress': progress,
            'next_step': next_step,
            'checkpoint_at': checkpoint_at
        }), 200

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/session/resume', methods=['GET'])
def get_checkpoint():
    """Get a checkpoint for a task if one exists.

    Used to resume work after a crash or context loss.
    """
    task_id = request.args.get('task_id')

    if not task_id:
        return jsonify({'error': 'task_id required'}), 400

    cur = get_cursor()

    try:
        cur.execute('''
            SELECT sc.*, t.description as task_description, t.status as task_status, t.branch
            FROM session_checkpoints sc
            JOIN tasks t ON sc.task_id = t.id
            WHERE sc.task_id = %s AND sc.tenant_id = %s
        ''', (task_id, get_tenant_id()))

        row = cur.fetchone()
        cur.close()

        if not row:
            return jsonify({'checkpoint': None, 'message': 'No checkpoint found for this task'}), 200

        checkpoint = {
            'task_id': str(row['task_id']),
            'instance_id': row['instance_id'],
            'progress': row['progress'],
            'next_step': row['next_step'],
            'context_snapshot': row['context_snapshot'] if row['context_snapshot'] else {},
            'checkpoint_at': str(row['checkpoint_at']),
            'expires_at': str(row['expires_at']) if row['expires_at'] else None,
            'task_description': row['task_description'],
            'task_status': row['task_status'],
            'branch': row['branch']
        }

        return jsonify({'checkpoint': checkpoint}), 200

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/session/checkpoint', methods=['DELETE'])
def delete_checkpoint():
    """Delete a checkpoint for a task.

    Called when task is completed or checkpoint is no longer needed.
    """
    task_id = request.args.get('task_id')

    if not task_id:
        return jsonify({'error': 'task_id required'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        cur.execute('''
            DELETE FROM session_checkpoints
            WHERE task_id = %s AND tenant_id = %s
            RETURNING task_id
        ''', (task_id, get_tenant_id()))

        deleted = cur.fetchone()
        db.commit()
        cur.close()

        if deleted:
            return jsonify({'status': 'deleted', 'task_id': task_id}), 200
        else:
            return jsonify({'status': 'not_found', 'message': f'No checkpoint for task {task_id}'}), 200

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/session/orphaned', methods=['GET'])
def list_orphaned_checkpoints():
    """List orphaned checkpoints - instances that may have crashed.

    Orphaned = checkpoint_at > 2 hours ago AND task.status != done/deleted
    Shows potential crashed instances for dashboard monitoring.
    """
    hours = request.args.get('hours', 2, type=int)

    cur = get_cursor()

    try:
        cur.execute('''
            SELECT sc.*, t.description as task_description, t.status as task_status, t.branch
            FROM session_checkpoints sc
            JOIN tasks t ON sc.task_id = t.id
            WHERE sc.tenant_id = %s
            AND sc.checkpoint_at < NOW() - INTERVAL '%s hours'
            AND t.status != 'done'
            ORDER BY sc.checkpoint_at ASC
        ''', (get_tenant_id(), hours))

        orphaned = []
        for row in cur.fetchall():
            orphaned.append({
                'task_id': str(row['task_id']),
                'instance_id': row['instance_id'],
                'progress': row['progress'],
                'next_step': row['next_step'],
                'checkpoint_at': str(row['checkpoint_at']),
                'task_description': row['task_description'],
                'task_status': row['task_status'],
                'branch': row['branch'],
                'context_snapshot': row['context_snapshot'] if row['context_snapshot'] else {}
            })

        cur.close()

        return jsonify({
            'orphaned': orphaned,
            'count': len(orphaned),
            'threshold_hours': hours
        }), 200

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


# ==================== TRAILS (Memory Path Tracking) ====================

def ensure_trails_table():
    """Create trails table if it doesn't exist, with lifecycle columns."""
    cur = get_cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS trails (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(100) NOT NULL DEFAULT 'default',
            source_blob VARCHAR(64) NOT NULL,
            target_blob VARCHAR(64) NOT NULL,
            traversal_count INTEGER DEFAULT 1,
            last_traversed TIMESTAMP DEFAULT NOW(),
            strength FLOAT DEFAULT 1.0,
            state VARCHAR(20) DEFAULT 'active',
            archived_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(tenant_id, source_blob, target_blob)
        )
    ''')
    # Add lifecycle columns if table already exists without them
    cur.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'trails' AND column_name = 'state') THEN
                ALTER TABLE trails ADD COLUMN state VARCHAR(20) DEFAULT 'active';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'trails' AND column_name = 'archived_at') THEN
                ALTER TABLE trails ADD COLUMN archived_at TIMESTAMP;
            END IF;
        END $$;
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trails_strength ON trails(strength DESC)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trails_source ON trails(source_blob)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trails_target ON trails(target_blob)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trails_state ON trails(state)')
    get_db().commit()
    cur.close()


@app.route('/v2/trails/record', methods=['POST'])
def record_trail():
    """Record a traversal between two memories. Creates or strengthens the trail."""
    ensure_trails_table()

    data = request.get_json() or {}
    source_blob = data.get('source_blob')
    target_blob = data.get('target_blob')

    if not source_blob or not target_blob:
        return jsonify({'error': 'source_blob and target_blob required'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        cur.execute('''
            INSERT INTO trails (tenant_id, source_blob, target_blob, traversal_count, last_traversed, strength)
            VALUES (%s, %s, %s, 1, NOW(), 1.0)
            ON CONFLICT (tenant_id, source_blob, target_blob) DO UPDATE
            SET traversal_count = trails.traversal_count + 1,
                last_traversed = NOW(),
                strength = LEAST(trails.strength * 1.1, 10.0)
            RETURNING id, traversal_count, strength
        ''', (get_tenant_id(), source_blob, target_blob))

        row = cur.fetchone()
        db.commit()
        cur.close()

        return jsonify({
            'status': 'recorded',
            'trail_id': str(row['id']),
            'source_blob': source_blob,
            'target_blob': target_blob,
            'traversal_count': row['traversal_count'],
            'strength': row['strength']
        })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/trails/hot', methods=['GET'])
def get_hot_trails():
    """Get strongest trails, sorted by strength. Use limit param (default 20)."""
    ensure_trails_table()

    limit = request.args.get('limit', 20, type=int)
    cur = get_cursor()

    try:
        cur.execute('''
            SELECT id, source_blob, target_blob, traversal_count,
                   last_traversed, strength, created_at
            FROM trails
            WHERE tenant_id = %s
            ORDER BY strength DESC
            LIMIT %s
        ''', (get_tenant_id(), limit))

        trails = []
        for row in cur.fetchall():
            trails.append({
                'id': str(row['id']),
                'source_blob': row['source_blob'],
                'target_blob': row['target_blob'],
                'traversal_count': row['traversal_count'],
                'last_traversed': row['last_traversed'].isoformat() if row['last_traversed'] else None,
                'strength': row['strength'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None
            })

        cur.close()
        return jsonify({'trails': trails, 'count': len(trails)})

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/trails/from/<source_blob>', methods=['GET'])
def get_trails_from(source_blob):
    """Get outbound trails from a specific memory blob."""
    ensure_trails_table()

    limit = request.args.get('limit', 20, type=int)
    cur = get_cursor()

    try:
        cur.execute('''
            SELECT id, source_blob, target_blob, traversal_count,
                   last_traversed, strength
            FROM trails
            WHERE tenant_id = %s AND source_blob = %s
            ORDER BY strength DESC
            LIMIT %s
        ''', (get_tenant_id(), source_blob, limit))

        trails = []
        for row in cur.fetchall():
            trails.append({
                'id': str(row['id']),
                'target_blob': row['target_blob'],
                'traversal_count': row['traversal_count'],
                'last_traversed': row['last_traversed'].isoformat() if row['last_traversed'] else None,
                'strength': row['strength']
            })

        cur.close()
        return jsonify({'source_blob': source_blob, 'outbound_trails': trails})

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/trails/to/<target_blob>', methods=['GET'])
def get_trails_to(target_blob):
    """Get inbound trails to a specific memory blob."""
    ensure_trails_table()

    limit = request.args.get('limit', 20, type=int)
    cur = get_cursor()

    try:
        cur.execute('''
            SELECT id, source_blob, target_blob, traversal_count,
                   last_traversed, strength
            FROM trails
            WHERE tenant_id = %s AND target_blob = %s
            ORDER BY strength DESC
            LIMIT %s
        ''', (get_tenant_id(), target_blob, limit))

        trails = []
        for row in cur.fetchall():
            trails.append({
                'id': str(row['id']),
                'source_blob': row['source_blob'],
                'traversal_count': row['traversal_count'],
                'last_traversed': row['last_traversed'].isoformat() if row['last_traversed'] else None,
                'strength': row['strength']
            })

        cur.close()
        return jsonify({'target_blob': target_blob, 'inbound_trails': trails})

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/trails/decay', methods=['POST'])
def decay_trails():
    """Apply Physarum-inspired decay to trails based on idle time.

    FROZEN by sacred directive (2026-02-09). No decay until Steve re-enables.
    See Boswell commit bf4b68532a81 on branch boswell.
    Lift condition: Steve explicitly re-enables after architecture review.

    Original formula: strength = base_strength * (0.95 ^ days_idle)

    State transitions based on strength:
    - ACTIVE: strength >= 1.0 (frequently used)
    - FADING: 0.3 <= strength < 1.0 (cooling off)
    - DORMANT: 0.1 <= strength < 0.3 (rarely accessed)
    - ARCHIVED: strength < 0.1 (preserved but inactive)

    Call via Railway cron daily.
    """
    # SACRED DIRECTIVE: Decay frozen (2026-02-09)
    # No trail may transition to dormant or archived.
    # Lift condition: Steve explicitly re-enables after architecture review.
    return jsonify({
        'status': 'frozen',
        'reason': 'Sacred directive bf4b68532a81 - decay disabled until architecture review',
        'decay_rate': 1.0,
        'trails_processed': 0,
        'state_transitions': {
            'became_active': 0, 'became_fading': 0,
            'became_dormant': 0, 'became_archived': 0
        },
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

    # --- ORIGINAL DECAY LOGIC (frozen) ---
    ensure_trails_table()

    db = get_db()
    cur = get_cursor()
    decay_rate = 0.95  # Per-day decay factor

    try:
        # Apply time-based decay: strength = strength * (0.95 ^ days_since_last_traversal)
        # PostgreSQL: EXTRACT(EPOCH FROM (NOW() - last_traversed)) / 86400 = days idle
        cur.execute('''
            UPDATE trails
            SET strength = strength * POWER(%s, EXTRACT(EPOCH FROM (NOW() - last_traversed)) / 86400)
            WHERE tenant_id = %s AND state != 'archived'
        ''', (decay_rate, get_tenant_id()))
        decayed_count = cur.rowcount

        # Update states based on new strength values
        # ACTIVE: strength >= 1.0
        cur.execute('''
            UPDATE trails SET state = 'active'
            WHERE tenant_id = %s AND strength >= 1.0 AND state != 'active'
        ''', (get_tenant_id(),))
        became_active = cur.rowcount

        # FADING: 0.3 <= strength < 1.0
        cur.execute('''
            UPDATE trails SET state = 'fading'
            WHERE tenant_id = %s AND strength >= 0.3 AND strength < 1.0 AND state != 'fading'
        ''', (get_tenant_id(),))
        became_fading = cur.rowcount

        # DORMANT: 0.1 <= strength < 0.3
        cur.execute('''
            UPDATE trails SET state = 'dormant'
            WHERE tenant_id = %s AND strength >= 0.1 AND strength < 0.3 AND state != 'dormant'
        ''', (get_tenant_id(),))
        became_dormant = cur.rowcount

        # ARCHIVED: strength < 0.1 (preserve, don't delete)
        cur.execute('''
            UPDATE trails SET state = 'archived', archived_at = NOW()
            WHERE tenant_id = %s AND strength < 0.1 AND state != 'archived'
        ''', (get_tenant_id(),))
        became_archived = cur.rowcount

        # Get current state distribution
        cur.execute('''
            SELECT state, COUNT(*) as count, AVG(strength) as avg_strength
            FROM trails WHERE tenant_id = %s
            GROUP BY state
        ''', (get_tenant_id(),))
        state_stats = {row['state']: {'count': row['count'], 'avg_strength': float(row['avg_strength'] or 0)}
                      for row in cur.fetchall()}

        db.commit()
        cur.close()

        return jsonify({
            'status': 'decayed',
            'decay_rate': decay_rate,
            'trails_processed': decayed_count,
            'state_transitions': {
                'became_active': became_active,
                'became_fading': became_fading,
                'became_dormant': became_dormant,
                'became_archived': became_archived
            },
            'state_distribution': state_stats,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/trails/health', methods=['GET'])
def trail_health():
    """Get trail system health overview - state distribution, decay rates, activity."""
    ensure_trails_table()
    cur = get_cursor()

    try:
        # State distribution
        cur.execute('''
            SELECT state, COUNT(*) as count,
                   AVG(strength) as avg_strength,
                   MIN(strength) as min_strength,
                   MAX(strength) as max_strength,
                   AVG(traversal_count) as avg_traversals
            FROM trails WHERE tenant_id = %s
            GROUP BY state
        ''', (get_tenant_id(),))
        states = {}
        total_trails = 0
        for row in cur.fetchall():
            states[row['state'] or 'active'] = {
                'count': row['count'],
                'avg_strength': round(float(row['avg_strength'] or 0), 3),
                'min_strength': round(float(row['min_strength'] or 0), 3),
                'max_strength': round(float(row['max_strength'] or 0), 3),
                'avg_traversals': round(float(row['avg_traversals'] or 0), 1)
            }
            total_trails += row['count']

        # Recent activity (last 24h, 7d, 30d)
        cur.execute('''
            SELECT
                COUNT(*) FILTER (WHERE last_traversed > NOW() - INTERVAL '24 hours') as last_24h,
                COUNT(*) FILTER (WHERE last_traversed > NOW() - INTERVAL '7 days') as last_7d,
                COUNT(*) FILTER (WHERE last_traversed > NOW() - INTERVAL '30 days') as last_30d
            FROM trails WHERE tenant_id = %s
        ''', (get_tenant_id(),))
        activity = cur.fetchone()

        # Top 5 strongest trails
        cur.execute('''
            SELECT source_blob, target_blob, strength, traversal_count, state,
                   last_traversed
            FROM trails WHERE tenant_id = %s
            ORDER BY strength DESC LIMIT 5
        ''', (get_tenant_id(),))
        hottest = [{
            'source': row['source_blob'][:12] + '...',
            'target': row['target_blob'][:12] + '...',
            'strength': round(float(row['strength']), 2),
            'traversals': row['traversal_count'],
            'state': row['state'] or 'active'
        } for row in cur.fetchall()]

        cur.close()

        return jsonify({
            'total_trails': total_trails,
            'state_distribution': states,
            'activity': {
                'last_24h': activity['last_24h'],
                'last_7d': activity['last_7d'],
                'last_30d': activity['last_30d']
            },
            'hottest_trails': hottest,
            'decay_rate': 0.95,
            'state_thresholds': {
                'active': '>= 1.0',
                'fading': '0.3 - 1.0',
                'dormant': '0.1 - 0.3',
                'archived': '< 0.1'
            },
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/trails/buried', methods=['GET'])
def buried_memories():
    """Find dormant and archived trails - memories fading from recall."""
    ensure_trails_table()
    cur = get_cursor()

    limit = request.args.get('limit', 20, type=int)
    include_archived = request.args.get('include_archived', 'true').lower() == 'true'

    try:
        states = ['dormant']
        if include_archived:
            states.append('archived')

        placeholders = ','.join(['%s'] * len(states))
        cur.execute(f'''
            SELECT t.id, t.source_blob, t.target_blob, t.strength,
                   t.traversal_count, t.state, t.last_traversed, t.archived_at,
                   t.created_at
            FROM trails t
            WHERE t.tenant_id = %s AND t.state IN ({placeholders})
            ORDER BY t.strength ASC
            LIMIT %s
        ''', (get_tenant_id(), *states, limit))

        buried = []
        for row in cur.fetchall():
            days_dormant = (datetime.utcnow() - row['last_traversed']).days if row['last_traversed'] else 0
            buried.append({
                'id': str(row['id']),
                'source_blob': row['source_blob'],
                'target_blob': row['target_blob'],
                'strength': round(float(row['strength']), 4),
                'traversal_count': row['traversal_count'],
                'state': row['state'],
                'days_dormant': days_dormant,
                'last_traversed': row['last_traversed'].isoformat() if row['last_traversed'] else None,
                'archived_at': row['archived_at'].isoformat() if row['archived_at'] else None
            })

        cur.close()

        return jsonify({
            'buried_trails': buried,
            'count': len(buried),
            'include_archived': include_archived,
            'message': 'These memory paths are fading. Traverse them to resurrect.',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/trails/forecast', methods=['GET'])
def decay_forecast():
    """Predict when trails will transition states based on decay rate."""
    ensure_trails_table()
    cur = get_cursor()

    decay_rate = 0.95

    try:
        cur.execute('''
            SELECT id, source_blob, target_blob, strength, state, last_traversed
            FROM trails
            WHERE tenant_id = %s AND state IN ('active', 'fading')
            ORDER BY strength DESC
            LIMIT 20
        ''', (get_tenant_id(),))

        forecasts = []
        for row in cur.fetchall():
            strength = float(row['strength'])
            current_state = row['state'] or 'active'

            # Calculate days until state transitions
            # strength * (0.95 ^ days) = threshold
            # days = log(threshold/strength) / log(0.95)
            days_to_fading = None
            days_to_dormant = None
            days_to_archived = None

            if strength > 1.0:
                days_to_fading = max(0, int(math.log(1.0 / strength) / math.log(decay_rate)))
            if strength > 0.3:
                days_to_dormant = max(0, int(math.log(0.3 / strength) / math.log(decay_rate)))
            if strength > 0.1:
                days_to_archived = max(0, int(math.log(0.1 / strength) / math.log(decay_rate)))

            forecasts.append({
                'source_blob': row['source_blob'][:16] + '...',
                'target_blob': row['target_blob'][:16] + '...',
                'current_strength': round(strength, 3),
                'current_state': current_state,
                'days_to_fading': days_to_fading,
                'days_to_dormant': days_to_dormant,
                'days_to_archived': days_to_archived
            })

        cur.close()

        return jsonify({
            'forecasts': forecasts,
            'decay_rate': decay_rate,
            'interpretation': 'Days until trail transitions to each state if not traversed',
            'remedy': 'Traverse the trail (boswell_record_trail) to reset decay timer and boost strength',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/trails/resurrect', methods=['POST'])
def resurrect_trail():
    """Resurrect a dormant or archived trail by traversing it."""
    ensure_trails_table()

    data = request.get_json() or {}
    trail_id = data.get('trail_id')
    source_blob = data.get('source_blob')
    target_blob = data.get('target_blob')

    if not trail_id and not (source_blob and target_blob):
        return jsonify({'error': 'Provide trail_id or (source_blob, target_blob)'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        if trail_id:
            cur.execute('''
                UPDATE trails
                SET strength = GREATEST(strength * 2, 1.0),
                    state = 'active',
                    last_traversed = NOW(),
                    traversal_count = traversal_count + 1,
                    archived_at = NULL
                WHERE id = %s AND tenant_id = %s
                RETURNING id, source_blob, target_blob, strength, state, traversal_count
            ''', (trail_id, get_tenant_id()))
        else:
            cur.execute('''
                UPDATE trails
                SET strength = GREATEST(strength * 2, 1.0),
                    state = 'active',
                    last_traversed = NOW(),
                    traversal_count = traversal_count + 1,
                    archived_at = NULL
                WHERE source_blob = %s AND target_blob = %s AND tenant_id = %s
                RETURNING id, source_blob, target_blob, strength, state, traversal_count
            ''', (source_blob, target_blob, get_tenant_id()))

        row = cur.fetchone()
        db.commit()
        cur.close()

        if row:
            return jsonify({
                'status': 'resurrected',
                'trail': {
                    'id': str(row['id']),
                    'source_blob': row['source_blob'],
                    'target_blob': row['target_blob'],
                    'new_strength': round(float(row['strength']), 3),
                    'state': row['state'],
                    'traversal_count': row['traversal_count']
                },
                'message': 'Trail resurrected to active state'
            })
        else:
            return jsonify({'error': 'Trail not found'}), 404

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


# ==================== IMMUNE SYSTEM (Anomaly Detection & Quarantine) ====================

def ensure_immune_tables():
    """Create immune system tables if they don't exist."""
    cur = get_cursor()

    # Add quarantine columns to blobs
    cur.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'blobs' AND column_name = 'quarantined') THEN
                ALTER TABLE blobs ADD COLUMN quarantined BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'blobs' AND column_name = 'quarantined_at') THEN
                ALTER TABLE blobs ADD COLUMN quarantined_at TIMESTAMPTZ;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'blobs' AND column_name = 'quarantine_reason') THEN
                ALTER TABLE blobs ADD COLUMN quarantine_reason TEXT;
            END IF;
        END $$;
    ''')

    # Create partial index for quarantined blobs
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_blobs_quarantined
        ON blobs(quarantined) WHERE quarantined = TRUE
    ''')

    # Create immune_log table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS immune_log (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001',
            action VARCHAR(50) NOT NULL,
            blob_hash VARCHAR(64),
            patrol_type VARCHAR(50),
            details JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    cur.execute('CREATE INDEX IF NOT EXISTS idx_immune_log_action ON immune_log(action)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_immune_log_blob ON immune_log(blob_hash) WHERE blob_hash IS NOT NULL')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_immune_log_tenant ON immune_log(tenant_id)')

    # Add health columns to branch_fingerprints if table exists
    cur.execute('''
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'branch_fingerprints') THEN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'branch_fingerprints' AND column_name = 'health_score') THEN
                    ALTER TABLE branch_fingerprints ADD COLUMN health_score FLOAT DEFAULT 1.0;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'branch_fingerprints' AND column_name = 'last_patrol') THEN
                    ALTER TABLE branch_fingerprints ADD COLUMN last_patrol TIMESTAMPTZ;
                END IF;
            END IF;
        END $$;
    ''')

    get_db().commit()
    cur.close()


def log_immune_action(action: str, blob_hash: str = None, patrol_type: str = None, details: dict = None):
    """Log an immune system action for audit trail."""
    cur = get_cursor()
    cur.execute('''
        INSERT INTO immune_log (tenant_id, action, blob_hash, patrol_type, details)
        VALUES (%s, %s, %s, %s, %s)
    ''', (get_tenant_id(), action, blob_hash, patrol_type, json.dumps(details) if details else None))
    get_db().commit()
    cur.close()


def quarantine_blob(blob_hash: str, reason: str, patrol_type: str = None):
    """Quarantine a blob and log the action."""
    cur = get_cursor()
    cur.execute('''
        UPDATE blobs SET quarantined = TRUE, quarantined_at = NOW(), quarantine_reason = %s
        WHERE blob_hash = %s AND tenant_id = %s
    ''', (reason, blob_hash, get_tenant_id()))
    get_db().commit()
    cur.close()

    log_immune_action('QUARANTINE', blob_hash, patrol_type, {'reason': reason})


def get_quarantine_count() -> int:
    """Get count of quarantined blobs."""
    cur = get_cursor()
    cur.execute('''
        SELECT COUNT(*) as cnt FROM blobs
        WHERE quarantined = TRUE AND tenant_id = %s
    ''', (get_tenant_id(),))
    row = cur.fetchone()
    cur.close()
    return row['cnt'] if row else 0


# Patrol Routes - Anomaly Detectors

def patrol_centroid_drift(threshold: float = 0.5) -> list:
    """Detect blobs whose embeddings are too far from their branch centroid."""
    findings = []
    cur = get_cursor()

    # Get all branch centroids
    cur.execute('''
        SELECT branch_name, centroid FROM branch_fingerprints
        WHERE tenant_id = %s AND centroid IS NOT NULL
    ''', (get_tenant_id(),))
    fingerprints = {row['branch_name']: row['centroid'] for row in cur.fetchall()}

    if not fingerprints:
        cur.close()
        return findings

    # Check each blob against its branch centroid
    for branch_name, centroid in fingerprints.items():
        cur.execute('''
            SELECT b.blob_hash, b.embedding <=> %s::vector AS distance
            FROM blobs b
            JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
            JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
            JOIN branches br ON br.head_commit = c.commit_hash AND br.tenant_id = c.tenant_id
            WHERE br.name = %s AND b.embedding IS NOT NULL
              AND b.tenant_id = %s AND COALESCE(b.quarantined, FALSE) = FALSE
              AND b.embedding <=> %s::vector > %s
        ''', (centroid, branch_name, get_tenant_id(), centroid, threshold))

        for row in cur.fetchall():
            findings.append({
                'blob_hash': row['blob_hash'],
                'reason': f"Embedding distance {row['distance']:.3f} exceeds threshold {threshold} for branch {branch_name}",
                'distance': float(row['distance']),
                'branch': branch_name
            })

    cur.close()
    return findings


def patrol_orphan_blobs() -> list:
    """Detect blobs not referenced by any commit tree."""
    findings = []
    cur = get_cursor()

    cur.execute('''
        SELECT b.blob_hash, substring(b.content, 1, 100) as preview
        FROM blobs b
        LEFT JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
        WHERE t.id IS NULL AND b.tenant_id = %s AND COALESCE(b.quarantined, FALSE) = FALSE
    ''', (get_tenant_id(),))

    for row in cur.fetchall():
        findings.append({
            'blob_hash': row['blob_hash'],
            'reason': f"Orphan blob not referenced by any commit",
            'preview': row['preview']
        })

    cur.close()
    return findings


def patrol_broken_links() -> list:
    """Detect cross_references pointing to non-existent blobs."""
    findings = []
    cur = get_cursor()

    # Check source_blob references
    cur.execute('''
        SELECT cr.id, cr.source_blob, cr.target_blob, cr.link_type
        FROM cross_references cr
        LEFT JOIN blobs b ON cr.source_blob = b.blob_hash AND cr.tenant_id = b.tenant_id
        WHERE b.blob_hash IS NULL AND cr.tenant_id = %s
    ''', (get_tenant_id(),))

    for row in cur.fetchall():
        findings.append({
            'blob_hash': row['source_blob'],
            'reason': f"Broken link: source_blob does not exist (link_type: {row['link_type']})",
            'link_id': row['id'],
            'target_blob': row['target_blob']
        })

    # Check target_blob references
    cur.execute('''
        SELECT cr.id, cr.source_blob, cr.target_blob, cr.link_type
        FROM cross_references cr
        LEFT JOIN blobs b ON cr.target_blob = b.blob_hash AND cr.tenant_id = b.tenant_id
        WHERE b.blob_hash IS NULL AND cr.tenant_id = %s
    ''', (get_tenant_id(),))

    for row in cur.fetchall():
        findings.append({
            'blob_hash': row['target_blob'],
            'reason': f"Broken link: target_blob does not exist (link_type: {row['link_type']})",
            'link_id': row['id'],
            'source_blob': row['source_blob']
        })

    cur.close()
    return findings


def patrol_isolated_clusters() -> list:
    """Detect blobs with no trails and no cross_references (isolated memories)."""
    findings = []
    cur = get_cursor()

    # Find blobs with no outgoing/incoming trails AND no cross_references
    cur.execute('''
        SELECT b.blob_hash, substring(b.content, 1, 100) as preview
        FROM blobs b
        JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
        LEFT JOIN trails tr_out ON b.blob_hash = tr_out.source_blob
        LEFT JOIN trails tr_in ON b.blob_hash = tr_in.target_blob
        LEFT JOIN cross_references cr_out ON b.blob_hash = cr_out.source_blob AND b.tenant_id = cr_out.tenant_id
        LEFT JOIN cross_references cr_in ON b.blob_hash = cr_in.target_blob AND b.tenant_id = cr_in.tenant_id
        WHERE b.tenant_id = %s
          AND COALESCE(b.quarantined, FALSE) = FALSE
          AND tr_out.id IS NULL AND tr_in.id IS NULL
          AND cr_out.id IS NULL AND cr_in.id IS NULL
    ''', (get_tenant_id(),))

    for row in cur.fetchall():
        findings.append({
            'blob_hash': row['blob_hash'],
            'reason': "Isolated memory: no trails or cross-references",
            'preview': row['preview']
        })

    cur.close()
    return findings


def patrol_duplicate_embeddings(threshold: float = 0.02) -> list:
    """Detect near-identical embeddings (possible duplicates)."""
    findings = []
    cur = get_cursor()

    # Find pairs of blobs with very similar embeddings
    cur.execute('''
        SELECT b1.blob_hash as blob1, b2.blob_hash as blob2,
               b1.embedding <=> b2.embedding AS distance
        FROM blobs b1
        JOIN blobs b2 ON b1.blob_hash < b2.blob_hash AND b1.tenant_id = b2.tenant_id
        WHERE b1.embedding IS NOT NULL AND b2.embedding IS NOT NULL
          AND b1.tenant_id = %s
          AND COALESCE(b1.quarantined, FALSE) = FALSE
          AND COALESCE(b2.quarantined, FALSE) = FALSE
          AND b1.embedding <=> b2.embedding < %s
        LIMIT 50
    ''', (get_tenant_id(), threshold))

    seen = set()
    for row in cur.fetchall():
        # Only report the second blob (keep the older one)
        if row['blob2'] not in seen:
            findings.append({
                'blob_hash': row['blob2'],
                'reason': f"Near-duplicate of {row['blob1'][:12]}... (distance: {row['distance']:.4f})",
                'duplicate_of': row['blob1'],
                'distance': float(row['distance'])
            })
            seen.add(row['blob2'])

    cur.close()
    return findings


def patrol_stale_checkpoints(days: int = 30) -> list:
    """Detect session checkpoints older than threshold."""
    findings = []
    cur = get_cursor()

    try:
        cur.execute('''
            SELECT s.session_id, s.synced_at, s.status, substring(s.content, 1, 100) as preview
            FROM sessions s
            WHERE s.tenant_id = %s
              AND s.synced_at < NOW() - INTERVAL '%s days'
              AND s.status != 'archived'
        ''', (get_tenant_id(), days))

        for row in cur.fetchall():
            findings.append({
                'blob_hash': row['session_id'],  # Use session_id as identifier
                'reason': f"Stale checkpoint: {days}+ days old (synced: {row['synced_at']})",
                'status': row['status'],
                'preview': row['preview']
            })
    except Exception:
        # sessions table might not have synced_at column
        pass

    cur.close()
    return findings


# Define patrol routes
PATROL_ROUTES = [
    {'name': 'CENTROID_DRIFT', 'detector': patrol_centroid_drift},
    {'name': 'ORPHAN_BLOB', 'detector': patrol_orphan_blobs},
    {'name': 'BROKEN_LINK', 'detector': patrol_broken_links},
    {'name': 'ISOLATED_CLUSTER', 'detector': patrol_isolated_clusters},
    {'name': 'DUPLICATE_EMBEDDING', 'detector': patrol_duplicate_embeddings},
    {'name': 'STALE_CHECKPOINT', 'detector': patrol_stale_checkpoints},
]


@app.route('/v2/immune/patrol', methods=['POST'])
def immune_patrol():
    """Run immune system patrol - detect and quarantine anomalies.

    POST body (optional):
    - auto_quarantine: bool (default: True) - whether to quarantine findings
    - routes: list[str] - specific routes to run (default: all)
    """
    import uuid as uuid_module
    ensure_immune_tables()

    start_time = time.time()
    data = request.get_json() or {}
    auto_quarantine = data.get('auto_quarantine', True)
    route_filter = data.get('routes')  # Optional list of route names

    results = {
        'patrol_id': str(uuid_module.uuid4()),
        'started_at': datetime.utcnow().isoformat() + 'Z',
        'routes_checked': [],
        'quarantined': [],
        'findings': [],  # All findings regardless of quarantine
        'errors': []
    }

    # Log patrol start
    log_immune_action('PATROL_START', details={'patrol_id': results['patrol_id']})

    # Run each patrol route
    for route in PATROL_ROUTES:
        if route_filter and route['name'] not in route_filter:
            continue

        try:
            findings = route['detector']()
            results['routes_checked'].append({
                'route': route['name'],
                'findings_count': len(findings)
            })

            for finding in findings:
                results['findings'].append({
                    'route': route['name'],
                    **finding
                })

                if auto_quarantine and 'blob_hash' in finding:
                    try:
                        quarantine_blob(finding['blob_hash'], finding['reason'], route['name'])
                        results['quarantined'].append({
                            'blob_hash': finding['blob_hash'],
                            'route': route['name'],
                            'reason': finding['reason']
                        })
                    except Exception as qe:
                        results['errors'].append({
                            'route': route['name'],
                            'blob_hash': finding.get('blob_hash'),
                            'error': f"Quarantine failed: {str(qe)}"
                        })

        except Exception as e:
            results['errors'].append({'route': route['name'], 'error': str(e)})

    # Update branch health scores
    try:
        cur = get_cursor()
        cur.execute('''
            UPDATE branch_fingerprints SET last_patrol = NOW()
            WHERE tenant_id = %s
        ''', (get_tenant_id(),))
        get_db().commit()
        cur.close()
    except Exception:
        pass

    # Log patrol end
    results['duration_seconds'] = round(time.time() - start_time, 2)
    results['completed_at'] = datetime.utcnow().isoformat() + 'Z'
    log_immune_action('PATROL_END', details={
        'patrol_id': results['patrol_id'],
        'routes_checked': len(results['routes_checked']),
        'findings_count': len(results['findings']),
        'quarantined_count': len(results['quarantined']),
        'duration_seconds': results['duration_seconds']
    })

    return jsonify(results)


@app.route('/v2/immune/quarantine', methods=['GET'])
def list_quarantine():
    """List all quarantined memories awaiting human review."""
    ensure_immune_tables()

    limit = request.args.get('limit', 50, type=int)

    cur = get_cursor()
    cur.execute('''
        SELECT b.blob_hash, substring(b.content, 1, 300) as content_preview,
               b.quarantine_reason, b.quarantined_at, b.created_at as blob_created,
               c.message as commit_message
        FROM blobs b
        LEFT JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
        LEFT JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
        WHERE b.quarantined = TRUE AND b.tenant_id = %s
        ORDER BY b.quarantined_at DESC
        LIMIT %s
    ''', (get_tenant_id(), limit))

    quarantined = []
    for row in cur.fetchall():
        quarantined.append({
            'blob_hash': row['blob_hash'],
            'content_preview': row['content_preview'],
            'quarantine_reason': row['quarantine_reason'],
            'quarantined_at': row['quarantined_at'].isoformat() if row['quarantined_at'] else None,
            'blob_created_at': row['blob_created'].isoformat() if row['blob_created'] else None,
            'commit_message': row['commit_message']
        })

    cur.close()
    return jsonify({
        'count': len(quarantined),
        'quarantined': quarantined
    })


@app.route('/v2/immune/quarantine/<blob_hash>/resolve', methods=['POST'])
def resolve_quarantine(blob_hash):
    """Resolve a quarantined memory: reinstate or delete.

    POST body:
    - action: "reinstate" | "delete" (required)
    - reason: str (optional) - why reinstating/deleting
    """
    ensure_immune_tables()

    data = request.get_json() or {}
    action = data.get('action')
    reason = data.get('reason', '')

    if action not in ('reinstate', 'delete'):
        return jsonify({'error': 'action must be "reinstate" or "delete"'}), 400

    cur = get_cursor()
    db = get_db()

    # Verify blob exists and is quarantined
    cur.execute('''
        SELECT blob_hash, quarantine_reason FROM blobs
        WHERE blob_hash = %s AND tenant_id = %s AND quarantined = TRUE
    ''', (blob_hash, get_tenant_id()))

    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({'error': 'Blob not found or not quarantined'}), 404

    original_reason = row['quarantine_reason']

    try:
        if action == 'reinstate':
            # Clear quarantine flags
            cur.execute('''
                UPDATE blobs SET quarantined = FALSE, quarantined_at = NULL, quarantine_reason = NULL
                WHERE blob_hash = %s AND tenant_id = %s
            ''', (blob_hash, get_tenant_id()))
            db.commit()

            log_immune_action('REINSTATE', blob_hash, details={
                'original_reason': original_reason,
                'reinstate_reason': reason
            })

            cur.close()
            return jsonify({
                'status': 'reinstated',
                'blob_hash': blob_hash,
                'message': f"Memory reinstated: {reason}" if reason else "Memory reinstated"
            })

        else:  # delete
            # Delete blob and associated data
            cur.execute('DELETE FROM tree_entries WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, get_tenant_id()))
            cur.execute('DELETE FROM cross_references WHERE (source_blob = %s OR target_blob = %s) AND tenant_id = %s',
                       (blob_hash, blob_hash, get_tenant_id()))
            cur.execute('DELETE FROM tags WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, get_tenant_id()))

            # Delete from trails if table exists
            try:
                cur.execute('DELETE FROM trails WHERE source_blob = %s OR target_blob = %s', (blob_hash, blob_hash))
            except Exception:
                pass

            cur.execute('DELETE FROM blobs WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, get_tenant_id()))
            db.commit()

            log_immune_action('DELETE', blob_hash, details={
                'original_reason': original_reason,
                'delete_reason': reason
            })

            cur.close()
            return jsonify({
                'status': 'deleted',
                'blob_hash': blob_hash,
                'message': f"Memory permanently deleted: {reason}" if reason else "Memory permanently deleted"
            })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/immune/status', methods=['GET'])
def immune_status():
    """Get immune system health: quarantine counts, last patrol, branch health."""
    ensure_immune_tables()

    cur = get_cursor()

    # Get quarantine count
    cur.execute('''
        SELECT COUNT(*) as cnt FROM blobs
        WHERE quarantined = TRUE AND tenant_id = %s
    ''', (get_tenant_id(),))
    quarantine_count = cur.fetchone()['cnt']

    # Get last patrol info
    last_patrol = None
    last_patrol_findings = 0
    cur.execute('''
        SELECT details, created_at FROM immune_log
        WHERE action = 'PATROL_END' AND tenant_id = %s
        ORDER BY created_at DESC LIMIT 1
    ''', (get_tenant_id(),))
    row = cur.fetchone()
    if row:
        last_patrol = row['created_at'].isoformat() if row['created_at'] else None
        details = row['details'] or {}
        last_patrol_findings = details.get('findings_count', 0)

    # Get branch health
    branch_health = []
    try:
        cur.execute('''
            SELECT branch_name, health_score, last_patrol, last_updated,
                   EXTRACT(EPOCH FROM (NOW() - last_updated)) / 86400 as centroid_age_days
            FROM branch_fingerprints
            WHERE tenant_id = %s AND centroid IS NOT NULL
        ''', (get_tenant_id(),))

        for row in cur.fetchall():
            branch_health.append({
                'branch': row['branch_name'],
                'health_score': float(row['health_score']) if row['health_score'] else 1.0,
                'centroid_age_days': round(float(row['centroid_age_days']), 1) if row['centroid_age_days'] else None,
                'last_patrol': row['last_patrol'].isoformat() if row['last_patrol'] else None
            })
    except Exception:
        pass

    cur.close()

    return jsonify({
        'quarantine_count': quarantine_count,
        'last_patrol': last_patrol,
        'last_patrol_findings': last_patrol_findings,
        'branch_health': branch_health,
        'patrol_routes': [r['name'] for r in PATROL_ROUTES]
    })


@app.route('/v2/immune/log', methods=['GET'])
def immune_log():
    """Get immune system audit log."""
    limit = request.args.get('limit', 50, type=int)
    action_filter = request.args.get('action')  # Optional filter by action

    cur = get_cursor()

    if action_filter:
        cur.execute('''
            SELECT * FROM immune_log
            WHERE tenant_id = %s AND action = %s
            ORDER BY created_at DESC LIMIT %s
        ''', (get_tenant_id(), action_filter, limit))
    else:
        cur.execute('''
            SELECT * FROM immune_log
            WHERE tenant_id = %s
            ORDER BY created_at DESC LIMIT %s
        ''', (get_tenant_id(), limit))

    entries = []
    for row in cur.fetchall():
        entries.append({
            'id': str(row['id']),
            'action': row['action'],
            'blob_hash': row['blob_hash'],
            'patrol_type': row['patrol_type'],
            'details': row['details'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None
        })

    cur.close()
    return jsonify({'entries': entries, 'count': len(entries)})


# ==================== BRANCH FINGERPRINTS (Intelligent Routing) ====================

def ensure_fingerprints_table():
    """Create branch_fingerprints table if it doesn't exist."""
    cur = get_cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS branch_fingerprints (
            tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001',
            branch_name VARCHAR(255) NOT NULL,
            centroid vector(1536),
            commit_count INTEGER DEFAULT 0,
            last_updated TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (tenant_id, branch_name)
        )
    ''')
    get_db().commit()
    cur.close()


def compute_branch_centroid(branch_name: str, tenant_id: str = None) -> tuple:
    """Compute the centroid (average embedding) for a branch.
    Returns (centroid_vector, commit_count) or (None, 0) if no embeddings."""
    tenant_id = tenant_id or get_tenant_id()
    cur = get_cursor()
    
    # Get all embeddings for commits on this branch via walking from head
    cur.execute('''
        WITH RECURSIVE branch_commits AS (
            SELECT c.commit_hash, c.tree_hash, c.parent_hash
            FROM commits c
            JOIN branches b ON b.head_commit = c.commit_hash
            WHERE b.name = %s AND b.tenant_id = %s
            
            UNION ALL
            
            SELECT c.commit_hash, c.tree_hash, c.parent_hash
            FROM commits c
            JOIN branch_commits bc ON c.commit_hash = bc.parent_hash
            WHERE c.tenant_id = %s
        )
        SELECT DISTINCT b.embedding
        FROM branch_commits bc
        JOIN tree_entries te ON bc.tree_hash = te.tree_hash
        JOIN blobs b ON te.blob_hash = b.blob_hash
        WHERE b.embedding IS NOT NULL AND b.tenant_id = %s
    ''', (branch_name, tenant_id, tenant_id, tenant_id))
    
    embeddings = []
    for row in cur.fetchall():
        if row['embedding'] is not None:
            embeddings.append(row['embedding'])
    
    cur.close()
    
    if not embeddings:
        return None, 0
    
    # Compute average (centroid)
    import numpy as np
    centroid = np.mean(embeddings, axis=0).tolist()
    return centroid, len(embeddings)


def cosine_similarity(vec1, vec2) -> float:
    """Compute cosine similarity between two vectors."""
    import numpy as np
    a = np.array(vec1)
    b = np.array(vec2)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


@app.route('/v2/fingerprints/bootstrap', methods=['POST'])
def bootstrap_fingerprints():
    """Compute and store fingerprints (centroids) for all branches.
    Call this after cleaning up misplaced commits."""
    ensure_fingerprints_table()
    
    db = get_db()
    cur = get_cursor()
    
    try:
        # Get all branches
        cur.execute('SELECT name FROM branches WHERE tenant_id = %s', (get_tenant_id(),))
        branches = [row['name'] for row in cur.fetchall()]
        
        results = []
        for branch_name in branches:
            centroid, count = compute_branch_centroid(branch_name)
            
            if centroid:
                cur.execute('''
                    INSERT INTO branch_fingerprints (tenant_id, branch_name, centroid, commit_count, last_updated)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (tenant_id, branch_name) DO UPDATE SET
                        centroid = EXCLUDED.centroid,
                        commit_count = EXCLUDED.commit_count,
                        last_updated = NOW()
                ''', (get_tenant_id(), branch_name, centroid, count))
                results.append({'branch': branch_name, 'commits_with_embeddings': count, 'status': 'computed'})
            else:
                results.append({'branch': branch_name, 'commits_with_embeddings': 0, 'status': 'skipped_no_embeddings'})
        
        db.commit()
        cur.close()
        
        return jsonify({
            'status': 'bootstrapped',
            'branches': results,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    
    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/fingerprints', methods=['GET'])
def get_fingerprints():
    """Get all branch fingerprints."""
    ensure_fingerprints_table()
    
    cur = get_cursor()
    cur.execute('''
        SELECT branch_name, commit_count, last_updated
        FROM branch_fingerprints
        WHERE tenant_id = %s
        ORDER BY commit_count DESC
    ''', (get_tenant_id(),))
    
    fingerprints = []
    for row in cur.fetchall():
        fingerprints.append({
            'branch': row['branch_name'],
            'commit_count': row['commit_count'],
            'last_updated': row['last_updated'].isoformat() if row['last_updated'] else None
        })
    
    cur.close()
    return jsonify({'fingerprints': fingerprints, 'count': len(fingerprints)})


@app.route('/v2/commit/validate-routing', methods=['POST'])
def validate_commit_routing():
    """Check which branch best matches the given content.
    Use before committing to verify branch selection."""
    ensure_fingerprints_table()
    
    data = request.get_json() or {}
    content = data.get('content')
    requested_branch = data.get('branch', 'command-center')
    
    if not content:
        return jsonify({'error': 'Content required'}), 400
    
    # Generate embedding for the content
    content_str = json.dumps(content) if isinstance(content, dict) else str(content)
    embedding = generate_embedding(content_str)
    
    if not embedding:
        return jsonify({
            'status': 'skipped',
            'reason': 'Could not generate embedding',
            'suggested_branch': requested_branch
        })
    
    cur = get_cursor()
    
    # Get all fingerprints
    cur.execute('''
        SELECT branch_name, centroid, commit_count
        FROM branch_fingerprints
        WHERE tenant_id = %s AND centroid IS NOT NULL
    ''', (get_tenant_id(),))
    
    scores = []
    for row in cur.fetchall():
        if row['centroid'] is not None:
            similarity = cosine_similarity(embedding, row['centroid'])
            scores.append({
                'branch': row['branch_name'],
                'similarity': round(similarity, 4),
                'commit_count': row['commit_count']
            })
    
    cur.close()
    
    if not scores:
        return jsonify({
            'status': 'no_fingerprints',
            'suggested_branch': requested_branch,
            'message': 'No branch fingerprints computed yet. Run POST /v2/fingerprints/bootstrap first.'
        })
    
    # Sort by similarity
    scores.sort(key=lambda x: x['similarity'], reverse=True)
    best_match = scores[0]
    
    # Check if requested branch is the best match
    is_mismatch = best_match['branch'].lower() != requested_branch.lower()
    confidence_gap = best_match['similarity'] - scores[1]['similarity'] if len(scores) > 1 else 0
    
    return jsonify({
        'status': 'validated',
        'requested_branch': requested_branch,
        'suggested_branch': best_match['branch'],
        'is_mismatch': is_mismatch,
        'confidence': best_match['similarity'],
        'confidence_gap': round(confidence_gap, 4),
        'all_scores': scores[:5]  # Top 5 matches
    })


@app.route('/v2/admin/spawn-agent', methods=['POST'])
def spawn_agent():
    """Spawn a new agent with a task. Creates a task entry for agent coordination."""
    data = request.get_json() or {}
    agent_type = data.get('agentType', 'general')
    task_prompt = data.get('task')
    branch = data.get('branch', 'command-center')

    if not task_prompt:
        return jsonify({'error': 'Task prompt required'}), 400

    valid_agent_types = ['general', 'research', 'coding', 'analysis']
    if agent_type not in valid_agent_types:
        return jsonify({'error': f'Invalid agent type. Must be one of: {valid_agent_types}'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        # Generate a unique agent ID
        import uuid
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"

        # Create a task for the agent
        metadata = {
            'agent_type': agent_type,
            'agent_id': agent_id,
            'spawned_from': 'god-mode-dashboard'
        }

        cur.execute(
            '''INSERT INTO tasks (tenant_id, description, branch, assigned_to, status, priority, metadata)
               VALUES (%s, %s, %s, %s, 'open', 1, %s)
               RETURNING id, created_at''',
            (get_tenant_id(), task_prompt, branch, agent_id, json.dumps(metadata))
        )
        row = cur.fetchone()
        task_id = str(row['id'])
        created_at = str(row['created_at'])

        # Also commit this spawn event to memory
        spawn_record = {
            'event': 'agent_spawned',
            'agent_id': agent_id,
            'agent_type': agent_type,
            'task': task_prompt,
            'branch': branch,
            'task_id': task_id
        }
        content_str = json.dumps(spawn_record)
        blob_hash = compute_hash(content_str)
        now = datetime.utcnow().isoformat() + 'Z'

        cur.execute(
            '''INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (blob_hash) DO NOTHING''',
            (blob_hash, get_tenant_id(), content_str, 'agent_spawn', now, len(content_str))
        )

        db.commit()
        cur.close()

        return jsonify({
            'status': 'spawned',
            'agent_id': agent_id,
            'agent_type': agent_type,
            'task_id': task_id,
            'branch': branch,
            'task': task_prompt,
            'created_at': created_at
        }), 201

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


# =============================================================================
# HIPPOCAMPAL MEMORY STAGING (Boswell v4.0)
# Two-stage memory: working memory (bookmarks) + long-term (commits)
# Connected by consolidation cycle (sleep phase)
# =============================================================================

_hippocampal_tables_ensured = False

def ensure_hippocampal_tables():
    """Create hippocampal staging tables if they don't exist."""
    global _hippocampal_tables_ensured
    if _hippocampal_tables_ensured:
        return
    try:
        db = get_db()
        cur = db.cursor()
        migration_path = os.path.join(os.path.dirname(__file__), 'db', 'migrations', '013_hippocampal_staging.sql')
        if os.path.exists(migration_path):
            with open(migration_path, 'r') as f:
                cur.execute(f.read())
            db.commit()
        # Kill TTL: set expires_at = NULL for all active/cooling candidates
        # Steve's directive: "No expiry. Not a long expiry. No expiry."
        cur.execute("""
            UPDATE candidate_memories
            SET expires_at = NULL
            WHERE tenant_id = %s AND status IN ('active', 'cooling')
              AND expires_at IS NOT NULL
        """, (get_tenant_id(),))
        if cur.rowcount > 0:
            print(f"[TTL-KILL] Set expires_at = NULL for {cur.rowcount} candidates", file=sys.stderr)
        db.commit()

        cur.close()
        _hippocampal_tables_ensured = True
        print("[STARTUP] Hippocampal tables ensured", file=sys.stderr)
    except Exception as e:
        print(f"[STARTUP] Hippocampal tables check: {e}", file=sys.stderr)
        try:
            db.rollback()
        except:
            pass
        _hippocampal_tables_ensured = True  # Don't retry on every request


@app.route('/v2/bookmark', methods=['POST'])
def create_bookmark():
    """Stage a lightweight memory bookmark (working memory / RAM).
    Does NOT create blob/tree/commit. Does NOT touch centroids.
    Generates dual embeddings: content for search, context for auto-replay."""
    ensure_hippocampal_tables()
    data = request.get_json() or {}
    summary = data.get('summary')
    if not summary:
        return jsonify({'error': 'summary is required'}), 400

    branch = data.get('branch', 'command-center')
    content = data.get('content')
    message = data.get('message', summary[:100])
    tags = data.get('tags', [])
    salience = min(max(float(data.get('salience', 0.3)), 0.0), 1.0)
    salience_type = data.get('salience_type')
    source_instance = data.get('source_instance')
    context_str = data.get('context')  # working context for auto-replay
    ttl_days = data.get('ttl_days', 7)
    session_context = data.get('session_context')

    # Generate content embedding from summary + content
    embed_text = summary
    if content:
        content_str = json.dumps(content, default=str) if isinstance(content, dict) else str(content)
        embed_text = f"{summary}\n{content_str}"
    embedding = generate_embedding(embed_text)

    # Generate context embedding if context provided
    context_embedding = None
    if context_str:
        context_embedding = generate_embedding(context_str)

    import uuid
    candidate_id = str(uuid.uuid4())
    db = get_db()
    cur = get_cursor()

    try:
        # TTL is dead — expires_at = NULL. Bookmarks live until consolidated or explicitly cleaned.
        cur.execute("""
            INSERT INTO candidate_memories
                (id, tenant_id, branch, summary, content, message, tags, salience, salience_type,
                 embedding, context_embedding, status, source_instance, session_context, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s, NULL)
        """, (
            candidate_id, get_tenant_id(), branch, summary,
            json.dumps(content, default=str) if content else None,
            message, tags, salience, salience_type,
            embedding, context_embedding,
            source_instance,
            json.dumps(session_context, default=str) if session_context else None
        ))
        db.commit()

        # Fetch expires_at for response
        cur.execute("SELECT expires_at FROM candidate_memories WHERE id = %s", (candidate_id,))
        row = cur.fetchone()
        expires_at = str(row['expires_at']) if row else None
        cur.close()

        return jsonify({
            'status': 'bookmarked',
            'candidate_id': candidate_id,
            'branch': branch,
            'salience': salience,
            'expires_at': expires_at,
            'has_context': context_embedding is not None
        }), 201

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': f'Bookmark failed: {str(e)}'}), 500


@app.route('/v2/replay', methods=['POST'])
def record_replay():
    """Record topic recurrence — strengthens a bookmark's case for permanent storage."""
    ensure_hippocampal_tables()
    data = request.get_json() or {}
    candidate_id = data.get('candidate_id')
    keywords = data.get('keywords')
    session_id = data.get('session_id')
    replay_context = data.get('replay_context')

    if not candidate_id and not keywords:
        return jsonify({'error': 'candidate_id or keywords required'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        # Resolve candidate by ID or keyword search
        if candidate_id:
            cur.execute("""
                SELECT id, replay_count, expires_at, status
                FROM candidate_memories
                WHERE id = %s AND tenant_id = %s AND status IN ('active', 'cooling')
            """, (candidate_id, get_tenant_id()))
        else:
            # Semantic search against candidate embeddings
            query_embedding = generate_embedding(keywords)
            if not query_embedding:
                return jsonify({'error': 'Failed to generate embedding for keywords'}), 500
            cur.execute("""
                SELECT id, replay_count, expires_at, status,
                       embedding <=> %s::vector AS distance
                FROM candidate_memories
                WHERE tenant_id = %s AND status IN ('active', 'cooling') AND embedding IS NOT NULL
                ORDER BY distance LIMIT 1
            """, (query_embedding, get_tenant_id()))

        row = cur.fetchone()
        if not row:
            cur.close()
            return jsonify({'error': 'No matching active candidate found'}), 404

        cid = str(row['id'])
        new_replay_count = row['replay_count'] + 1

        # Increment replay_count
        cur.execute("""
            UPDATE candidate_memories SET replay_count = %s WHERE id = %s
        """, (new_replay_count, cid))

        # Near-expiry rescue: if replay_count >= 3 and expires within 48h, extend TTL by 3 days
        cur.execute("""
            UPDATE candidate_memories
            SET expires_at = expires_at + INTERVAL '3 days'
            WHERE id = %s AND replay_count >= 3
              AND expires_at < NOW() + INTERVAL '48 hours'
              AND expires_at > NOW()
        """, (cid,))

        # Log replay event
        import uuid
        cur.execute("""
            INSERT INTO replay_events (id, tenant_id, candidate_id, session_id, replay_context,
                                       similarity_score, fired, threshold_used, context_type)
            VALUES (%s, %s, %s, %s, %s, NULL, true, NULL, 'manual')
        """, (str(uuid.uuid4()), get_tenant_id(), cid, session_id, replay_context))

        db.commit()
        cur.close()

        return jsonify({
            'status': 'replayed',
            'candidate_id': cid,
            'replay_count': new_replay_count
        })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': f'Replay failed: {str(e)}'}), 500


@app.route('/v2/candidates', methods=['GET'])
def list_candidates():
    """View staging buffer — what's in working memory."""
    ensure_hippocampal_tables()
    branch = request.args.get('branch')
    status = request.args.get('status')
    limit = request.args.get('limit', 20, type=int)
    sort = request.args.get('sort', 'created_at')

    valid_sorts = {'salience': 'salience DESC', 'replay_count': 'replay_count DESC',
                   'created_at': 'created_at DESC', 'expires_at': 'expires_at ASC'}
    order_clause = valid_sorts.get(sort, 'created_at DESC')

    cur = get_cursor()
    sql = """
        SELECT id, branch, summary, salience, salience_type, replay_count,
               consolidation_score, status, source_instance,
               created_at, expires_at, promoted_at, promoted_commit_hash,
               (context_embedding IS NOT NULL) as has_context
        FROM candidate_memories
        WHERE tenant_id = %s
    """
    params = [get_tenant_id()]

    if branch:
        sql += " AND branch = %s"
        params.append(branch)
    if status:
        sql += " AND status = %s::candidate_status"
        params.append(status)

    sql += f" ORDER BY {order_clause} LIMIT %s"
    params.append(limit)

    cur.execute(sql, params)
    candidates = []
    for row in cur.fetchall():
        candidates.append({
            'id': str(row['id']),
            'branch': row['branch'],
            'summary': row['summary'],
            'salience': row['salience'],
            'salience_type': row['salience_type'],
            'replay_count': row['replay_count'],
            'consolidation_score': row['consolidation_score'],
            'status': row['status'],
            'source_instance': row['source_instance'],
            'has_context': row['has_context'],
            'created_at': str(row['created_at']) if row['created_at'] else None,
            'expires_at': str(row['expires_at']) if row['expires_at'] else None,
            'promoted_at': str(row['promoted_at']) if row['promoted_at'] else None,
            'promoted_commit_hash': row['promoted_commit_hash']
        })

    cur.close()
    return jsonify({'candidates': candidates, 'count': len(candidates)})


@app.route('/v2/candidates/decay-status', methods=['GET'])
def get_decay_status():
    """View expiring candidates — what's about to be forgotten."""
    ensure_hippocampal_tables()
    days = request.args.get('days', 2, type=int)
    cur = get_cursor()

    cur.execute("""
        SELECT id, branch, summary, salience, replay_count, status,
               created_at, expires_at,
               EXTRACT(EPOCH FROM (expires_at - NOW())) / 3600 as hours_remaining
        FROM candidate_memories
        WHERE tenant_id = %s AND status IN ('active', 'cooling')
          AND expires_at < NOW() + INTERVAL '%s days'
          AND expires_at > NOW()
        ORDER BY expires_at ASC
    """, (get_tenant_id(), days))

    expiring = []
    for row in cur.fetchall():
        expiring.append({
            'id': str(row['id']),
            'branch': row['branch'],
            'summary': row['summary'],
            'salience': row['salience'],
            'replay_count': row['replay_count'],
            'status': row['status'],
            'hours_remaining': round(float(row['hours_remaining']), 1),
            'expires_at': str(row['expires_at'])
        })

    cur.close()
    return jsonify({'expiring': expiring, 'count': len(expiring), 'within_days': days})


def _compute_connectivity(embedding, branch_name, cur):
    """Compute connectivity score for a candidate embedding.
    Cross-branch neighbors weighted 1.0, same-branch neighbors 0.1.
    Normalized to 0-1, capped at 10 neighbors.
    Uses batch query for branch lookups instead of N individual queries."""
    if embedding is None:
        return 0.0

    tenant_id = get_tenant_id()

    cur.execute("""
        SELECT b.blob_hash, te.name as branch_hint,
               b.embedding <=> %s::vector AS distance
        FROM blobs b
        JOIN tree_entries te ON b.blob_hash = te.blob_hash AND b.tenant_id = te.tenant_id
        WHERE b.embedding IS NOT NULL AND b.tenant_id = %s
          AND b.embedding <=> %s::vector < 0.4
        ORDER BY distance LIMIT 20
    """, (embedding, tenant_id, embedding))

    neighbors = cur.fetchall()
    if not neighbors:
        return 0.0

    # Batch lookup: get branch for all neighbor blob_hashes in one query
    blob_hashes = [row['blob_hash'] for row in neighbors]
    cur.execute("""
        SELECT DISTINCT ON (te.blob_hash) te.blob_hash, br.name as branch_name
        FROM tree_entries te
        JOIN commits c ON te.tree_hash = c.tree_hash AND te.tenant_id = c.tenant_id
        JOIN branches br ON br.head_commit IS NOT NULL AND br.tenant_id = c.tenant_id
        WHERE te.blob_hash = ANY(%s) AND te.tenant_id = %s
    """, (blob_hashes, tenant_id))

    branch_map = {row['blob_hash']: row['branch_name'] for row in cur.fetchall()}

    weighted_count = 0.0
    for row in neighbors:
        neighbor_branch = branch_map.get(row['blob_hash'], 'unknown')
        if neighbor_branch.lower() == branch_name.lower():
            weighted_count += 0.1  # Same-branch: low weight
        else:
            weighted_count += 1.0  # Cross-branch: full weight

    # Normalize: cap at 10 neighbors worth of weight
    return min(weighted_count / 10.0, 1.0)


def _promote_candidate_to_commit(candidate_row, cur, db):
    """Promote a candidate memory to a permanent commit.
    Reuses existing commit-chain logic. Copies embedding (zero API cost)."""
    import uuid

    content = candidate_row['content']
    if content is None:
        content = json.dumps({"summary": candidate_row['summary'], "source": "hippocampal_promotion"})
    elif isinstance(content, dict):
        content = json.dumps(content, default=str)

    blob_hash = compute_hash(content)
    branch = candidate_row['branch']
    message = candidate_row['message'] or f"Promoted: {candidate_row['summary'][:80]}"
    now = datetime.utcnow().isoformat() + 'Z'
    tags = candidate_row['tags'] or []

    # Insert blob (copy embedding from candidate — zero API cost)
    cur.execute(
        '''INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size, embedding)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (blob_hash) DO NOTHING''',
        (blob_hash, get_tenant_id(), content, 'memory', now, len(content),
         candidate_row['embedding'])
    )

    # Create tree entry
    tree_hash = compute_hash(f"{branch}:{blob_hash}:{now}")
    cur.execute(
        '''INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
           VALUES (%s, %s, %s, %s, %s)''',
        (get_tenant_id(), tree_hash, message[:100], blob_hash, 'memory')
    )

    # Get parent commit
    cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s',
                (branch, get_tenant_id()))
    branch_row = cur.fetchone()
    if branch_row:
        branch = branch_row['name']
        parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
    else:
        cur.execute(
            '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
               VALUES (%s, %s, %s, %s)''',
            (get_tenant_id(), branch, 'GENESIS', now)
        )
        parent_hash = None

    # Create commit
    commit_data = f"{tree_hash}:{parent_hash}:{message}:{now}"
    commit_hash = compute_hash(commit_data)
    cur.execute(
        '''INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)''',
        (commit_hash, get_tenant_id(), tree_hash, parent_hash, 'consolidation', message, now)
    )

    # Update branch HEAD
    cur.execute(
        'UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s',
        (commit_hash, branch, get_tenant_id())
    )

    # Insert tags
    for tag in tags:
        tag_str = tag if isinstance(tag, str) else str(tag)
        try:
            cur.execute(
                '''INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
                   VALUES (%s, %s, %s, %s)''',
                (get_tenant_id(), blob_hash, tag_str, now)
            )
        except Exception:
            pass

    # Update candidate status
    cur.execute("""
        UPDATE candidate_memories
        SET status = 'promoted', promoted_at = NOW(), promoted_commit_hash = %s
        WHERE id = %s
    """, (commit_hash, str(candidate_row['id'])))

    return commit_hash, blob_hash


@app.route('/v2/consolidate', methods=['POST'])
def run_consolidation():
    """Sleep phase: score and promote top candidates to permanent memory."""
    ensure_hippocampal_tables()
    data = request.get_json() or {}
    max_promotions = data.get('max_promotions', 10)
    dry_run = data.get('dry_run', False)
    filter_branch = data.get('branch')
    min_score = data.get('min_score', 0.0)
    cycle_type = data.get('cycle_type', 'manual')

    import math
    start_time = time.time()

    db = get_db()
    cur = get_cursor()

    try:
        # Step 1: Transition stale candidates to cooling
        cur.execute("""
            UPDATE candidate_memories
            SET status = 'cooling'
            WHERE tenant_id = %s AND status = 'active'
              AND created_at < NOW() - INTERVAL '3 days'
        """, (get_tenant_id(),))
        cooled = cur.rowcount

        # Step 2: Expire dead candidates (past TTL — only if expires_at is set)
        cur.execute("""
            UPDATE candidate_memories
            SET status = 'expired'
            WHERE tenant_id = %s AND status IN ('active', 'cooling')
              AND expires_at IS NOT NULL AND expires_at < NOW()
        """, (get_tenant_id(),))
        expired = cur.rowcount

        # Step 3: Load all active/cooling candidates
        filter_sql = ""
        filter_params = [get_tenant_id()]
        if filter_branch:
            filter_sql = " AND branch = %s"
            filter_params.append(filter_branch)

        cur.execute(f"""
            SELECT id, branch, summary, content, message, tags, salience,
                   replay_count, embedding, status
            FROM candidate_memories
            WHERE tenant_id = %s AND status IN ('active', 'cooling'){filter_sql}
        """, filter_params)

        candidates = cur.fetchall()

        # Step 4: Compute consolidation scores
        scored = []
        score_updates = []
        for c in candidates:
            connectivity = _compute_connectivity(c['embedding'], c['branch'], cur)
            score = c['salience'] * (1 + math.log(c['replay_count'] + 1)) * (1 + connectivity)

            score_updates.append((score, str(c['id'])))

            if score >= min_score:
                scored.append({
                    'candidate': c,
                    'score': score,
                    'connectivity': connectivity
                })

        # Batch update all consolidation scores
        if score_updates:
            from psycopg2.extras import execute_values
            execute_values(cur, """
                UPDATE candidate_memories AS cm
                SET consolidation_score = v.score
                FROM (VALUES %s) AS v(score, id)
                WHERE cm.id = v.id::uuid
            """, score_updates)

        # Step 5: Rank and take top N
        scored.sort(key=lambda x: x['score'], reverse=True)
        to_promote = scored[:max_promotions]

        promoted_commits = []
        if not dry_run:
            # Step 6: Promote winners
            affected_branches = set()
            for item in to_promote:
                commit_hash, blob_hash = _promote_candidate_to_commit(item['candidate'], cur, db)
                promoted_commits.append(commit_hash)
                affected_branches.add(item['candidate']['branch'])

            # Step 7: Hard-delete expired candidates older than 30 days
            cur.execute("""
                DELETE FROM candidate_memories
                WHERE tenant_id = %s AND status = 'expired'
                  AND expires_at < NOW() - INTERVAL '30 days'
            """, (get_tenant_id(),))
            hard_deleted = cur.rowcount

            db.commit()

            # Step 8: Refresh centroids for affected branches
            for br in affected_branches:
                try:
                    ensure_fingerprints_table()
                    centroid, count = compute_branch_centroid(br)
                    if centroid:
                        fp_cur = get_cursor()
                        fp_cur.execute("""
                            INSERT INTO branch_fingerprints (tenant_id, branch_name, centroid, commit_count, last_updated)
                            VALUES (%s, %s, %s, %s, NOW())
                            ON CONFLICT (tenant_id, branch_name) DO UPDATE
                            SET centroid = EXCLUDED.centroid, commit_count = EXCLUDED.commit_count,
                                last_updated = NOW()
                        """, (get_tenant_id(), br, centroid, count))
                        get_db().commit()
                        fp_cur.close()
                except Exception as e:
                    print(f"[CONSOLIDATION] Centroid refresh failed for {br}: {e}", file=sys.stderr)
        else:
            hard_deleted = 0

        duration_ms = int((time.time() - start_time) * 1000)

        # Log to consolidation_log
        import uuid
        top_score = scored[0]['score'] if scored else None
        cur.execute("""
            INSERT INTO consolidation_log
                (id, tenant_id, cycle_type, candidates_evaluated, candidates_promoted,
                 candidates_expired, top_score, threshold_used, promoted_commits,
                 duration_ms, completed_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """, (
            str(uuid.uuid4()), get_tenant_id(), cycle_type,
            len(candidates), len(promoted_commits) if not dry_run else 0,
            expired, top_score, min_score, promoted_commits,
            duration_ms, json.dumps({'dry_run': dry_run, 'cooled': cooled, 'hard_deleted': hard_deleted})
        ))
        db.commit()
        cur.close()

        report = {
            'status': 'dry_run' if dry_run else 'consolidated',
            'candidates_evaluated': len(candidates),
            'candidates_promoted': len(promoted_commits) if not dry_run else 0,
            'candidates_expired': expired,
            'candidates_cooled': cooled,
            'top_scores': [{'id': str(s['candidate']['id']), 'summary': s['candidate']['summary'][:80],
                           'score': round(s['score'], 4), 'connectivity': round(s['connectivity'], 4)}
                          for s in scored[:max_promotions]],
            'promoted_commits': promoted_commits,
            'duration_ms': duration_ms
        }
        if not dry_run:
            report['hard_deleted'] = hard_deleted

        return jsonify(report)

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': f'Consolidation failed: {str(e)}'}), 500


@app.route('/v2/candidates/cleanup', methods=['POST'])
def cleanup_candidates():
    """Expire past-TTL candidates and hard-delete old expired ones.

    FROZEN by sacred directive (2026-02-09). No candidates may expire or be deleted.
    See Boswell commit bf4b68532a81 on branch boswell.
    Lift condition: Steve explicitly re-enables after architecture review.
    """
    # SACRED DIRECTIVE: Candidate cleanup frozen (2026-02-09)
    return jsonify({
        'status': 'frozen',
        'reason': 'Sacred directive bf4b68532a81 - candidate cleanup disabled until architecture review',
        'expired': 0,
        'hard_deleted': 0,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

    # --- ORIGINAL CLEANUP LOGIC (frozen) ---
    ensure_hippocampal_tables()
    db = get_db()
    cur = get_cursor()

    try:
        # Expire past-TTL (only if expires_at is set — NULL means no expiry)
        cur.execute("""
            UPDATE candidate_memories
            SET status = 'expired'
            WHERE tenant_id = %s AND status IN ('active', 'cooling')
              AND expires_at IS NOT NULL AND expires_at < NOW()
        """, (get_tenant_id(),))
        expired = cur.rowcount

        # Hard-delete expired > 30 days
        cur.execute("""
            DELETE FROM candidate_memories
            WHERE tenant_id = %s AND status = 'expired'
              AND expires_at IS NOT NULL AND expires_at < NOW() - INTERVAL '30 days'
        """, (get_tenant_id(),))
        hard_deleted = cur.rowcount

        db.commit()
        cur.close()

        return jsonify({
            'status': 'cleaned',
            'expired': expired,
            'hard_deleted': hard_deleted,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


def ensure_discovery_queue_table():
    """Create discovery_queue table if it doesn't exist."""
    cur = get_cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS discovery_queue (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(100) NOT NULL DEFAULT 'default',
            blob_hash VARCHAR(64) NOT NULL,
            orphan_score FLOAT NOT NULL,
            value_score FLOAT NOT NULL,
            branch VARCHAR(255),
            preview TEXT,
            commit_message TEXT,
            surfaced_at TIMESTAMPTZ DEFAULT NOW(),
            consumed_by VARCHAR(255),
            consumed_at TIMESTAMPTZ,
            status VARCHAR(20) DEFAULT 'pending',
            UNIQUE(tenant_id, blob_hash)
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_discovery_queue_status ON discovery_queue(status, value_score DESC)')
    get_db().commit()
    cur.close()


@app.route('/v2/discovery/pass', methods=['POST'])
def discovery_pass():
    """Score orphaned blobs and populate discovery queue."""
    ensure_discovery_queue_table()

    db = get_db()
    cur = get_cursor()

    try:
        # 1. Find blobs with zero or few trails + links
        # Note: commits table has no 'branch' column, so we get branch from
        # cross_references or default to 'unknown'. For scoring we use the
        # branch_fingerprints approach: find which branch HEAD chain includes each commit.
        # Pragmatic approach: LEFT JOIN branches where commit is HEAD (catches latest),
        # fall back to 'unknown' for older commits.
        cur.execute('''
            WITH blob_connectivity AS (
                SELECT DISTINCT ON (b.blob_hash)
                       b.blob_hash, b.content,
                       COALESCE(t.trail_count, 0) as trail_count,
                       COALESCE(cr.link_count, 0) as link_count,
                       c.message as commit_message,
                       COALESCE(br.name, 'unknown') as branch
                FROM blobs b
                JOIN tree_entries te ON b.blob_hash = te.blob_hash AND b.tenant_id = te.tenant_id
                JOIN commits c ON te.tree_hash = c.tree_hash AND te.tenant_id = c.tenant_id
                LEFT JOIN branches br ON br.head_commit = c.commit_hash AND br.tenant_id = c.tenant_id
                LEFT JOIN (
                    SELECT source_blob as blob, COUNT(*) as trail_count FROM trails
                    WHERE tenant_id = %s GROUP BY source_blob
                    UNION ALL
                    SELECT target_blob, COUNT(*) FROM trails
                    WHERE tenant_id = %s GROUP BY target_blob
                ) t ON b.blob_hash = t.blob
                LEFT JOIN (
                    SELECT source_blob as blob, COUNT(*) as link_count FROM cross_references
                    WHERE tenant_id = %s GROUP BY source_blob
                    UNION ALL
                    SELECT target_blob, COUNT(*) FROM cross_references
                    WHERE tenant_id = %s GROUP BY target_blob
                ) cr ON b.blob_hash = cr.blob
                WHERE b.tenant_id = %s
                  AND b.embedding IS NOT NULL
                  AND COALESCE(b.quarantined, FALSE) = FALSE
            )
            SELECT blob_hash, content, commit_message, branch,
                   trail_count, link_count,
                   1.0 / (1.0 + trail_count + link_count) as orphan_score
            FROM blob_connectivity
            WHERE trail_count + link_count < 3
            ORDER BY orphan_score DESC, LENGTH(content) DESC
        ''', (get_tenant_id(),) * 5)

        candidates = cur.fetchall()

        # 2. Value filter — skip noise
        scored = []
        for c in candidates:
            content_len = len(c['content'] or '')
            branch = c['branch']

            # Branch priority
            branch_weight = {
                'tint-atlanta': 1.0, 'iris': 1.0, 'tint-empire': 0.9,
                'family': 0.7, 'boswell': 0.6, 'thalamus': 0.5,
                'command-center': 0.3, 'viscera': 0.2
            }.get(branch, 0.5)

            # Content substance (longer = more likely substantive)
            content_weight = min(content_len / 500.0, 1.0)

            # Skip very short commits (likely noise)
            if content_len < 50:
                continue

            value = float(c['orphan_score']) * branch_weight * content_weight
            scored.append({
                'blob_hash': c['blob_hash'],
                'content': c['content'],
                'commit_message': c['commit_message'],
                'branch': c['branch'],
                'orphan_score': float(c['orphan_score']),
                'value_score': value
            })

        # 3. Take top 20 and upsert into discovery_queue
        scored.sort(key=lambda x: x['value_score'], reverse=True)
        top_orphans = scored[:20]

        for orphan in top_orphans:
            cur.execute('''
                INSERT INTO discovery_queue
                    (tenant_id, blob_hash, orphan_score, value_score, branch,
                     preview, commit_message, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
                ON CONFLICT (tenant_id, blob_hash) DO UPDATE
                SET orphan_score = EXCLUDED.orphan_score,
                    value_score = EXCLUDED.value_score,
                    surfaced_at = NOW(),
                    status = 'pending'
            ''', (get_tenant_id(), orphan['blob_hash'], orphan['orphan_score'],
                  orphan['value_score'], orphan['branch'],
                  (orphan['content'] or '')[:200], orphan['commit_message']))

        db.commit()
        cur.close()
        return jsonify({
            'status': 'discovery_complete',
            'candidates_scanned': len(candidates),
            'orphans_queued': len(top_orphans)
        })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': f'Discovery pass failed: {str(e)}'}), 500


@app.route('/v2/nightly', methods=['POST'])
def nightly_maintenance():
    """Composite nightly maintenance for ALL tenants: trails + candidates + consolidation + discovery."""
    start_time = time.time()
    all_results = {}

    # Get all active tenants
    try:
        db = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, name FROM tenants")
        tenants = cur.fetchall()
        cur.close()
        db.close()
    except Exception as e:
        return jsonify({'error': f'Failed to fetch tenants: {str(e)}'}), 500

    for tenant in tenants:
        tenant_id = str(tenant['id'])
        tenant_name = tenant.get('name', tenant_id[:8])
        push_tenant_override(tenant_id)
        try:
            results = {}

            # Step 1: Trail decay
            try:
                with app.test_request_context(method='POST', path='/v2/trails/decay'):
                    g.mcp_auth = {'tenant_id': tenant_id, 'source': 'nightly_maintenance'}
                    trail_result = decay_trails()
                    if isinstance(trail_result, tuple):
                        results['trail_decay'] = trail_result[0].get_json() if hasattr(trail_result[0], 'get_json') else trail_result[0]
                    elif hasattr(trail_result, 'get_json'):
                        results['trail_decay'] = trail_result.get_json()
                    else:
                        results['trail_decay'] = trail_result
            except Exception as e:
                results['trail_decay'] = {'error': str(e)}

            # Step 2: Candidate cleanup
            try:
                with app.test_request_context(method='POST', path='/v2/candidates/cleanup',
                                               content_type='application/json', json={}):
                    g.mcp_auth = {'tenant_id': tenant_id, 'source': 'nightly_maintenance'}
                    cleanup_result = cleanup_candidates()
                    if isinstance(cleanup_result, tuple):
                        results['candidate_cleanup'] = cleanup_result[0].get_json() if hasattr(cleanup_result[0], 'get_json') else cleanup_result[0]
                    elif hasattr(cleanup_result, 'get_json'):
                        results['candidate_cleanup'] = cleanup_result.get_json()
                    else:
                        results['candidate_cleanup'] = cleanup_result
            except Exception as e:
                results['candidate_cleanup'] = {'error': str(e)}

            # Step 3: Consolidation (promote top 10)
            try:
                with app.test_request_context(method='POST', path='/v2/consolidate',
                                               content_type='application/json',
                                               json={'max_promotions': 10, 'cycle_type': 'nightly'}):
                    g.mcp_auth = {'tenant_id': tenant_id, 'source': 'nightly_maintenance'}
                    consol_result = run_consolidation()
                    if isinstance(consol_result, tuple):
                        results['consolidation'] = consol_result[0].get_json() if hasattr(consol_result[0], 'get_json') else consol_result[0]
                    elif hasattr(consol_result, 'get_json'):
                        results['consolidation'] = consol_result.get_json()
                    else:
                        results['consolidation'] = consol_result
            except Exception as e:
                results['consolidation'] = {'error': str(e)}

            # Step 4: Discovery pass (surface orphaned memories)
            try:
                with app.test_request_context(method='POST', path='/v2/discovery/pass'):
                    g.mcp_auth = {'tenant_id': tenant_id, 'source': 'nightly_maintenance'}
                    discovery_result = discovery_pass()
                    if isinstance(discovery_result, tuple):
                        results['discovery_pass'] = discovery_result[0].get_json() if hasattr(discovery_result[0], 'get_json') else discovery_result[0]
                    elif hasattr(discovery_result, 'get_json'):
                        results['discovery_pass'] = discovery_result.get_json()
                    else:
                        results['discovery_pass'] = discovery_result
            except Exception as e:
                results['discovery_pass'] = {'error': str(e)}

            all_results[tenant_name] = results
        finally:
            pop_tenant_override()

    duration_ms = int((time.time() - start_time) * 1000)

    return jsonify({
        'status': 'nightly_complete',
        'tenants_processed': len(tenants),
        'results': all_results,
        'duration_ms': duration_ms,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


# =============================================================================
# PASSKEY AUTHENTICATION ENDPOINTS (WebAuthn / Face ID)
# Author: CC2 - Swarm task beta-4
# =============================================================================

from passkey_auth import (
    generate_registration_options,
    generate_authentication_options,
    verify_registration_response,
    verify_authentication_response,
    generate_session_token,
    hash_session_token,
    base64url_to_bytes
)

GODMODE_PASSWORD = os.environ.get('GODMODE_PASSWORD')


def get_session_from_request():
    """Extract and validate session from request."""
    # Check Authorization header
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    else:
        # Check cookie
        token = request.cookies.get('boswell_session')

    if not token:
        return None

    token_hash = hash_session_token(token)
    cur = get_cursor()
    cur.execute(
        '''SELECT user_id, expires_at FROM passkey_sessions
           WHERE token = %s AND expires_at > NOW()''',
        (token_hash,)
    )
    row = cur.fetchone()
    cur.close()

    if row:
        return {'user_id': row['user_id'], 'expires_at': str(row['expires_at'])}
    return None


def require_auth(f):
    """Decorator to require authentication."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        session = get_session_from_request()
        if not session:
            # Also allow GODMODE_PASSWORD for backward compatibility
            if request.headers.get('X-Godmode-Password') == GODMODE_PASSWORD:
                return f(*args, **kwargs)
            return jsonify({'error': 'Authentication required'}), 401
        g.current_user = session['user_id']
        return f(*args, **kwargs)
    return decorated


@app.route('/auth/register/options', methods=['POST'])
def auth_register_options():
    """
    Start passkey registration.
    First user to register becomes admin.
    Requires GODMODE_PASSWORD for initial setup.
    """
    # Check if any credentials exist
    cur = get_cursor()
    cur.execute('SELECT COUNT(*) as count FROM passkey_credentials')
    count = cur.fetchone()['count']

    # If credentials exist, require authentication
    if count > 0:
        session = get_session_from_request()
        if not session and request.headers.get('X-Godmode-Password') != GODMODE_PASSWORD:
            cur.close()
            return jsonify({'error': 'Authentication required to add new passkey'}), 401

    data = request.get_json() or {}
    user_id = data.get('user_id', 'steve')  # Default to steve for single-user mode
    user_name = data.get('user_name', user_id)
    display_name = data.get('display_name', 'Steve Krontz')

    # Get existing credentials for this user
    cur.execute(
        'SELECT credential_id FROM passkey_credentials WHERE user_id = %s',
        (user_id,)
    )
    existing = [bytes(row['credential_id']) for row in cur.fetchall()]

    # Generate options
    options, challenge = generate_registration_options(
        user_id=user_id,
        user_name=user_name,
        user_display_name=display_name,
        existing_credentials=existing
    )

    # Store challenge
    cur.execute(
        '''INSERT INTO passkey_challenges (user_id, challenge, type)
           VALUES (%s, %s, 'registration')''',
        (user_id, challenge)
    )
    get_db().commit()
    cur.close()

    return jsonify(options)


@app.route('/auth/register/verify', methods=['POST'])
def auth_register_verify():
    """Verify passkey registration and store credential."""
    data = request.get_json() or {}
    credential = data.get('credential')
    user_id = data.get('user_id', 'steve')
    friendly_name = data.get('friendly_name', 'My Passkey')

    if not credential:
        return jsonify({'error': 'credential is required'}), 400

    cur = get_cursor()
    db = get_db()

    try:
        # Get the challenge
        cur.execute(
            '''SELECT challenge FROM passkey_challenges
               WHERE user_id = %s AND type = 'registration'
               AND expires_at > NOW()
               ORDER BY created_at DESC LIMIT 1''',
            (user_id,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'No valid challenge found. Start registration again.'}), 400

        expected_challenge = bytes(row['challenge'])

        # Verify the registration
        result = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge
        )

        # Store the credential
        cur.execute(
            '''INSERT INTO passkey_credentials
               (user_id, credential_id, public_key, device_type, backed_up, transports, friendly_name)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id''',
            (
                user_id,
                result['credential_id'],
                result['public_key'],
                result['device_type'],
                result['backed_up'],
                result.get('transports', ['internal']),
                friendly_name
            )
        )

        # Clean up used challenge
        cur.execute(
            "DELETE FROM passkey_challenges WHERE user_id = %s AND type = 'registration'",
            (user_id,)
        )

        db.commit()
        cur.close()

        return jsonify({
            'status': 'registered',
            'user_id': user_id,
            'friendly_name': friendly_name
        })

    except ValueError as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/auth/login/options', methods=['POST'])
def auth_login_options():
    """Start passkey authentication."""
    data = request.get_json() or {}
    user_id = data.get('user_id', 'steve')

    cur = get_cursor()

    # Get user's credentials
    cur.execute(
        '''SELECT credential_id, transports FROM passkey_credentials
           WHERE user_id = %s''',
        (user_id,)
    )
    credentials = cur.fetchall()

    if not credentials:
        cur.close()
        return jsonify({'error': 'No passkeys registered. Please register first.'}), 404

    # Generate options
    options, challenge = generate_authentication_options(credentials)

    # Store challenge
    cur.execute(
        '''INSERT INTO passkey_challenges (user_id, challenge, type)
           VALUES (%s, %s, 'authentication')''',
        (user_id, challenge)
    )
    get_db().commit()
    cur.close()

    return jsonify(options)


@app.route('/auth/login/verify', methods=['POST'])
def auth_login_verify():
    """Verify passkey authentication and create session."""
    data = request.get_json() or {}
    credential = data.get('credential')
    user_id = data.get('user_id', 'steve')

    if not credential:
        return jsonify({'error': 'credential is required'}), 400

    cur = get_cursor()
    db = get_db()

    try:
        # Get the challenge
        cur.execute(
            '''SELECT challenge FROM passkey_challenges
               WHERE user_id = %s AND type = 'authentication'
               AND expires_at > NOW()
               ORDER BY created_at DESC LIMIT 1''',
            (user_id,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'No valid challenge found. Start login again.'}), 400

        expected_challenge = bytes(row['challenge'])

        # Get the stored credential
        credential_id = base64url_to_bytes(credential.get('id', ''))
        cur.execute(
            '''SELECT * FROM passkey_credentials
               WHERE user_id = %s AND credential_id = %s''',
            (user_id, credential_id)
        )
        stored_credential = cur.fetchone()

        if not stored_credential:
            return jsonify({'error': 'Credential not found'}), 404

        # Verify the authentication
        verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            stored_credential=stored_credential
        )

        # Update counter and last_used
        cur.execute(
            '''UPDATE passkey_credentials
               SET counter = counter + 1, last_used_at = NOW()
               WHERE id = %s''',
            (stored_credential['id'],)
        )

        # Create session
        session_token = generate_session_token()
        token_hash = hash_session_token(session_token)

        cur.execute(
            '''INSERT INTO passkey_sessions (user_id, token, user_agent, ip_address)
               VALUES (%s, %s, %s, %s)
               RETURNING expires_at''',
            (
                user_id,
                token_hash,
                request.headers.get('User-Agent', '')[:500],
                request.remote_addr
            )
        )
        expires_at = cur.fetchone()['expires_at']

        # Clean up used challenge
        cur.execute(
            "DELETE FROM passkey_challenges WHERE user_id = %s AND type = 'authentication'",
            (user_id,)
        )

        db.commit()
        cur.close()

        response = jsonify({
            'status': 'authenticated',
            'user_id': user_id,
            'expires_at': str(expires_at)
        })

        # Set cookie for browser use
        response.set_cookie(
            'boswell_session',
            session_token,
            httponly=True,
            secure=True,
            samesite='Lax',
            max_age=7 * 24 * 60 * 60  # 7 days
        )

        # Also return token in body for API use
        response_data = response.get_json()
        response_data['token'] = session_token
        response.set_data(json.dumps(response_data))

        return response

    except ValueError as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/auth/session', methods=['GET'])
def auth_session():
    """Check current session status."""
    session = get_session_from_request()
    if session:
        return jsonify({
            'authenticated': True,
            'user_id': session['user_id'],
            'expires_at': session['expires_at']
        })
    return jsonify({'authenticated': False}), 401


@app.route('/auth/logout', methods=['POST'])
def auth_logout():
    """Destroy current session."""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    else:
        token = request.cookies.get('boswell_session')

    if token:
        token_hash = hash_session_token(token)
        cur = get_cursor()
        cur.execute('DELETE FROM passkey_sessions WHERE token = %s', (token_hash,))
        get_db().commit()
        cur.close()

    response = jsonify({'status': 'logged_out'})
    response.delete_cookie('boswell_session')
    return response


@app.route('/auth/passkeys', methods=['GET'])
@require_auth
def list_passkeys():
    """List all registered passkeys for current user."""
    user_id = g.get('current_user', 'steve')
    cur = get_cursor()
    cur.execute(
        '''SELECT id, friendly_name, device_type, created_at, last_used_at
           FROM passkey_credentials WHERE user_id = %s
           ORDER BY created_at DESC''',
        (user_id,)
    )
    passkeys = cur.fetchall()
    cur.close()

    return jsonify({
        'passkeys': [
            {
                'id': str(p['id']),
                'friendly_name': p['friendly_name'],
                'device_type': p['device_type'],
                'created_at': str(p['created_at']),
                'last_used_at': str(p['last_used_at']) if p['last_used_at'] else None
            }
            for p in passkeys
        ]
    })


@app.route('/auth/password', methods=['POST'])
def auth_password():
    """
    Password fallback authentication.
    Uses GODMODE_PASSWORD for single-user mode.
    """
    data = request.get_json() or {}
    password = data.get('password')

    if not password:
        return jsonify({'error': 'password is required'}), 400

    if password != GODMODE_PASSWORD:
        return jsonify({'error': 'Invalid password'}), 401

    user_id = 'steve'  # Single-user mode

    # Create session
    cur = get_cursor()
    db = get_db()

    session_token = generate_session_token()
    token_hash = hash_session_token(session_token)

    cur.execute(
        '''INSERT INTO passkey_sessions (user_id, token, user_agent, ip_address)
           VALUES (%s, %s, %s, %s)
           RETURNING expires_at''',
        (
            user_id,
            token_hash,
            request.headers.get('User-Agent', '')[:500],
            request.remote_addr
        )
    )
    expires_at = cur.fetchone()['expires_at']
    db.commit()
    cur.close()

    response = jsonify({
        'status': 'authenticated',
        'user_id': user_id,
        'token': session_token,
        'expires_at': str(expires_at)
    })

    response.set_cookie(
        'boswell_session',
        session_token,
        httponly=True,
        secure=True,
        samesite='Lax',
        max_age=7 * 24 * 60 * 60
    )

    return response


# =============================================================================
# USER REGISTRATION (W1P1 - CC1)
# =============================================================================

from auth.registration import init_registration
registration_bp = init_registration(get_db, get_cursor)
app.register_blueprint(registration_bp)


# =============================================================================
# USER LOGIN (W1P2 - CC1) - UNBLOCKS CC3
# =============================================================================

from auth.login import init_login
login_bp = init_login(get_db, get_cursor)
app.register_blueprint(login_bp)


# =============================================================================
# API KEY MANAGEMENT (W1P3 - CC1)
# =============================================================================

from auth.api_keys import init_api_keys
api_keys_bp = init_api_keys(get_db, get_cursor)
app.register_blueprint(api_keys_bp)


# =============================================================================
# PASSWORD RESET (W1P4 - CC1)
# =============================================================================

from auth.password_reset import init_password_reset
password_reset_bp = init_password_reset(get_db, get_cursor)
app.register_blueprint(password_reset_bp)


# =============================================================================
# USER PROFILE ENDPOINT (Self-Service Onboarding)
# =============================================================================

@app.route('/v2/me', methods=['GET'])
def get_current_user():
    """
    Get current user's account info including API key.

    Requires JWT authentication.
    Returns user details, status, plan, and decrypted API key for dashboard display.
    """
    from auth import verify_jwt, decrypt_api_key

    # Require authentication (JWT or session token)
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Authorization header required'}), 401

    token = auth_header[7:]
    user_id = None

    # Try JWT first
    try:
        payload = verify_jwt(token)
        user_id = payload.get('sub')
    except ValueError:
        # Fall back to session token (passkey auth)
        from passkey_auth import hash_session_token
        token_hash = hash_session_token(token)
        scur = get_cursor()
        try:
            scur.execute(
                '''SELECT user_id FROM passkey_sessions
                   WHERE token = %s AND expires_at > NOW()''',
                (token_hash,)
            )
            session = scur.fetchone()
            if session:
                user_id = session['user_id']
        finally:
            scur.close()

    if not user_id:
        return jsonify({'error': 'Invalid or expired token'}), 401

    cur = get_cursor()

    try:
        cur.execute('''
            SELECT email, name, tenant_id, plan, status, api_key_encrypted,
                   stripe_customer_id, stripe_subscription_id, created_at
            FROM users WHERE id = %s
        ''', (user_id,))
        user = cur.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Decrypt API key if present
        api_key = None
        if user.get('api_key_encrypted'):
            try:
                api_key = decrypt_api_key(user['api_key_encrypted'])
            except Exception:
                api_key = None

        # Get usage stats if user has a tenant
        usage = None
        if user.get('tenant_id'):
            try:
                cur.execute('''
                    SELECT COUNT(*) as branches FROM branches WHERE tenant_id = %s
                ''', (user['tenant_id'],))
                branch_count = cur.fetchone()['branches']

                cur.execute('''
                    SELECT COUNT(*) as commits FROM commits
                    WHERE tenant_id = %s
                    AND created_at >= date_trunc('month', CURRENT_TIMESTAMP)
                ''', (user['tenant_id'],))
                commit_count = cur.fetchone()['commits']

                usage = {
                    'branches': branch_count,
                    'commits_this_month': commit_count
                }
            except Exception:
                pass

        return jsonify({
            'id': user_id,
            'email': user['email'],
            'name': user.get('name'),
            'tenant_id': str(user['tenant_id']) if user.get('tenant_id') else None,
            'plan': user.get('plan') or 'free',
            'status': user.get('status') or 'pending_payment',
            'api_key': api_key,
            'has_subscription': bool(user.get('stripe_subscription_id')),
            'member_since': str(user['created_at']) if user.get('created_at') else None,
            'usage': usage
        })

    finally:
        cur.close()


# =============================================================================
# BILLING & STRIPE WEBHOOKS (W2P2 - CC2)
# =============================================================================

from billing.stripe_handler import billing_bp
app.register_blueprint(billing_bp)


# =============================================================================
# EXTENSION DOWNLOAD (W4P2 - CC4)
# =============================================================================

@app.route('/api/extension/download', methods=['GET'])
@require_auth
def download_extension():
    """
    Download personalized .mcpb bundle for Claude Desktop.

    The bundle is pre-configured with the user's API credentials.
    Requires authentication via session token or GODMODE_PASSWORD.
    """
    from flask import Response
    from extension.builder.bundler import generate_bundle_for_user

    user_id = g.get('current_user', 'steve')

    # Get tenant_id for this user
    cur = get_cursor()
    cur.execute(
        'SELECT id, name FROM tenants WHERE name = %s OR id::text = %s LIMIT 1',
        (user_id, get_tenant_id())
    )
    tenant_row = cur.fetchone()

    if not tenant_row:
        cur.close()
        return jsonify({'error': 'Tenant not found'}), 404

    tenant_id = str(tenant_row['id'])
    display_name = tenant_row['name']

    # Get or create an API key for this tenant
    cur.execute(
        'SELECT key_hash FROM api_keys WHERE tenant_id = %s AND revoked_at IS NULL LIMIT 1',
        (tenant_id,)
    )
    key_row = cur.fetchone()

    if key_row:
        # Return error - we can't retrieve the actual key, only the hash
        # User needs to use an existing key or create a new one via /api/keys
        cur.close()
        return jsonify({
            'error': 'API key required. Create one via POST /api/keys first, then use that key.',
            'hint': 'The download endpoint needs your actual API key. Create one and save it.'
        }), 400

    cur.close()

    # Alternative: Accept API key as query param for download
    api_key = request.args.get('api_key')
    if not api_key:
        return jsonify({
            'error': 'api_key query parameter required',
            'hint': 'GET /api/extension/download?api_key=bos_xxx'
        }), 400

    try:
        bundle_bytes = generate_bundle_for_user(
            tenant_id=tenant_id,
            api_key=api_key,
            display_name=display_name
        )

        return Response(
            bundle_bytes,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': 'attachment; filename=boswell.mcpb',
                'Content-Length': str(len(bundle_bytes))
            }
        )

    except Exception as e:
        return jsonify({'error': f'Bundle generation failed: {str(e)}'}), 500



# ============================================================
# MCP Streamable HTTP Handler
# ============================================================
# Implements MCP JSON-RPC 2.0 over HTTP POST
# Replaces the deprecated SSE-based boswell-mcp service
# Direct in-process routing - no HTTP round-trip

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "boswell-mcp"
MCP_SERVER_VERSION = "3.0.0"

def invoke_view(view_fn, method='GET', path='/', query_string=None, json_data=None, view_args=None):
    """
    Call Flask view function in synthetic request context.
    Returns (data_dict, status_code).

    view_args: dict of URL path parameters (e.g., {'task_id': '...'})
    """
    # Capture tenant from outer (real) request context
    outer_tenant = getattr(g, 'mcp_auth', {}).get('tenant_id') if has_request_context() else None

    ctx_kwargs = {'method': method, 'path': path}
    if query_string:
        ctx_kwargs['query_string'] = query_string
    if json_data is not None:
        ctx_kwargs['json'] = json_data
        ctx_kwargs['content_type'] = 'application/json'

    with app.test_request_context(**ctx_kwargs):
        # Propagate tenant into the synthetic context
        if outer_tenant:
            push_tenant_override(outer_tenant)
            g.mcp_auth = {'tenant_id': outer_tenant, 'source': 'invoke_view'}
        try:
            if view_args:
                result = view_fn(**view_args)
            else:
                result = view_fn()

            # Handle tuple returns (response, status_code)
            if isinstance(result, tuple):
                resp, code = result[0], result[1]
                if hasattr(resp, 'get_json'):
                    return resp.get_json(), code
                return resp, code
            # Handle Response objects
            if hasattr(result, 'get_json'):
                return result.get_json(), 200
            # Handle raw dicts (shouldn't happen but safety)
            return result, 200
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'error': str(e)}, 500
        finally:
            if outer_tenant:
                pop_tenant_override()


# Whisper-enabled MCP_TOOLS - behavioral hints embedded in descriptions
MCP_TOOLS = [
    {
        "name": "boswell_startup",
        "description": "Load startup context. Returns sacred commitments, open tasks, and relevant memories. CALL THIS FIRST at conversation start, before responding to anything—even 'hi'. Sets the stage for continuity. Use verbosity='minimal' for greetings, 'normal' (default) for work, 'full' for debugging.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Optional context for semantic retrieval (default: 'important decisions and active commitments')"},
                "k": {"type": "integer", "description": "Number of relevant memories to return (default: 5)", "default": 5},
                "verbosity": {"type": "string", "enum": ["minimal", "normal", "full"], "description": "Response size: minimal (greeting), normal (work), full (debug)", "default": "normal"}
            }
        }
    },
    {
        "name": "boswell_brief",
        "description": "Quick context snapshot—recent commits, open tasks, branch activity. Call when resuming work or when asked 'what's been happening?' Lighter than boswell_startup.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch to focus on (default: command-center)", "default": "command-center"}
            }
        }
    },
    {
        "name": "boswell_branches",
        "description": "List all cognitive branches: command-center (infrastructure), tint-atlanta (CRM), iris (research), tint-empire (franchise), family (personal), boswell (memory system). Use to understand the topology.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_head",
        "description": "Get the current HEAD commit for a branch. Use to check what was last committed.",
        "inputSchema": {
            "type": "object",
            "properties": {"branch": {"type": "string", "description": "Branch name (e.g., tint-atlanta, command-center, boswell)"}},
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_log",
        "description": "View commit history for a branch. Use to trace what happened, find specific decisions, or understand work progression.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch name"},
                "limit": {"type": "integer", "description": "Max commits to return (default: 10)", "default": 10}
            },
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_search",
        "description": "Keyword search across all memories. Call BEFORE answering questions about past work when immediate context is missing. If asked 'what were we doing?' and you don't know, search first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "branch": {"type": "string", "description": "Optional: limit search to specific branch"},
                "limit": {"type": "integer", "description": "Max results (default: 10)", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "boswell_semantic_search",
        "description": "Find conceptually related memories using AI embeddings. Use for fuzzy queries like 'decisions about architecture' or when keyword search misses context. Complements boswell_search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Conceptual search query"},
                "limit": {"type": "integer", "description": "Max results (default: 10)", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "boswell_recall",
        "description": "Retrieve a specific memory by its blob hash or commit hash. Use when you have a hash reference and need full content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hash": {"type": "string", "description": "Blob hash to recall"},
                "commit": {"type": "string", "description": "Or commit hash to recall"}
            }
        }
    },
    {
        "name": "boswell_links",
        "description": "List resonance links between memories. Use to see cross-branch connections and conceptual relationships.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Optional: filter by branch"},
                "link_type": {"type": "string", "description": "Optional: filter by type (resonance, causal, contradiction, elaboration, application)"}
            }
        }
    },
    {
        "name": "boswell_graph",
        "description": "Get full memory graph—nodes and edges. Use for topology analysis or visualization.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_reflect",
        "description": "Get AI-surfaced insights—highly connected memories and cross-branch patterns. Use for strategic review.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_commit",
        "description": "Preserve a decision, insight, or context to memory. ALWAYS capture WHY, not just WHAT—future instances need reasoning. Call after completing steps, solving problems, making decisions, or learning something new. Use content_type='plan' to create persistent work plans that group tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch to commit to (tint-atlanta, iris, tint-empire, family, command-center, boswell)"},
                "content": {"type": "object", "description": "Memory content as JSON object"},
                "message": {"type": "string", "description": "Commit message describing the memory"},
                "content_type": {"type": "string", "description": "Content type: 'memory' (default) or 'plan'. Plans require title and status fields in content.", "default": "memory"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags for categorization"},
                "force_branch": {"type": "boolean", "description": "Suppress routing warnings - use when intentionally committing to a branch despite mismatch"},
                "content_type": {"type": "string", "description": "Content type: 'memory' (default) or 'skill' (behavioral instruction)"}
            },
            "required": ["branch", "content", "message"]
        }
    },
    {
        "name": "boswell_link",
        "description": "Create a resonance link between two memories. Captures conceptual connections across branches. Explain the reasoning—links are for pattern discovery.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_blob": {"type": "string", "description": "Source memory blob hash"},
                "target_blob": {"type": "string", "description": "Target memory blob hash"},
                "source_branch": {"type": "string", "description": "Source branch name"},
                "target_branch": {"type": "string", "description": "Target branch name"},
                "link_type": {"type": "string", "description": "Type: resonance, causal, contradiction, elaboration, application", "default": "resonance"},
                "reasoning": {"type": "string", "description": "Why these memories are connected"}
            },
            "required": ["source_blob", "target_blob", "source_branch", "target_branch", "reasoning"]
        }
    },
    {
        "name": "boswell_checkout",
        "description": "Switch focus to a different branch. Use when changing work contexts.",
        "inputSchema": {
            "type": "object",
            "properties": {"branch": {"type": "string", "description": "Branch to check out"}},
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_create_task",
        "description": "Add a task to the queue for yourself or other agents. Use to spawn subtasks, track work, or hand off to other instances.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What needs to be done"},
                "title": {"type": "string", "description": "Short display name for the work item (e.g. 'Fix dropdown bug')"},
                "branch": {"type": "string", "description": "Which branch this relates to (command-center, tint-atlanta, etc.)"},
                "priority": {"type": "integer", "description": "Priority 1-10 (1=highest, default=5)"},
                "assigned_to": {"type": "string", "description": "Optional: assign to specific instance"},
                "plan_blob_hash": {"type": "string", "description": "Blob hash of the plan this task serves. Omit for unorganized backlog tasks."},
                "metadata": {"type": "object", "description": "Optional: additional context"}
            },
            "required": ["description"]
        }
    },
    {
        "name": "boswell_claim_task",
        "description": "Claim a task to prevent other agents from working on it. Call when starting work from the queue. Always provide your instance_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to claim"},
                "instance_id": {"type": "string", "description": "Your unique instance identifier (e.g., 'CC1', 'CW-PM')"}
            },
            "required": ["task_id", "instance_id"]
        }
    },
    {
        "name": "boswell_release_task",
        "description": "Release a claimed task. Use 'completed' when done, 'blocked' if stuck, 'manual' to just unclaim. Always release what you claim.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to release"},
                "instance_id": {"type": "string", "description": "Your instance identifier"},
                "reason": {"type": "string", "enum": ["completed", "blocked", "timeout", "manual"], "description": "Why releasing (default: manual)"}
            },
            "required": ["task_id", "instance_id"]
        }
    },
    {
        "name": "boswell_update_task",
        "description": "Update task status, description, or priority. Use to report progress or modify details. Good practice: update status as you work.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to update"},
                "status": {"type": "string", "enum": ["open", "claimed", "blocked", "done"], "description": "New status"},
                "title": {"type": "string", "description": "Short display name for the task"},
                "description": {"type": "string", "description": "Updated description"},
                "priority": {"type": "integer", "description": "Priority (1=highest)"},
                "plan_blob_hash": {"type": "string", "description": "Blob hash of the plan this task serves"},
                "metadata": {"type": "object", "description": "Additional metadata to merge"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_delete_task",
        "description": "Soft-delete a task. Use for cleanup after completion or cancellation.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task ID to delete"}},
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_halt_tasks",
        "description": "EMERGENCY STOP. Halts all task processing, blocks claims. Use when swarm behavior is problematic or coordination breaks down.",
        "inputSchema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Why halting (default: 'Manual emergency halt')"}}
        }
    },
    {
        "name": "boswell_resume_tasks",
        "description": "Resume task processing after a halt. Clears the halt flag.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_halt_status",
        "description": "Check if task system is halted. Call before claiming tasks if unsure.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_landscape",
        "description": "View the full work landscape — branches as projects, plans with progress, cascade health scores, and unorganized backlog. Call when you need the big picture.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Optional: filter by branch"},
                "include_done": {"type": "boolean", "description": "Include completed plans (default: false)"}
            }
        }
    },
    {
        "name": "boswell_record_trail",
        "description": "Record a traversal between memories. Strengthens the path for future recall. Trails that aren't traversed decay over time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_blob": {"type": "string", "description": "Source memory blob hash"},
                "target_blob": {"type": "string", "description": "Target memory blob hash"}
            },
            "required": ["source_blob", "target_blob"]
        }
    },
    {
        "name": "boswell_hot_trails",
        "description": "Get strongest memory trails—frequently traversed paths. Shows what's top of mind.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max trails to return (default: 20)"}}
        }
    },
    {
        "name": "boswell_trails_from",
        "description": "Get outbound trails from a memory. Shows what's typically accessed next.",
        "inputSchema": {
            "type": "object",
            "properties": {"blob": {"type": "string", "description": "Source memory blob hash"}},
            "required": ["blob"]
        }
    },
    {
        "name": "boswell_trails_to",
        "description": "Get inbound trails to a memory. Shows what typically leads here.",
        "inputSchema": {
            "type": "object",
            "properties": {"blob": {"type": "string", "description": "Target memory blob hash"}},
            "required": ["blob"]
        }
    },
    {
        "name": "boswell_trail_health",
        "description": "Trail system health—state distribution (ACTIVE/FADING/DORMANT/ARCHIVED), activity metrics. Use to monitor memory decay.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "boswell_buried_memories",
        "description": "Find dormant and archived trails—memory paths fading from recall. These can be resurrected by traversing them.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max trails to return (default: 20)"},
                "include_archived": {"type": "boolean", "description": "Include archived trails (default: true)"}
            }
        }
    },
    {
        "name": "boswell_decay_forecast",
        "description": "Predict when trails will decay. Use to identify memories at risk of fading.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "boswell_resurrect",
        "description": "Resurrect a dormant trail by traversing it. Doubles strength, resets to ACTIVE. Use to save important paths from decay.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trail_id": {"type": "string", "description": "Trail ID to resurrect"},
                "source_blob": {"type": "string", "description": "Or: source blob hash"},
                "target_blob": {"type": "string", "description": "Or: target blob hash"}
            }
        }
    },
    {
        "name": "boswell_checkpoint",
        "description": "Save session checkpoint for crash recovery. Captures WHERE you are—progress, next step, context. Use before risky operations or long tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to checkpoint"},
                "instance_id": {"type": "string", "description": "Your instance identifier (e.g., 'CC1', 'CW-Opus')"},
                "progress": {"type": "string", "description": "Human-readable progress description"},
                "next_step": {"type": "string", "description": "What to do next on resume"},
                "context_snapshot": {"type": "object", "description": "Arbitrary context data to preserve"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_resume",
        "description": "Get checkpoint for a task. Use to resume after crash or context loss.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to resume"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_validate_routing",
        "description": "Check which branch best matches content before committing. Returns confidence scores. Use when unsure about branch selection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "object", "description": "Content to analyze"},
                "branch": {"type": "string", "description": "Requested branch"}
            },
            "required": ["content"]
        }
    },
    # ===== IMMUNE SYSTEM TOOLS =====
    {
        "name": "boswell_quarantine_list",
        "description": "List all quarantined memories awaiting human review. Quarantined memories are anomalies detected by the immune system patrol. Review and resolve them with boswell_quarantine_resolve.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max entries to return (default: 50)", "default": 50}
            }
        }
    },
    {
        "name": "boswell_quarantine_resolve",
        "description": "Resolve a quarantined memory: reinstate it to active status or permanently delete it. Always provide a reason explaining your decision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blob_hash": {"type": "string", "description": "Hash of the quarantined blob"},
                "action": {"type": "string", "enum": ["reinstate", "delete"], "description": "Whether to reinstate or delete"},
                "reason": {"type": "string", "description": "Why you're reinstating or deleting this memory"}
            },
            "required": ["blob_hash", "action"]
        }
    },
    {
        "name": "boswell_immune_status",
        "description": "Get immune system health: quarantine counts, last patrol time, branch health scores. Use to monitor memory graph health.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    # Hippocampal Memory Tools (v4.0)
    {
        "name": "boswell_bookmark",
        "description": "Lightweight memory staging. Use for observations, patterns, context that MIGHT be worth remembering. Cheaper than commit — expires in 7 days unless replayed. Default salience 0.3.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch to stage on (tint-atlanta, iris, tint-empire, family, command-center, boswell)"},
                "summary": {"type": "string", "description": "Brief summary of the observation/insight"},
                "content": {"type": "object", "description": "Optional structured content"},
                "message": {"type": "string", "description": "Optional commit-style message"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"},
                "salience": {"type": "number", "description": "Importance 0-1 (default 0.3). Higher = more likely to be promoted"},
                "context": {"type": "string", "description": "Optional working context description — used for auto-replay differentiation"},
                "source_instance": {"type": "string", "description": "Which instance created this (e.g., CC1, CW-PM)"},
                "ttl_days": {"type": "integer", "description": "Days until expiry (default 7)"}
            },
            "required": ["branch", "summary"]
        }
    },
    {
        "name": "boswell_replay",
        "description": "Record topic recurrence — strengthens a bookmark's case for permanent storage. Increases replay_count. Near-expiry bookmarks with 3+ replays get TTL extension.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string", "description": "UUID of the candidate to replay"},
                "keywords": {"type": "string", "description": "Alternative: semantic search for matching candidate"},
                "session_id": {"type": "string", "description": "Optional session identifier"},
                "replay_context": {"type": "string", "description": "Optional context of the replay"}
            }
        }
    },
    {
        "name": "boswell_consolidate",
        "description": "Manual consolidation trigger — score and promote top candidates to permanent memory. Use dry_run=true to preview scores without committing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_promotions": {"type": "integer", "description": "Max candidates to promote (default 10)", "default": 10},
                "dry_run": {"type": "boolean", "description": "Preview scores without promoting (default false)", "default": False},
                "branch": {"type": "string", "description": "Optional: only consolidate this branch"},
                "min_score": {"type": "number", "description": "Minimum consolidation score to promote (default 0)", "default": 0}
            }
        }
    },
    {
        "name": "boswell_candidates",
        "description": "View staging buffer — what's in working memory. Shows bookmarks with salience, replay count, and expiry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Optional: filter by branch"},
                "status": {"type": "string", "description": "Optional: filter by status (active, cooling, promoted, expired)"},
                "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
                "sort": {"type": "string", "description": "Sort by: salience, replay_count, created_at, expires_at (default created_at)"}
            }
        }
    },
    {
        "name": "boswell_decay_status",
        "description": "View expiring candidates — what's about to be forgotten. Shows bookmarks expiring within N days.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Show candidates expiring within this many days (default 2)", "default": 2}
            }
        }
    },
]

def mcp_error_response(req_id, code, message):
    """Build JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message}
    }

def mcp_success_response(req_id, result):
    """Build JSON-RPC success response."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result
    }


def dispatch_mcp_tool(tool_name, args):
    """
    Dispatch MCP tool call to appropriate Flask view function.
    Returns (result_dict, status_code).
    """
    # ===== READ OPERATIONS =====
    
    if tool_name == "boswell_brief":
        branch = args.get("branch", "command-center")
        return invoke_view(quick_brief, query_string={"branch": branch})
    
    elif tool_name == "boswell_branches":
        return invoke_view(list_branches)
    
    elif tool_name == "boswell_head":
        return invoke_view(get_head, query_string={"branch": args["branch"]})
    
    elif tool_name == "boswell_log":
        qs = {"branch": args["branch"]}
        if "limit" in args:
            qs["limit"] = args["limit"]
        return invoke_view(get_log, query_string=qs)
    
    elif tool_name == "boswell_search":
        qs = {"q": args["query"]}
        if "branch" in args:
            qs["branch"] = args["branch"]
        if "limit" in args:
            qs["limit"] = args["limit"]
        return invoke_view(search_memories, query_string=qs)
    
    elif tool_name == "boswell_semantic_search":
        qs = {"q": args["query"]}
        if "limit" in args:
            qs["limit"] = args["limit"]
        return invoke_view(semantic_search, query_string=qs)
    
    elif tool_name == "boswell_recall":
        qs = {}
        if "hash" in args:
            qs["hash"] = args["hash"]
        if "commit" in args:
            qs["commit"] = args["commit"]
        return invoke_view(recall_memory, query_string=qs)
    
    elif tool_name == "boswell_links":
        qs = {}
        if "branch" in args:
            qs["branch"] = args["branch"]
        if "link_type" in args:
            qs["link_type"] = args["link_type"]
        return invoke_view(list_links, query_string=qs)
    
    elif tool_name == "boswell_graph":
        return invoke_view(get_graph)
    
    elif tool_name == "boswell_reflect":
        return invoke_view(reflect)
    
    elif tool_name == "boswell_startup":
        qs = {}
        if "context" in args:
            qs["context"] = args["context"]
        if "k" in args:
            qs["k"] = args["k"]
        return invoke_view(semantic_startup, query_string=qs)
    
    # ===== WRITE OPERATIONS =====
    
    elif tool_name == "boswell_commit":
        payload = {
            "branch": args["branch"],
            "content": args["content"],
            "message": args["message"],
            "author": "claude-web",
            "type": args.get("content_type", "memory")
        }
        if "tags" in args:
            payload["tags"] = args["tags"]
        if "force_branch" in args:
            payload["force_branch"] = args["force_branch"]
        return invoke_view(create_commit, method='POST', json_data=payload)
    
    elif tool_name == "boswell_link":
        payload = {
            "source_blob": args["source_blob"],
            "target_blob": args["target_blob"],
            "source_branch": args["source_branch"],
            "target_branch": args["target_branch"],
            "link_type": args.get("link_type", "resonance"),
            "reasoning": args["reasoning"],
            "created_by": "claude-web"
        }
        return invoke_view(create_link, method='POST', json_data=payload)
    
    elif tool_name == "boswell_checkout":
        return invoke_view(checkout_branch, method='POST', json_data={"branch": args["branch"]})
    
    # ===== TASK QUEUE OPERATIONS =====
    
    elif tool_name == "boswell_create_task":
        payload = {"description": args["description"]}
        for field in ["title", "branch", "priority", "assigned_to", "metadata", "plan_blob_hash"]:
            if field in args:
                payload[field] = args[field]
        return invoke_view(create_task, method='POST', json_data=payload)
    
    elif tool_name == "boswell_claim_task":
        task_id = args["task_id"]
        payload = {"instance_id": args["instance_id"]}
        return invoke_view(
            claim_task,
            method='POST',
            path=f'/v2/tasks/{task_id}/claim',
            json_data=payload,
            view_args={"task_id": task_id}
        )
    
    elif tool_name == "boswell_release_task":
        task_id = args["task_id"]
        payload = {
            "instance_id": args["instance_id"],
            "reason": args.get("reason", "manual")
        }
        return invoke_view(
            release_task,
            method='POST',
            path=f'/v2/tasks/{task_id}/release',
            json_data=payload,
            view_args={"task_id": task_id}
        )
    
    elif tool_name == "boswell_update_task":
        task_id = args["task_id"]
        payload = {}
        for field in ["status", "description", "title", "priority", "metadata", "plan_blob_hash"]:
            if field in args:
                payload[field] = args[field]
        return invoke_view(
            update_task,
            method='PATCH',
            path=f'/v2/tasks/{task_id}',
            json_data=payload,
            view_args={"task_id": task_id}
        )
    
    elif tool_name == "boswell_delete_task":
        task_id = args["task_id"]
        return invoke_view(
            delete_task,
            method='DELETE',
            path=f'/v2/tasks/{task_id}',
            view_args={"task_id": task_id}
        )
    
    elif tool_name == "boswell_halt_tasks":
        payload = {}
        if "reason" in args:
            payload["reason"] = args["reason"]
        return invoke_view(halt_tasks, method='POST', json_data=payload)
    
    elif tool_name == "boswell_resume_tasks":
        return invoke_view(resume_tasks, method='POST', json_data={})
    
    elif tool_name == "boswell_halt_status":
        return invoke_view(halt_status)

    elif tool_name == "boswell_landscape":
        qs = {}
        if "branch" in args:
            qs["branch"] = args["branch"]
        if "include_done" in args:
            qs["include_done"] = "true" if args["include_done"] else "false"
        return invoke_view(work_landscape, query_string=qs if qs else None)

    # ===== TRAIL OPERATIONS =====
    
    elif tool_name == "boswell_record_trail":
        payload = {
            "source_blob": args["source_blob"],
            "target_blob": args["target_blob"]
        }
        return invoke_view(record_trail, method='POST', json_data=payload)
    
    elif tool_name == "boswell_hot_trails":
        qs = {}
        if "limit" in args:
            qs["limit"] = args["limit"]
        return invoke_view(get_hot_trails, query_string=qs if qs else None)
    
    elif tool_name == "boswell_trails_from":
        blob = args["blob"]
        return invoke_view(
            get_trails_from,
            path=f'/v2/trails/from/{blob}',
            view_args={"source_blob": blob}
        )
    
    elif tool_name == "boswell_trails_to":
        blob = args["blob"]
        return invoke_view(
            get_trails_to,
            path=f'/v2/trails/to/{blob}',
            view_args={"target_blob": blob}
        )

    # ===== TRAIL LIFECYCLE TOOLS =====

    elif tool_name == "boswell_trail_health":
        return invoke_view(trail_health)

    elif tool_name == "boswell_buried_memories":
        qs = {}
        if "limit" in args:
            qs["limit"] = args["limit"]
        if "include_archived" in args:
            qs["include_archived"] = str(args["include_archived"]).lower()
        return invoke_view(buried_memories, query_string=qs if qs else None)

    elif tool_name == "boswell_decay_forecast":
        return invoke_view(decay_forecast)

    elif tool_name == "boswell_resurrect":
        payload = {}
        if "trail_id" in args:
            payload["trail_id"] = args["trail_id"]
        if "source_blob" in args:
            payload["source_blob"] = args["source_blob"]
        if "target_blob" in args:
            payload["target_blob"] = args["target_blob"]
        return invoke_view(resurrect_trail, method='POST', json_data=payload)

    # ===== SESSION CHECKPOINT TOOLS =====

    elif tool_name == "boswell_checkpoint":
        json_data = {
            "task_id": args["task_id"],
            "instance_id": args.get("instance_id"),
            "progress": args.get("progress"),
            "next_step": args.get("next_step"),
            "context_snapshot": args.get("context_snapshot", {})
        }
        return invoke_view(create_checkpoint, method='POST', json_data=json_data)

    elif tool_name == "boswell_resume":
        return invoke_view(get_checkpoint, query_string={"task_id": args["task_id"]})

    elif tool_name == "boswell_validate_routing":
        json_data = {
            "content": args.get("content"),
            "branch": args.get("branch", "command-center")
        }
        return invoke_view(validate_commit_routing, method='POST', json_data=json_data)

    # ===== IMMUNE SYSTEM TOOLS =====

    elif tool_name == "boswell_quarantine_list":
        qs = {}
        if "limit" in args:
            qs["limit"] = args["limit"]
        return invoke_view(list_quarantine, query_string=qs if qs else None)

    elif tool_name == "boswell_quarantine_resolve":
        blob_hash = args["blob_hash"]
        json_data = {
            "action": args["action"],
            "reason": args.get("reason", "")
        }
        return invoke_view(
            resolve_quarantine,
            method='POST',
            path=f'/v2/immune/quarantine/{blob_hash}/resolve',
            json_data=json_data,
            view_args={"blob_hash": blob_hash}
        )

    elif tool_name == "boswell_immune_status":
        return invoke_view(immune_status)

    # ===== HIPPOCAMPAL MEMORY TOOLS (v4.0) =====

    elif tool_name == "boswell_bookmark":
        payload = {
            "branch": args.get("branch", "command-center"),
            "summary": args["summary"]
        }
        for field in ["content", "message", "tags", "salience", "salience_type",
                       "source_instance", "context", "ttl_days", "session_context"]:
            if field in args:
                payload[field] = args[field]
        return invoke_view(create_bookmark, method='POST', json_data=payload)

    elif tool_name == "boswell_replay":
        payload = {}
        for field in ["candidate_id", "keywords", "session_id", "replay_context"]:
            if field in args:
                payload[field] = args[field]
        return invoke_view(record_replay, method='POST', json_data=payload)

    elif tool_name == "boswell_consolidate":
        payload = {}
        for field in ["max_promotions", "dry_run", "branch", "min_score"]:
            if field in args:
                payload[field] = args[field]
        return invoke_view(run_consolidation, method='POST', json_data=payload)

    elif tool_name == "boswell_candidates":
        qs = {}
        for field in ["branch", "status", "limit", "sort"]:
            if field in args:
                qs[field] = args[field]
        return invoke_view(list_candidates, query_string=qs if qs else None)

    elif tool_name == "boswell_decay_status":
        qs = {}
        if "days" in args:
            qs["days"] = args["days"]
        return invoke_view(get_decay_status, query_string=qs if qs else None)

    else:
        return {"error": f"Unknown tool: {tool_name}"}, 400


@app.route('/v2/mcp', methods=['POST'])
def mcp_handler():
    """
    MCP Streamable HTTP endpoint.
    Handles JSON-RPC 2.0 requests: initialize, tools/list, tools/call
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify(mcp_error_response(None, -32700, "Parse error: empty body")), 400
    except Exception as e:
        return jsonify(mcp_error_response(None, -32700, f"Parse error: {str(e)}")), 400
    
    req_id = data.get("id")
    method = data.get("method")
    params = data.get("params", {})
    
    # Log for audit
    print(f"[MCP] method={method} id={req_id}", file=sys.stderr)
    
    # ===== INITIALIZE =====
    if method == "initialize":
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": MCP_SERVER_NAME,
                "version": MCP_SERVER_VERSION,
                "title": "Boswell Memory System",
                "description": "Git-style memory architecture for persistent context across AI instances"
            },
            "capabilities": {
                "tools": {"listChanged": False}
            },
            "instructions": """Boswell is a git-style memory system for AI instances. Use these tools proactively:

STARTUP:
- Call boswell_startup FIRST every conversation, before responding to anything
- This loads active commitments and relevant context

DURING CONVERSATION:
- boswell_commit: Preserve decisions, insights, and context worth remembering. Capture WHY, not just WHAT.
- boswell_search: Find past decisions when context is ambiguous
- boswell_brief: Quick overview of recent activity and open tasks
- boswell_log: View commit history on a branch

BEHAVIORAL RULES:
- If asked "what were we doing" and immediate context is empty, query Boswell before answering
- Recent commits contain the thread of work in progress
- Treat this as your external memory—use it like you'd use your own recall"""
        }
        return jsonify(mcp_success_response(req_id, result))
    
    # ===== TOOLS/LIST =====
    elif method == "tools/list":
        result = {"tools": MCP_TOOLS}
        return jsonify(mcp_success_response(req_id, result))
    
    # ===== TOOLS/CALL =====
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        
        if not tool_name:
            return jsonify(mcp_error_response(req_id, -32602, "Missing tool name")), 400
        
        # Dispatch to view function
        start_time = time.time()
        result_data, status_code = dispatch_mcp_tool(tool_name, tool_args)
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Log tool call for audit
        print(f"[MCP] tool={tool_name} status={status_code} duration={duration_ms}ms", file=sys.stderr)
        
        # Build MCP response
        if status_code >= 400:
            # Return error in MCP format (but with 200 HTTP - MCP convention)
            error_text = result_data.get('error', 'Unknown error') if isinstance(result_data, dict) else str(result_data)
            result = {
                "content": [{"type": "text", "text": f"Error: {error_text}"}],
                "isError": True
            }
        else:
            # Success - serialize result as text content
            result = {
                "content": [{"type": "text", "text": json.dumps(result_data, indent=2, default=str)}]
            }
        
        return jsonify(mcp_success_response(req_id, result))
    
    # ===== NOTIFICATIONS (no response required per MCP spec) =====
    elif method and method.startswith("notifications/"):
        # MCP notifications are fire-and-forget, return empty 200
        print(f"[MCP] notification acknowledged: {method}", file=sys.stderr)
        return "", 200
    
    # ===== UNKNOWN METHOD =====
    else:
        return jsonify(mcp_error_response(req_id, -32601, f"Method not found: {method}")), 400


# Debug endpoint for routing similarity scores
@app.route('/v2/routing/debug', methods=['POST'])
def debug_routing():
    """Debug routing similarity - shows what scores the content gets against each branch."""
    data = request.get_json() or {}
    content = data.get('content', {})
    message = data.get('message', '')
    
    # Generate embedding
    text_for_embedding = f"{message}\n{json.dumps(content, default=str)}"
    embedding = None
    try:
        from openai import OpenAI
        client = OpenAI()
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text_for_embedding
        )
        embedding = response.data[0].embedding
    except Exception as e:
        return jsonify({"error": f"Failed to generate embedding: {e}"}), 500
    
    # Compare against all fingerprints
    cur = get_cursor()
    cur.execute("""
        SELECT branch_name, centroid, commit_count
        FROM branch_fingerprints
        WHERE tenant_id = %s AND centroid IS NOT NULL
    """, (get_tenant_id(),))
    
    scores = []
    for row in cur.fetchall():
        if row['centroid'] is not None:
            similarity = cosine_similarity(embedding, row['centroid'])
            scores.append({
                'branch': row['branch_name'],
                'similarity': round(similarity, 4),
                'commit_count': row['commit_count']
            })
    cur.close()
    
    scores.sort(key=lambda x: x['similarity'], reverse=True)
    
    return jsonify({
        "scores": scores,
        "best_match": scores[0] if scores else None,
        "threshold": 0.15,
        "would_trigger_warning": scores[0]['similarity'] > 0.15 if scores else False,
        "text_embedded": text_for_embedding[:200] + "..."
    })


# Convenience endpoint for MCP health check
@app.route('/v2/mcp/health', methods=['GET'])
def mcp_health():
    """Health check for MCP endpoint."""
    return jsonify({
        "status": "ok",
        "server": MCP_SERVER_NAME,
        "version": MCP_SERVER_VERSION,
        "protocol": MCP_PROTOCOL_VERSION,
        "tools_count": len(MCP_TOOLS)
    })


# ============================================================
# Dashboard Serving (React SPA)
# ============================================================

DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), 'static', 'dist')

@app.route('/')
def serve_dashboard():
    """Serve the React dashboard index."""
    return send_from_directory(DASHBOARD_DIR, 'index.html')

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    """Serve static assets (JS, CSS, etc.)."""
    return send_from_directory(os.path.join(DASHBOARD_DIR, 'assets'), filename)

@app.route('/<path:path>')
def serve_spa(path):
    """Catch-all route for SPA - return index.html for client-side routing."""
    # Don't catch API routes
    if path.startswith('v2/') or path.startswith('api/') or path.startswith('auth/') or path.startswith('mcp'):
        return jsonify({'error': 'Not found'}), 404
    # Check if it's a static file
    static_path = os.path.join(DASHBOARD_DIR, path)
    if os.path.isfile(static_path):
        return send_from_directory(DASHBOARD_DIR, path)
    # Otherwise return index.html for SPA routing
    return send_from_directory(DASHBOARD_DIR, 'index.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
