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
from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
import time
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
        # Register pgvector for embedding queries (if available)
        if PGVECTOR_AVAILABLE and register_vector:
            try:
                register_vector(g.db)
            except Exception:
                pass  # pgvector extension not in DB, skip
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

@app.route('/api/health', methods=['GET'])
@app.route('/v2/health', methods=['GET'])
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
    """List all cognitive branches for the authenticated user."""
    from auth import verify_jwt

    # Get user's tenant_id from JWT
    auth_header = request.headers.get('Authorization', '')
    tenant_id = DEFAULT_TENANT  # Fallback for API key auth

    if auth_header.startswith('Bearer '):
        try:
            token = auth_header[7:]
            payload = verify_jwt(token)
            user_id = payload.get('sub')

            # Get user's tenant_id
            cur = get_cursor()
            cur.execute('SELECT tenant_id FROM users WHERE id = %s', (user_id,))
            user = cur.fetchone()
            if user and user.get('tenant_id'):
                tenant_id = str(user['tenant_id'])
            cur.close()
        except ValueError:
            pass  # Fall back to DEFAULT_TENANT

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
    from auth import verify_jwt

    data = request.get_json() or {}
    name = data.get('name')
    from_branch = data.get('from', 'command-center')

    if not name:
        return jsonify({'error': 'Branch name required'}), 400

    # Get user's tenant_id from JWT (same pattern as list_branches)
    auth_header = request.headers.get('Authorization', '')
    tenant_id = DEFAULT_TENANT  # Fallback for API key auth

    if auth_header.startswith('Bearer '):
        try:
            token = auth_header[7:]
            payload = verify_jwt(token)
            user_id = payload.get('sub')

            # Get user's tenant_id
            cur = get_cursor()
            cur.execute('SELECT tenant_id FROM users WHERE id = %s', (user_id,))
            user = cur.fetchone()
            if user and user.get('tenant_id'):
                tenant_id = str(user['tenant_id'])
            cur.close()
        except ValueError:
            pass  # Fall back to DEFAULT_TENANT

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
    from auth import verify_jwt

    if not name:
        return jsonify({'error': 'Branch name required'}), 400

    # Prevent deleting core branches
    protected_branches = ['main', 'command-center']
    if name in protected_branches:
        return jsonify({'error': f'Cannot delete protected branch: {name}'}), 403

    # Get user's tenant_id from JWT
    auth_header = request.headers.get('Authorization', '')
    tenant_id = DEFAULT_TENANT

    if auth_header.startswith('Bearer '):
        try:
            token = auth_header[7:]
            payload = verify_jwt(token)
            user_id = payload.get('sub')

            cur = get_cursor()
            cur.execute('SELECT tenant_id FROM users WHERE id = %s', (user_id,))
            user = cur.fetchone()
            if user and user.get('tenant_id'):
                tenant_id = str(user['tenant_id'])
            cur.close()
        except ValueError:
            pass

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
            """, (DEFAULT_TENANT,))
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
    tenant_id = request.headers.get('X-Tenant-ID', DEFAULT_TENANT)
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

        # Generate and store embedding for semantic search
        embedding = generate_embedding(content_str)
        if embedding:
            try:
                cur.execute(
                    '''UPDATE blobs SET embedding = %s WHERE blob_hash = %s AND tenant_id = %s''',
                    (embedding, blob_hash, DEFAULT_TENANT)
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
                """, (DEFAULT_TENANT,))
                
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
            (DEFAULT_TENANT, tree_hash, message[:100], blob_hash, memory_type)
        )

        cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', (branch, DEFAULT_TENANT))
        branch_row = cur.fetchone()
        if branch_row:
            branch = branch_row['name']  # Use canonical casing
            parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
        else:
            # Auto-create branch on first commit
            cur.execute(
                '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
                   VALUES (%s, %s, %s, %s)''',
                (DEFAULT_TENANT, branch, 'GENESIS', now)
            )
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
            try:
                cur.execute(
                    '''INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
                       VALUES (%s, %s, %s, %s)''',
                    (DEFAULT_TENANT, blob_hash, tag_str, now)
                )
            except Exception:
                # Tag already exists, ignore duplicate
                pass

        db.commit()
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
            (source_hash, DEFAULT_TENANT)
        )
        source_commit = cur.fetchone()
        
        if not source_commit:
            cur.close()
            return jsonify({'error': 'Source commit not found'}), 404
        
        # 2. Get the blob via tree_entry
        cur.execute(
            'SELECT blob_hash, name, mode FROM tree_entries WHERE tree_hash = %s AND tenant_id = %s',
            (source_commit['tree_hash'], DEFAULT_TENANT)
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
            (DEFAULT_TENANT, new_tree_hash, f"[cherry-pick] {original_message}", blob_hash, memory_type)
        )
        
        # 4. Get or create target branch
        cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', 
                    (target_branch, DEFAULT_TENANT))
        branch_row = cur.fetchone()
        
        if branch_row:
            target_branch = branch_row['name']  # canonical casing
            parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
        else:
            # Auto-create branch
            cur.execute(
                '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
                   VALUES (%s, %s, %s, %s)''',
                (DEFAULT_TENANT, target_branch, 'GENESIS', now)
            )
            parent_hash = None
        
        # 5. Create new commit
        cherry_pick_message = f"[cherry-pick from {source_hash[:8]}] {original_message}"
        commit_data = f"{new_tree_hash}:{parent_hash}:{cherry_pick_message}:{now}"
        new_commit_hash = compute_hash(commit_data)
        
        cur.execute(
            '''INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (new_commit_hash, DEFAULT_TENANT, new_tree_hash, parent_hash, 'claude', cherry_pick_message, now)
        )
        
        # 6. Update target branch head
        cur.execute(
            'UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s',
            (new_commit_hash, target_branch, DEFAULT_TENANT)
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
            (commit_hash, DEFAULT_TENANT)
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
            (commit_hash, DEFAULT_TENANT, reason, reason)
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


@app.route('/v2/semantic-search', methods=['GET'])
def semantic_search():
    """Semantic search using vector embeddings.

    Query params:
    - q: Search query (required)
    - limit: Max results (default: 10)
    """
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

    # Vector cosine search using pgvector (excluding deprecated commits)
    cur.execute("""
        SELECT b.blob_hash, b.content, b.content_type, b.created_at,
               c.commit_hash, c.message, c.author,
               b.embedding <=> %s::vector AS distance
        FROM blobs b
        JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
        JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
        LEFT JOIN deprecated_commits dc ON c.commit_hash = dc.commit_hash
        WHERE b.embedding IS NOT NULL AND b.tenant_id = %s AND dc.commit_hash IS NULL
        ORDER BY distance
        LIMIT %s
    """, (query_embedding, DEFAULT_TENANT, limit))

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
            'distance': float(row['distance'])
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


@app.route('/v2/startup', methods=['GET'])
def semantic_startup():
    """v3 semantic startup - pull contextually relevant memories.

    Uses semantic search to find the most relevant memories for the
    current conversation context, rather than hardcoded lookups.

    Query params:
    - context: Optional context string to search for relevant memories
    - k: Number of relevant memories to return (default: 5)
    - agent_id: Optional agent ID to filter tasks assigned to this agent
    """
    context = request.args.get('context', 'important decisions and active commitments')
    k = request.args.get('k', 5, type=int)
    agent_id = request.args.get('agent_id')  # Filter tasks for specific agent

    cur = get_cursor()

    # Always include sacred commitments via literal search
    sacred_manifest = None
    tool_registry = None

    # Fetch sacred_manifest
    cur.execute("""
        SELECT b.content FROM blobs b
        WHERE b.content LIKE %s AND b.tenant_id = %s
        ORDER BY b.created_at DESC LIMIT 1
    """, ('%"type": "sacred_manifest"%', DEFAULT_TENANT))
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
    """, ('%"type": "tool_registry"%', DEFAULT_TENANT))
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
                       c.message, b.embedding <=> %s::vector AS distance
                FROM blobs b
                JOIN tree_entries t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
                JOIN commits c ON t.tree_hash = c.tree_hash AND t.tenant_id = c.tenant_id
                WHERE b.embedding IS NOT NULL AND b.tenant_id = %s
                ORDER BY distance LIMIT %s
            """, (query_embedding, DEFAULT_TENANT, k))
            for row in cur.fetchall():
                relevant_memories.append({
                    'blob_hash': row['blob_hash'],
                    'preview': row['preview'],
                    'message': row['message'],
                    'distance': float(row['distance'])
                })

    # Get open tasks (priority 1-3 = high, show first)
    # If agent_id provided, show: their assigned tasks + unassigned tasks
    # If no agent_id, show all open tasks
    open_tasks = []
    my_tasks = []  # Tasks assigned specifically to this agent
    try:
        if agent_id:
            # Get tasks assigned to this agent
            cur.execute("""
                SELECT id, description, branch, assigned_to, priority, created_at, metadata
                FROM tasks 
                WHERE tenant_id = %s AND status = 'open' AND assigned_to = %s
                ORDER BY priority ASC, created_at ASC
            """, (DEFAULT_TENANT, agent_id))
            for row in cur.fetchall():
                my_tasks.append({
                    'id': str(row['id']),
                    'description': row['description'],
                    'branch': row['branch'],
                    'assigned_to': row['assigned_to'],
                    'priority': row['priority'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'metadata': row['metadata'] if row['metadata'] else {}
                })
            # Also get unassigned tasks (available to claim)
            cur.execute("""
                SELECT id, description, branch, assigned_to, priority, created_at, metadata
                FROM tasks 
                WHERE tenant_id = %s AND status = 'open' AND assigned_to IS NULL
                ORDER BY priority ASC, created_at ASC
                LIMIT 5
            """, (DEFAULT_TENANT,))
            for row in cur.fetchall():
                open_tasks.append({
                    'id': str(row['id']),
                    'description': row['description'],
                    'branch': row['branch'],
                    'assigned_to': row['assigned_to'],
                    'priority': row['priority'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'metadata': row['metadata'] if row['metadata'] else {}
                })
        else:
            # No agent_id - return all open tasks
            cur.execute("""
                SELECT id, description, branch, assigned_to, priority, created_at, metadata
                FROM tasks 
                WHERE tenant_id = %s AND status = 'open'
                ORDER BY priority ASC, created_at ASC
                LIMIT 10
            """, (DEFAULT_TENANT,))
            for row in cur.fetchall():
                open_tasks.append({
                    'id': str(row['id']),
                    'description': row['description'],
                    'branch': row['branch'],
                    'assigned_to': row['assigned_to'],
                    'priority': row['priority'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'metadata': row['metadata'] if row['metadata'] else {}
                })
    except Exception as e:
        # tasks table might not exist - that's ok
        pass

    cur.close()
    
    response = {
        'sacred_manifest': sacred_manifest,
        'tool_registry': tool_registry,
        'relevant_memories': relevant_memories,
        'open_tasks': open_tasks,
        'context_used': context,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    # If agent_id provided, add their specific tasks
    if agent_id:
        response['agent_id'] = agent_id
        response['my_tasks'] = my_tasks
    
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
                   b.content as preview
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
                   content as preview
            FROM blobs WHERE tenant_id = %s ORDER BY created_at DESC LIMIT %s
        '''
        cur.execute(nodes_sql, (DEFAULT_TENANT, limit))

    rows = cur.fetchall()

    # Batch lookup branches for all blobs (O(1) queries instead of O(N))
    blob_hashes = [row['blob_hash'] for row in rows]
    branch_map = get_blob_branches_batch(cur, blob_hashes, DEFAULT_TENANT)

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
        cur.execute('SELECT COUNT(*) as cnt FROM blobs WHERE tenant_id = %s', (DEFAULT_TENANT,))
        blob_count = cur.fetchone()['cnt']

        # Test 2: Can we get embeddings?
        cur.execute('''
            SELECT blob_hash, embedding
            FROM blobs
            WHERE embedding IS NOT NULL AND tenant_id = %s
            LIMIT 1
        ''', (DEFAULT_TENANT,))
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
    ''', (DEFAULT_TENANT,))

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
    ''', (DEFAULT_TENANT,))
    existing_links = set(row['link_key'] for row in cur.fetchall())

    # Also add reverse keys
    cur.execute('''
        SELECT target_blob || '-' || source_blob as link_key
        FROM cross_references
        WHERE tenant_id = %s
    ''', (DEFAULT_TENANT,))
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
                    source_branch = get_blob_branch(cur, blob_a['hash'], DEFAULT_TENANT)
                    target_branch = get_blob_branch(cur, blob_b['hash'], DEFAULT_TENANT)

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
        cur.execute('SELECT DISTINCT tag FROM tags WHERE tenant_id = %s', (DEFAULT_TENANT,))
        all_tags = [row['tag'] for row in cur.fetchall()]

        for tag in all_tags[:20]:  # Limit to 20 tags
            # Get blobs with this tag
            cur.execute('''
                SELECT b.blob_hash, b.embedding
                FROM blobs b
                JOIN tags t ON b.blob_hash = t.blob_hash AND b.tenant_id = t.tenant_id
                WHERE t.tag = %s AND b.embedding IS NOT NULL AND b.tenant_id = %s
            ''', (tag, DEFAULT_TENANT))
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
            ''', (DEFAULT_TENANT, tag, DEFAULT_TENANT))
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
                    DEFAULT_TENANT, link['source'], link['target'],
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
                ''', (DEFAULT_TENANT, tag_prop['blob_hash'], tag_prop['tag'], now))
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
    ''', (DEFAULT_TENANT,))
    count = cur.fetchone()['count']

    deleted = 0
    if not dry_run and count > 0:
        cur.execute('''
            DELETE FROM cross_references
            WHERE (source_branch = 'unknown' OR target_branch = 'unknown')
            AND tenant_id = %s
        ''', (DEFAULT_TENANT,))
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
        ''', (DEFAULT_TENANT,))
        row = cur.fetchone()
        blob_hash = row['blob_hash'] if row else None
        cur.close()

    if not blob_hash:
        return jsonify({'error': 'No blob found'}), 404

    cur = get_cursor()
    debug_info = {'blob_hash': blob_hash}

    # Step 1: Check if blob exists
    cur.execute('SELECT blob_hash FROM blobs WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, DEFAULT_TENANT))
    debug_info['blob_exists'] = cur.fetchone() is not None

    # Step 2: Check tree_entries for this blob
    cur.execute('SELECT tree_hash, name FROM tree_entries WHERE blob_hash = %s AND tenant_id = %s', (blob_hash, DEFAULT_TENANT))
    tree_entries = cur.fetchall()
    debug_info['tree_entries'] = [{'tree_hash': r['tree_hash'], 'name': r['name']} for r in tree_entries]

    # Step 3: For each tree_entry, find the commit
    commits_found = []
    for te in tree_entries:
        cur.execute('SELECT commit_hash, message FROM commits WHERE tree_hash = %s AND tenant_id = %s', (te['tree_hash'], DEFAULT_TENANT))
        commits = cur.fetchall()
        for c in commits:
            commits_found.append({'tree_hash': te['tree_hash'], 'commit_hash': c['commit_hash'], 'message': c['message'][:50]})
    debug_info['commits_found'] = commits_found

    # Step 4: Check branch heads
    cur.execute('SELECT name, head_commit FROM branches WHERE tenant_id = %s', (DEFAULT_TENANT,))
    branches = [{'name': r['name'], 'head_commit': r['head_commit']} for r in cur.fetchall()]
    debug_info['branches'] = branches

    # Step 5: Run the actual get_blob_branch function
    debug_info['detected_branch'] = get_blob_branch(cur, blob_hash, DEFAULT_TENANT)

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
    ''', (DEFAULT_TENANT, limit))
    
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
                    (embedding, blob_hash, DEFAULT_TENANT)
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
    cur2.execute('SELECT COUNT(*) as remaining FROM blobs WHERE tenant_id = %s AND embedding IS NULL', (DEFAULT_TENANT,))
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
    ''', (DEFAULT_TENANT,))
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
    """Create a new task for agent coordination.
    
    Also creates a memory commit to make the task discoverable via semantic search.
    """
    data = request.get_json() or {}
    description = data.get('description')
    branch = data.get('branch', 'command-center')
    assigned_to = data.get('assigned_to')
    priority = data.get('priority', 5)
    deadline = data.get('deadline')
    metadata = data.get('metadata', {})

    if not description:
        return jsonify({'error': 'Description required'}), 400

    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'

    try:
        # 1. Insert task into task queue
        cur.execute(
            '''INSERT INTO tasks (tenant_id, description, branch, assigned_to, status, priority, deadline, metadata)
               VALUES (%s, %s, %s, %s, 'open', %s, %s, %s)
               RETURNING id, created_at''',
            (DEFAULT_TENANT, description, branch, assigned_to, priority, deadline, json.dumps(metadata))
        )
        row = cur.fetchone()
        task_id = str(row['id'])
        created_at = str(row['created_at'])

        # 2. Create memory commit for discoverability
        memory_content = {
            'type': 'task_created',
            'task_id': task_id,
            'description': description,
            'branch': branch,
            'priority': priority,
            'assigned_to': assigned_to,
            'metadata': metadata
        }
        content_str = json.dumps(memory_content)
        blob_hash = compute_hash(content_str)

        # Insert blob
        cur.execute(
            '''INSERT INTO blobs (blob_hash, tenant_id, content, content_type, created_at, byte_size)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (blob_hash) DO NOTHING''',
            (blob_hash, DEFAULT_TENANT, content_str, 'task', now, len(content_str))
        )

        # Generate embedding for semantic search
        embedding = generate_embedding(content_str)
        if embedding:
            try:
                cur.execute(
                    '''UPDATE blobs SET embedding = %s WHERE blob_hash = %s AND tenant_id = %s''',
                    (embedding, blob_hash, DEFAULT_TENANT)
                )
            except Exception as e:
                print(f"[TASK] Failed to store embedding: {e}", file=sys.stderr)

        # Create tree entry
        tree_hash = compute_hash(f"{branch}:{blob_hash}:{now}")
        message = f"TASK: {description[:80]}{'...' if len(description) > 80 else ''}"
        cur.execute(
            '''INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
               VALUES (%s, %s, %s, %s, %s)''',
            (DEFAULT_TENANT, tree_hash, message[:100], blob_hash, 'task')
        )

        # Get parent commit (case-insensitive branch lookup)
        cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', (branch, DEFAULT_TENANT))
        branch_row = cur.fetchone()
        if branch_row:
            branch = branch_row['name']  # Use canonical casing
            parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
        else:
            # Auto-create branch
            cur.execute(
                '''INSERT INTO branches (tenant_id, name, head_commit, created_at)
                   VALUES (%s, %s, %s, %s)''',
                (DEFAULT_TENANT, branch, 'GENESIS', now)
            )
            parent_hash = None

        # Create commit
        commit_data = f"{tree_hash}:{parent_hash}:{message}:{now}"
        commit_hash = compute_hash(commit_data)

        cur.execute(
            '''INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (commit_hash, DEFAULT_TENANT, tree_hash, parent_hash, 'task-system', message, now)
        )

        # Update branch head
        cur.execute(
            'UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s',
            (commit_hash, branch, DEFAULT_TENANT)
        )

        # Add task_id tag for easy lookup
        cur.execute(
            '''INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
               VALUES (%s, %s, %s, %s)''',
            (DEFAULT_TENANT, blob_hash, f"task:{task_id}", now)
        )

        db.commit()
        cur.close()

        return jsonify({
            'status': 'created',
            'task_id': task_id,
            'commit_hash': commit_hash,
            'blob_hash': blob_hash,
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

        # Auto-clear checkpoint when task is marked done
        if updates.get('status') == 'done':
            try:
                cur.execute(
                    'DELETE FROM session_checkpoints WHERE task_id = %s AND tenant_id = %s',
                    (task_id, DEFAULT_TENANT)
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
            (task_id, DEFAULT_TENANT)
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
            cur.execute('SELECT halted, reason FROM halt_state WHERE tenant_id = %s', (DEFAULT_TENANT,))
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
    """, (DEFAULT_TENANT, open_hours))
    
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
    """, (DEFAULT_TENANT, claimed_hours))
    
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
        ''', (DEFAULT_TENANT, now, reason))

        # Set all claimed tasks to blocked
        cur.execute('''
            UPDATE tasks SET status = 'blocked'
            WHERE tenant_id = %s AND status = 'claimed'
            RETURNING id
        ''', (DEFAULT_TENANT,))
        affected_tasks = [str(row['id']) for row in cur.fetchall()]

        # Release all active claims with EMERGENCY_HALT reason
        cur.execute('''
            UPDATE task_claims SET released_at = %s, release_reason = 'EMERGENCY_HALT'
            WHERE tenant_id = %s AND released_at IS NULL
        ''', (now, DEFAULT_TENANT))

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
        if not cur.fetchone()[0]:
            cur.close()
            return jsonify({'status': 'not_halted', 'message': 'System was not halted'})

        # Clear halt state
        cur.execute('''
            UPDATE halt_state SET halted = FALSE
            WHERE tenant_id = %s
            RETURNING halted_at, reason
        ''', (DEFAULT_TENANT,))
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
        if not cur.fetchone()[0]:
            cur.close()
            return jsonify({'halted': False})

        cur.execute('''
            SELECT halted, halted_at, reason FROM halt_state
            WHERE tenant_id = %s
        ''', (DEFAULT_TENANT,))
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
    """
    db = get_db()
    cur = get_cursor()
    
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
        ''', (DEFAULT_TENANT,))
        
        tasks = cur.fetchall()
        
        for task in tasks:
            task_id = str(task['id'])
            
            # Check if already has memory
            cur.execute('''
                SELECT 1 FROM tags 
                WHERE tenant_id = %s AND tag = %s
                LIMIT 1
            ''', (DEFAULT_TENANT, f"task:{task_id}"))
            
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
                ''', (blob_hash, DEFAULT_TENANT, content_str, 'task', created_at, len(content_str)))
                
                # Generate and store embedding
                embedding = generate_embedding(content_str)
                if embedding:
                    cur.execute('''
                        UPDATE blobs SET embedding = %s WHERE blob_hash = %s AND tenant_id = %s
                    ''', (embedding, blob_hash, DEFAULT_TENANT))
                
                # Create tree entry
                tree_hash = compute_hash(f"{branch}:{blob_hash}:{created_at}")
                message = f"TASK: {task['description'][:80]}{'...' if len(task['description']) > 80 else ''}"
                
                cur.execute('''
                    INSERT INTO tree_entries (tenant_id, tree_hash, name, blob_hash, mode)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (DEFAULT_TENANT, tree_hash, message[:100], blob_hash, 'task'))
                
                # Get branch head (case-insensitive)
                cur.execute('SELECT head_commit, name FROM branches WHERE LOWER(name) = LOWER(%s) AND tenant_id = %s', (branch, DEFAULT_TENANT))
                branch_row = cur.fetchone()
                
                if branch_row:
                    branch = branch_row['name']  # Use canonical casing
                    parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
                else:
                    cur.execute('''
                        INSERT INTO branches (tenant_id, name, head_commit, created_at)
                        VALUES (%s, %s, %s, %s)
                    ''', (DEFAULT_TENANT, branch, 'GENESIS', created_at))
                    parent_hash = None
                
                # Create commit
                commit_data = f"{tree_hash}:{parent_hash}:{message}:{created_at}"
                commit_hash = compute_hash(commit_data)
                
                cur.execute('''
                    INSERT INTO commits (commit_hash, tenant_id, tree_hash, parent_hash, author, message, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (commit_hash, DEFAULT_TENANT, tree_hash, parent_hash, 'backfill', message, created_at))
                
                # Update branch head
                cur.execute('''
                    UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s
                ''', (commit_hash, branch, DEFAULT_TENANT))
                
                # Add tag
                cur.execute('''
                    INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
                    VALUES (%s, %s, %s, %s)
                ''', (DEFAULT_TENANT, blob_hash, f"task:{task_id}", created_at))
                
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
        cur.execute('SELECT id FROM tasks WHERE id = %s AND tenant_id = %s', (task_id, DEFAULT_TENANT))
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
        ''', (task_id, DEFAULT_TENANT, instance_id, progress, next_step, json.dumps(context_snapshot), expires_at))

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
        ''', (task_id, DEFAULT_TENANT))

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
        ''', (task_id, DEFAULT_TENANT))

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
        ''', (DEFAULT_TENANT, hours))

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
    """Create trails table if it doesn't exist."""
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
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(tenant_id, source_blob, target_blob)
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trails_strength ON trails(strength DESC)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trails_source ON trails(source_blob)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trails_target ON trails(target_blob)')
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
        ''', (DEFAULT_TENANT, source_blob, target_blob))

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
        ''', (DEFAULT_TENANT, limit))

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
        ''', (DEFAULT_TENANT, source_blob, limit))

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
        ''', (DEFAULT_TENANT, target_blob, limit))

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
    """Decay all trails by 10% and prune dead ones. Call via Railway cron daily."""
    ensure_trails_table()

    db = get_db()
    cur = get_cursor()

    try:
        cur.execute('''
            UPDATE trails SET strength = strength * 0.9
            WHERE tenant_id = %s
        ''', (DEFAULT_TENANT,))
        decayed_count = cur.rowcount

        cur.execute('''
            DELETE FROM trails
            WHERE tenant_id = %s AND strength < 0.01
            RETURNING id
        ''', (DEFAULT_TENANT,))
        pruned = [str(row['id']) for row in cur.fetchall()]

        db.commit()
        cur.close()

        return jsonify({
            'status': 'decayed',
            'trails_decayed': decayed_count,
            'trails_pruned': len(pruned),
            'pruned_ids': pruned,
            'decay_factor': 0.9,
            'prune_threshold': 0.01,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })

    except Exception as e:
        db.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500




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
    tenant_id = tenant_id or DEFAULT_TENANT
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
        cur.execute('SELECT name FROM branches WHERE tenant_id = %s', (DEFAULT_TENANT,))
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
                ''', (DEFAULT_TENANT, branch_name, centroid, count))
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
    ''', (DEFAULT_TENANT,))
    
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
    ''', (DEFAULT_TENANT,))
    
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

    # Require JWT authentication
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Authorization header required'}), 401

    try:
        token = auth_header[7:]
        payload = verify_jwt(token)
        user_id = payload.get('sub')
    except ValueError as e:
        return jsonify({'error': str(e)}), 401

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
    ctx_kwargs = {'method': method, 'path': path}
    if query_string:
        ctx_kwargs['query_string'] = query_string
    if json_data is not None:
        ctx_kwargs['json'] = json_data
        ctx_kwargs['content_type'] = 'application/json'
    
    with app.test_request_context(**ctx_kwargs):
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


# Tool definitions - inline for single-service deployment
MCP_TOOLS = [
    {
        "name": "boswell_brief",
        "description": "Get a quick context brief of current Boswell state - recent commits, pending sessions, all branches. Use this at conversation start to understand what's been happening.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch to focus on (default: command-center)", "default": "command-center"}
            }
        }
    },
    {
        "name": "boswell_branches",
        "description": "List all cognitive branches in Boswell. Branches are: tint-atlanta (CRM/business), iris (research/BCI), tint-empire (franchise), family (personal), command-center (infrastructure), boswell (memory system).",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_head",
        "description": "Get the current HEAD commit for a specific branch.",
        "inputSchema": {
            "type": "object",
            "properties": {"branch": {"type": "string", "description": "Branch name"}},
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_log",
        "description": "Get commit history for a branch. Shows what memories have been recorded.",
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
        "description": "Search memories across all branches by keyword. Returns matching content with commit info.",
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
        "description": "Semantic search using AI embeddings. Finds conceptually related memories even without exact keyword matches. Use for conceptual queries like 'decisions about architecture' or 'patent opportunities'.",
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
        "description": "Recall a specific memory by its blob hash or commit hash.",
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
        "description": "List resonance links between memories. Shows cross-branch connections.",
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
        "description": "Get the full memory graph - all nodes (memories) and edges (links). Useful for understanding the topology.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_reflect",
        "description": "Get AI-surfaced insights - highly connected memories and cross-branch patterns.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_commit",
        "description": "Commit a new memory to Boswell. Use this to preserve important decisions, insights, or context worth remembering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch to commit to (tint-atlanta, iris, tint-empire, family, command-center, boswell)"},
                "content": {"type": "object", "description": "Memory content as JSON object"},
                "message": {"type": "string", "description": "Commit message describing the memory"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags for categorization"}
            },
            "required": ["branch", "content", "message"]
        }
    },
    {
        "name": "boswell_link",
        "description": "Create a resonance link between two memories across branches. Links capture conceptual connections.",
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
        "description": "Switch focus to a different cognitive branch.",
        "inputSchema": {
            "type": "object",
            "properties": {"branch": {"type": "string", "description": "Branch to check out"}},
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_startup",
        "description": "Load startup context. Returns commitments + semantically relevant memories. Call FIRST every conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Optional context for semantic retrieval (default: 'important decisions and active commitments')"},
                "k": {"type": "integer", "description": "Number of relevant memories to return (default: 5)", "default": 5}
            }
        }
    },
    {
        "name": "boswell_create_task",
        "description": "Create a new task in the queue. Use to spawn subtasks or add work for yourself or other agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What needs to be done"},
                "branch": {"type": "string", "description": "Which branch this relates to (command-center, tint-atlanta, etc.)"},
                "priority": {"type": "integer", "description": "Priority 1-10 (1=highest, default=5)"},
                "assigned_to": {"type": "string", "description": "Optional: assign to specific instance"},
                "metadata": {"type": "object", "description": "Optional: additional context"}
            },
            "required": ["description"]
        }
    },
    {
        "name": "boswell_claim_task",
        "description": "Claim a task for this agent instance. Prevents other agents from working on it. Use when starting work on a task from the queue.",
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
        "description": "Release a claimed task. Use 'completed' when done, 'blocked' if stuck, 'manual' to unclaim without status change.",
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
        "description": "Update a task's fields (description, status, priority, metadata). Use to report progress or modify task details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to update"},
                "status": {"type": "string", "enum": ["open", "claimed", "blocked", "done"], "description": "New status"},
                "description": {"type": "string", "description": "Updated description"},
                "priority": {"type": "integer", "description": "Priority (1=highest)"},
                "metadata": {"type": "object", "description": "Additional metadata to merge"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_delete_task",
        "description": "Soft delete a task (sets status to 'deleted'). Use to clean up completed or cancelled tasks from the queue.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task ID to delete"}},
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_halt_tasks",
        "description": "EMERGENCY STOP - Halt all task processing. Blocks all claimed tasks, prevents new claims. Use when swarm behavior is problematic.",
        "inputSchema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Why halting (default: 'Manual emergency halt')"}}
        }
    },
    {
        "name": "boswell_resume_tasks",
        "description": "Resume task processing after a halt. Clears the halt flag and allows new claims.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_halt_status",
        "description": "Check if the task system is currently halted.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_record_trail",
        "description": "Record a traversal between two memories. Strengthens the path for future recall.",
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
        "description": "Get the strongest memory trails, sorted by strength. These are frequently traversed paths.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max trails to return (default: 20)"}}
        }
    },
    {
        "name": "boswell_trails_from",
        "description": "Get outbound trails from a specific memory. Shows what memories are often accessed after this one.",
        "inputSchema": {
            "type": "object",
            "properties": {"blob": {"type": "string", "description": "Source memory blob hash"}},
            "required": ["blob"]
        }
    },
    {
        "name": "boswell_trails_to",
        "description": "Get inbound trails to a specific memory. Shows what memories often lead to this one.",
        "inputSchema": {
            "type": "object",
            "properties": {"blob": {"type": "string", "description": "Target memory blob hash"}},
            "required": ["blob"]
        }
    },
    # Session Checkpoint Tools
    {
        "name": "boswell_checkpoint",
        "description": "Save a session checkpoint for crash recovery. Captures WHERE you are in a task (progress, next step, context). UPSERT semantics - one checkpoint per task.",
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
        "description": "Get a checkpoint for a task if one exists. Use to resume work after crash or context loss.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to resume"}
            },
            "required": ["task_id"]
        }
    },
    # Branch Fingerprint Tools
    {
        "name": "boswell_validate_routing",
        "description": "Check which branch best matches content before committing. Returns suggested branch and confidence scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "object", "description": "Content to analyze"},
                "branch": {"type": "string", "description": "Requested branch"}
            },
            "required": ["content"]
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
            "type": "memory"
        }
        if "tags" in args:
            payload["tags"] = args["tags"]
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
        for field in ["branch", "priority", "assigned_to", "metadata"]:
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
        for field in ["status", "description", "priority", "metadata"]:
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
                "version": MCP_SERVER_VERSION
            },
            "capabilities": {
                "tools": {"listChanged": False}
            }
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
    """, (DEFAULT_TENANT,))
    
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
