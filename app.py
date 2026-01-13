#!/usr/bin/env python3
"""
Boswell v2 API - Git-Style Memory Architecture
PostgreSQL version with multi-tenant support + Encryption (Phase 2)
"""

import psycopg2
import psycopg2.extras
import hashlib
import json
import os
from datetime import datetime
from flask import Flask, request, jsonify, g
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)

# Encryption support (Phase 2)
ENCRYPTION_ENABLED = os.environ.get('ENCRYPTION_ENABLED', 'false').lower() == 'true'
CREDENTIALS_PATH = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-key.json')

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
            (DEFAULT_TENANT,)
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
        # Set tenant context for RLS
        cur = g.db.cursor()
        cur.execute(f"SET app.current_tenant = '{DEFAULT_TENANT}'")
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
    """Start timing for audit logging."""
    g.audit_start = time.time()

@app.after_request
def after_request(response):
    """Log request to audit trail."""
    if not AUDIT_ENABLED:
        return response
    # Skip health checks and static
    if request.path in ('/', '/health', '/favicon.ico', '/v2/'):
        return response
    try:
        from audit_service import log_audit, parse_request_action
        duration_ms = int((time.time() - getattr(g, 'audit_start', time.time())) * 1000)
        action, resource_type, resource_id = parse_request_action(request)

        cur = get_cursor()
        log_audit(
            cursor=cur,
            tenant_id=DEFAULT_TENANT,
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
        (branch, DEFAULT_TENANT)
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

@app.route('/', methods=['GET'])
@app.route('/v2/', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        cur = get_cursor()
        cur.execute('SELECT COUNT(*) as count FROM branches WHERE tenant_id = %s', (DEFAULT_TENANT,))
        branch_count = cur.fetchone()['count']
        cur.execute('SELECT COUNT(*) as count FROM commits WHERE tenant_id = %s', (DEFAULT_TENANT,))
        commit_count = cur.fetchone()['count']
        cur.close()
        # Check encryption status
        encryption_status = 'disabled'
        if ENCRYPTION_ENABLED:
            encryption_status = 'enabled'
            if get_active_dek():
                encryption_status = 'active'

        return jsonify({
            'status': 'ok',
            'service': 'boswell-v2',
            'version': '2.9.0-godmode',
            'platform': 'railway',
            'database': 'postgres',
            'encryption': encryption_status,
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

@app.route('/v2/head', methods=['GET'])
def get_head():
    """Get current HEAD state for a branch."""
    branch = request.args.get('branch', 'command-center')
    cur = get_cursor()

    cur.execute('SELECT * FROM branches WHERE name = %s AND tenant_id = %s', (branch, DEFAULT_TENANT))
    branch_info = cur.fetchone()

    if not branch_info:
        cur.close()
        return jsonify({'error': f'Branch {branch} not found'}), 404

    head_commit = branch_info['head_commit']
    commit_info = None
    if head_commit and head_commit != 'GENESIS':
        cur.execute('SELECT * FROM commits WHERE commit_hash = %s AND tenant_id = %s', (head_commit, DEFAULT_TENANT))
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
    cur.execute('SELECT * FROM branches WHERE name = %s AND tenant_id = %s', (branch, DEFAULT_TENANT))
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
    """List all cognitive branches."""
    cur = get_cursor()
    cur.execute('SELECT * FROM branches WHERE tenant_id = %s ORDER BY name', (DEFAULT_TENANT,))
    branches = [dict(row) for row in cur.fetchall()]
    cur.close()
    return jsonify({'branches': branches, 'count': len(branches)})

@app.route('/v2/branch', methods=['POST'])
def create_branch():
    """Create a new cognitive branch."""
    data = request.get_json() or {}
    name = data.get('name')
    from_branch = data.get('from', 'command-center')

    if not name:
        return jsonify({'error': 'Branch name required'}), 400

    db = get_db()
    cur = get_cursor()

    cur.execute('SELECT name FROM branches WHERE name = %s AND tenant_id = %s', (name, DEFAULT_TENANT))
    if cur.fetchone():
        cur.close()
        return jsonify({'error': f'Branch {name} already exists'}), 409

    cur.execute('SELECT head_commit FROM branches WHERE name = %s AND tenant_id = %s', (from_branch, DEFAULT_TENANT))
    source = cur.fetchone()
    head_commit = source['head_commit'] if source else 'GENESIS'

    now = datetime.utcnow().isoformat() + 'Z'
    cur.execute(
        '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
           VALUES (%s, %s, %s, %s)''',
        (DEFAULT_TENANT, name, head_commit, now)
    )
    db.commit()
    cur.close()

    return jsonify({
        'status': 'created',
        'branch': name,
        'from': from_branch,
        'head_commit': head_commit
    }), 201

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

    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'

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
            (blob_hash, DEFAULT_TENANT, content_str, psycopg2.Binary(ciphertext), psycopg2.Binary(nonce), key_id, memory_type, now, len(content_str))
        )
    else:
        # Fallback: store unencrypted
        cur.execute(
            '''INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (blob_hash) DO NOTHING''',
            (blob_hash, DEFAULT_TENANT, content_str, memory_type, now, len(content_str))
        )

    tree_hash = compute_hash(f"{branch}:{blob_hash}:{now}")
    cur.execute(
        '''INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
           VALUES (%s, %s, %s, %s, %s)''',
        (DEFAULT_TENANT, tree_hash, message[:100], blob_hash, memory_type)
    )

    cur.execute('SELECT head_commit FROM branches WHERE name = %s AND tenant_id = %s', (branch, DEFAULT_TENANT))
    branch_row = cur.fetchone()
    parent_hash = branch_row['head_commit'] if branch_row else None
    if parent_hash == 'GENESIS':
        parent_hash = None

    commit_data = f"{tree_hash}:{parent_hash}:{message}:{now}"
    commit_hash = compute_hash(commit_data)

    cur.execute(
        '''INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)''',
        (commit_hash, DEFAULT_TENANT, tree_hash, parent_hash, author, message, now)
    )

    cur.execute(
        'UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s',
        (commit_hash, branch, DEFAULT_TENANT)
    )

    for tag in tags:
        tag_str = tag if isinstance(tag, str) else str(tag)
        cur.execute(
            '''INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (tenant_id, blob_hash, tag) DO NOTHING''',
            (DEFAULT_TENANT, blob_hash, tag_str, now)
        )

    db.commit()
    cur.close()

    return jsonify({
        'status': 'committed',
        'commit_hash': commit_hash,
        'blob_hash': blob_hash,
        'tree_hash': tree_hash,
        'branch': branch,
        'message': message
    }), 201

@app.route('/v2/log', methods=['GET'])
def get_log():
    """Get commit history for a branch."""
    branch = request.args.get('branch', 'command-center')
    limit = request.args.get('limit', 20, type=int)

    cur = get_cursor()
    cur.execute('SELECT head_commit FROM branches WHERE name = %s AND tenant_id = %s', (branch, DEFAULT_TENANT))
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
        cur.execute('SELECT * FROM commits WHERE commit_hash = %s AND tenant_id = %s', (current_hash, DEFAULT_TENANT))
        commit = cur.fetchone()
        if not commit:
            break
        commits.append(dict(commit))
        current_hash = commit['parent_hash']

    cur.close()
    return jsonify({'branch': branch, 'commits': commits, 'count': len(commits)})

@app.route('/v2/search', methods=['GET'])
def search_memories():
    """Search memories across branches."""
    query = request.args.get('q', '')
    memory_type = request.args.get('type')
    limit = request.args.get('limit', 20, type=int)

    if not query:
        return jsonify({'error': 'Search query required'}), 400

    cur = get_cursor()

    sql = '''
        SELECT DISTINCT b.blob_hash, b.content, b.content_type, b.created_at,
               c.commit_hash, c.message, c.author
        FROM blobs b
        JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
        JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
        WHERE b.content LIKE %s AND b.tenant_id = %s
    '''
    params = [f'%{query}%', DEFAULT_TENANT]

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
            'author': row['author']
        })

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
        cur.execute('SELECT * FROM blobs WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, DEFAULT_TENANT))
        blob = cur.fetchone()
        if not blob:
            cur.close()
            return jsonify({'error': 'Memory not found'}), 404
        cur.close()

        # Decrypt content if needed
        content = decrypt_blob_content(dict(blob))

        return jsonify({
            'blob_hash': blob['blob_hash'],
            'content': content,
            'content_type': blob['content_type'],
            'created_at': str(blob['created_at']) if blob['created_at'] else None,
            'byte_size': blob['byte_size'],
            'encrypted': bool(blob.get('content_encrypted'))
        })

    elif commit_hash:
        cur.execute(
            '''SELECT c.*, b.content, b.content_type, b.content_encrypted, b.nonce, b.encryption_key_id
               FROM commits c
               JOIN tree_entries t ON c.tree_hash = t.tree_hash AND c.tenant_id = t.tenant_id
               JOIN blobs b ON t.blob_hash = b.blob_hash AND t.tenant_id = b.tenant_id
               WHERE c.commit_hash = %s AND c.tenant_id = %s''',
            (commit_hash, DEFAULT_TENANT)
        )
        commit = cur.fetchone()
        cur.close()
        if not commit:
            return jsonify({'error': 'Commit not found'}), 404
        result = dict(commit)

        # Decrypt content if needed
        result['content'] = decrypt_blob_content(result)
        result['encrypted'] = bool(result.get('content_encrypted'))

        # Clean up encryption fields from response
        result.pop('content_encrypted', None)
        result.pop('nonce', None)
        result.pop('encryption_key_id', None)

        if result.get('created_at'):
            result['created_at'] = str(result['created_at'])
        return jsonify(result)

    return jsonify({'error': 'Hash or commit required'}), 400

@app.route('/v2/quick-brief', methods=['GET'])
def quick_brief():
    """Get a context brief for current state."""
    branch = request.args.get('branch', 'command-center')

    cur = get_cursor()
    cur.execute('SELECT * FROM branches WHERE name = %s AND tenant_id = %s', (branch, DEFAULT_TENANT))
    branch_info = cur.fetchone()

    if not branch_info:
        cur.close()
        return jsonify({'error': f'Branch {branch} not found'}), 404

    cur.execute(
        '''SELECT commit_hash, message, created_at, author
           FROM commits WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 5''',
        (DEFAULT_TENANT,)
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
        (DEFAULT_TENANT,)
    )
    pending_sessions = []
    for row in cur.fetchall():
        r = dict(row)
        if r.get('synced_at'):
            r['synced_at'] = str(r['synced_at'])
        pending_sessions.append(r)

    cur.execute('SELECT name FROM branches WHERE tenant_id = %s', (DEFAULT_TENANT,))
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
            (DEFAULT_TENANT, source_blob, target_blob, source_branch, target_branch,
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
    params = [DEFAULT_TENANT]

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
                   substring(b.content, 1, 200) as preview
            FROM blobs b
            JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
            JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
            JOIN branches br ON (c.commit_hash = br.head_commit OR c.parent_hash IS NOT NULL) AND br.tenant_id = c.tenant_id
            WHERE br.name = %s AND b.tenant_id = %s
            LIMIT %s
        '''
        cur.execute(nodes_sql, (branch, DEFAULT_TENANT, limit))
    else:
        nodes_sql = '''
            SELECT blob_hash, content_type, created_at,
                   substring(content, 1, 200) as preview
            FROM blobs WHERE tenant_id = %s ORDER BY created_at DESC LIMIT %s
        '''
        cur.execute(nodes_sql, (DEFAULT_TENANT, limit))

    nodes = []
    for row in cur.fetchall():
        nodes.append({
            'id': row['blob_hash'],
            'type': row['content_type'],
            'created_at': str(row['created_at']) if row['created_at'] else None,
            'preview': row['preview']
        })

    if branch:
        edges_sql = '''
            SELECT * FROM cross_references
            WHERE (source_branch = %s OR target_branch = %s) AND tenant_id = %s LIMIT %s
        '''
        cur.execute(edges_sql, (branch, branch, DEFAULT_TENANT, limit))
    else:
        edges_sql = 'SELECT * FROM cross_references WHERE tenant_id = %s LIMIT %s'
        cur.execute(edges_sql, (DEFAULT_TENANT, limit))

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
            SELECT b.blob_hash, b.content_type, substring(b.content, 1, 500) as preview,
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

    cur.execute(sql, (DEFAULT_TENANT, DEFAULT_TENANT, min_links, limit))
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
    cur.execute(cross_branch_sql, (DEFAULT_TENANT, limit))
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
        (session_id, DEFAULT_TENANT, branch, content_str, summary, now, 'synced')
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
    params = [DEFAULT_TENANT]

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

        rows = query_audit_logs(cur, DEFAULT_TENANT, filters, limit, offset)
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
        stats = get_audit_stats(cur, DEFAULT_TENANT, hours)
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
        cur.execute('SELECT COUNT(*) as count FROM commits WHERE tenant_id = %s', (DEFAULT_TENANT,))
        commit_count = cur.fetchone()['count']

        # Count blobs
        cur.execute('SELECT COUNT(*) as count FROM blobs WHERE tenant_id = %s', (DEFAULT_TENANT,))
        blob_count = cur.fetchone()['count']

        # Total storage
        cur.execute('SELECT COALESCE(SUM(byte_size), 0) as total FROM blobs WHERE tenant_id = %s', (DEFAULT_TENANT,))
        total_storage = cur.fetchone()['total']

        # API calls in last 24h
        cur.execute('''
            SELECT COUNT(*) as count FROM audit_logs
            WHERE tenant_id = %s AND timestamp > NOW() - INTERVAL '24 hours'
        ''', (DEFAULT_TENANT,))
        api_calls_24h = cur.fetchone()['count']

        # Request volume by day (last 7 days)
        cur.execute('''
            SELECT DATE(timestamp) as day, COUNT(*) as requests
            FROM audit_logs
            WHERE tenant_id = %s AND timestamp > NOW() - INTERVAL '7 days'
            GROUP BY DATE(timestamp)
            ORDER BY day
        ''', (DEFAULT_TENANT,))
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
        ''', (DEFAULT_TENANT,))
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
        ''', (DEFAULT_TENANT,))
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
    """Create a new task for agent coordination."""
    data = request.get_json() or {}
    description = data.get('description')
    branch = data.get('branch')
    assigned_to = data.get('assigned_to')
    priority = data.get('priority', 5)
    deadline = data.get('deadline')
    metadata = data.get('metadata', {})

    if not description:
        return jsonify({'error': 'Description required'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        cur.execute(
            '''INSERT INTO tasks (tenant_id, description, branch, assigned_to, status, priority, deadline, metadata)
               VALUES (%s, %s, %s, %s, 'open', %s, %s, %s)
               RETURNING id, created_at''',
            (DEFAULT_TENANT, description, branch, assigned_to, priority, deadline, json.dumps(metadata))
        )
        row = cur.fetchone()
        task_id = str(row['id'])
        created_at = str(row['created_at'])
        db.commit()
        cur.close()

        return jsonify({
            'status': 'created',
            'task_id': task_id,
            'description': description,
            'branch': branch,
            'assigned_to': assigned_to,
            'priority': priority,
            'created_at': created_at
        }), 201

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
    params = [DEFAULT_TENANT]

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
    allowed_fields = ['description', 'branch', 'assigned_to', 'status', 'priority', 'deadline', 'metadata']
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

        params.extend([task_id, DEFAULT_TENANT])

        sql = f'''UPDATE tasks SET {', '.join(set_clauses)}
                  WHERE id = %s AND tenant_id = %s
                  RETURNING *'''

        cur.execute(sql, params)
        row = cur.fetchone()

        if not row:
            cur.close()
            return jsonify({'error': 'Task not found'}), 404

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


@app.route('/v2/tasks/<task_id>/claim', methods=['POST'])
def claim_task(task_id):
    """Claim a task for an agent instance. Includes collision detection."""
    data = request.get_json() or {}
    instance_id = data.get('instance_id')

    if not instance_id:
        return jsonify({'error': 'instance_id required'}), 400

    db = get_db()
    cur = get_cursor()

    try:
        # Check if task exists and is claimable
        cur.execute(
            'SELECT * FROM tasks WHERE id = %s AND tenant_id = %s',
            (task_id, DEFAULT_TENANT)
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
            (task_id, DEFAULT_TENANT)
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
            (DEFAULT_TENANT, task_id, instance_id)
        )
        claim_row = cur.fetchone()

        # Update task status
        cur.execute(
            '''UPDATE tasks SET status = 'claimed', assigned_to = %s
               WHERE id = %s AND tenant_id = %s''',
            (instance_id, task_id, DEFAULT_TENANT)
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
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500


@app.route('/v2/tasks/<task_id>/release', methods=['POST'])
def release_task(task_id):
    """Release a task claim."""
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
            (task_id, instance_id, DEFAULT_TENANT)
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
            (new_status, task_id, DEFAULT_TENANT)
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
            (DEFAULT_TENANT, task_prompt, branch, agent_id, json.dumps(metadata))
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
            (blob_hash, DEFAULT_TENANT, content_str, 'agent_spawn', now, len(content_str))
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
# API KEY MANAGEMENT (W1P3 - CC1)
# =============================================================================

from auth.api_keys import init_api_keys
api_keys_bp = init_api_keys(get_db, get_cursor)
app.register_blueprint(api_keys_bp)


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
        (user_id, DEFAULT_TENANT)
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
