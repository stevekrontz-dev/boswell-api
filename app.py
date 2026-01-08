#!/usr/bin/env python3
"""
Boswell v2 API - Git-Style Memory Architecture
Railway deployment version
"""

import sqlite3
import hashlib
import json
import os
from datetime import datetime
from flask import Flask, request, jsonify, g
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Database path - use volume mount on Railway
DATABASE = os.environ.get('BOSWELL_DB', '/data/boswell_v2.db')

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
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def compute_hash(content):
    """Compute SHA-256 hash for content-addressable storage."""
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()

def get_current_head(branch='command-center'):
    """Get the current HEAD commit for a branch."""
    db = get_db()
    cur = db.execute(
        'SELECT head_commit FROM branches WHERE name = ?',
        (branch,)
    )
    row = cur.fetchone()
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
        db = get_db()
        cur = db.execute('SELECT COUNT(*) as count FROM branches')
        branch_count = cur.fetchone()['count']
        cur = db.execute('SELECT COUNT(*) as count FROM commits')
        commit_count = cur.fetchone()['count']
        return jsonify({
            'status': 'ok',
            'service': 'boswell-v2',
            'version': '2.5.0',
            'platform': 'railway',
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
    db = get_db()

    cur = db.execute('SELECT * FROM branches WHERE name = ?', (branch,))
    branch_info = cur.fetchone()

    if not branch_info:
        return jsonify({'error': f'Branch {branch} not found'}), 404

    head_commit = branch_info['head_commit']
    commit_info = None
    if head_commit and head_commit != 'GENESIS':
        cur = db.execute('SELECT * FROM commits WHERE commit_hash = ?', (head_commit,))
        commit_row = cur.fetchone()
        if commit_row:
            commit_info = dict(commit_row)

    return jsonify({
        'branch': branch,
        'head_commit': head_commit,
        'description': branch_info['description'],
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

    db = get_db()
    cur = db.execute('SELECT * FROM branches WHERE name = ?', (branch,))
    branch_info = cur.fetchone()

    if not branch_info:
        return jsonify({'error': f'Branch {branch} not found'}), 404

    return jsonify({
        'status': 'checked_out',
        'branch': branch,
        'head_commit': branch_info['head_commit'],
        'description': branch_info['description']
    })

@app.route('/v2/branches', methods=['GET'])
def list_branches():
    """List all cognitive branches."""
    db = get_db()
    cur = db.execute('SELECT * FROM branches ORDER BY name')
    branches = [dict(row) for row in cur.fetchall()]
    return jsonify({'branches': branches, 'count': len(branches)})

@app.route('/v2/branch', methods=['POST'])
def create_branch():
    """Create a new cognitive branch."""
    data = request.get_json() or {}
    name = data.get('name')
    description = data.get('description', '')
    from_branch = data.get('from', 'command-center')

    if not name:
        return jsonify({'error': 'Branch name required'}), 400

    db = get_db()
    cur = db.execute('SELECT name FROM branches WHERE name = ?', (name,))
    if cur.fetchone():
        return jsonify({'error': f'Branch {name} already exists'}), 409

    cur = db.execute('SELECT head_commit FROM branches WHERE name = ?', (from_branch,))
    source = cur.fetchone()
    head_commit = source['head_commit'] if source else 'GENESIS'

    now = datetime.utcnow().isoformat() + 'Z'
    db.execute(
        '''INSERT INTO branches (name, head_commit, description, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)''',
        (name, head_commit, description, now, now)
    )
    db.commit()

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
    now = datetime.utcnow().isoformat() + 'Z'

    content_str = json.dumps(content) if isinstance(content, dict) else str(content)
    blob_hash = compute_hash(content_str)

    try:
        db.execute(
            '''INSERT OR IGNORE INTO blobs (blob_hash, content, content_type, created_at, byte_size)
               VALUES (?, ?, ?, ?, ?)''',
            (blob_hash, content_str, memory_type, now, len(content_str))
        )
    except sqlite3.IntegrityError:
        pass

    tree_hash = compute_hash(f"{branch}:{blob_hash}:{now}")
    db.execute(
        '''INSERT INTO tree_entries (tree_hash, name, blob_hash, mode)
           VALUES (?, ?, ?, ?)''',
        (tree_hash, message[:100], blob_hash, memory_type)
    )

    cur = db.execute('SELECT head_commit FROM branches WHERE name = ?', (branch,))
    branch_row = cur.fetchone()
    parent_hash = branch_row['head_commit'] if branch_row else None
    if parent_hash == 'GENESIS':
        parent_hash = None

    commit_data = f"{tree_hash}:{parent_hash}:{message}:{now}"
    commit_hash = compute_hash(commit_data)

    db.execute(
        '''INSERT INTO commits (commit_hash, tree_hash, parent_hash, author, message, created_at)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (commit_hash, tree_hash, parent_hash, author, message, now)
    )

    db.execute(
        'UPDATE branches SET head_commit = ?, updated_at = ? WHERE name = ?',
        (commit_hash, now, branch)
    )

    for tag in tags:
        tag_str = tag if isinstance(tag, str) else str(tag)
        db.execute(
            '''INSERT OR IGNORE INTO tags (name, commit_hash, created_at)
               VALUES (?, ?, ?)''',
            (tag_str, commit_hash, now)
        )

    db.commit()

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

    db = get_db()
    cur = db.execute('SELECT head_commit FROM branches WHERE name = ?', (branch,))
    branch_row = cur.fetchone()

    if not branch_row:
        return jsonify({'branch': branch, 'commits': [], 'count': 0})

    head_commit = branch_row['head_commit']
    if head_commit == 'GENESIS':
        return jsonify({'branch': branch, 'head': 'GENESIS', 'commits': [], 'count': 0})

    commits = []
    current_hash = head_commit

    while current_hash and len(commits) < limit:
        cur = db.execute('SELECT * FROM commits WHERE commit_hash = ?', (current_hash,))
        commit = cur.fetchone()
        if not commit:
            break
        commits.append(dict(commit))
        current_hash = commit['parent_hash']

    return jsonify({'branch': branch, 'commits': commits, 'count': len(commits)})

@app.route('/v2/search', methods=['GET'])
def search_memories():
    """Search memories across branches."""
    query = request.args.get('q', '')
    branch = request.args.get('branch')
    memory_type = request.args.get('type')
    limit = request.args.get('limit', 20, type=int)

    if not query:
        return jsonify({'error': 'Search query required'}), 400

    db = get_db()

    sql = '''
        SELECT DISTINCT b.blob_hash, b.content, b.content_type, b.created_at,
               c.commit_hash, c.message, c.author
        FROM blobs b
        JOIN tree_entries t ON b.blob_hash = t.blob_hash
        JOIN commits c ON t.tree_hash = c.tree_hash
        WHERE b.content LIKE ?
    '''
    params = [f'%{query}%']

    if memory_type:
        sql += ' AND b.content_type = ?'
        params.append(memory_type)

    sql += ' ORDER BY b.created_at DESC LIMIT ?'
    params.append(limit)

    cur = db.execute(sql, params)
    results = []

    for row in cur.fetchall():
        results.append({
            'blob_hash': row['blob_hash'],
            'content': row['content'][:500] + '...' if len(row['content']) > 500 else row['content'],
            'content_type': row['content_type'],
            'created_at': row['created_at'],
            'commit_hash': row['commit_hash'],
            'message': row['message'],
            'author': row['author']
        })

    return jsonify({'query': query, 'results': results, 'count': len(results)})

@app.route('/v2/recall', methods=['GET'])
def recall_memory():
    """Recall a specific memory by hash."""
    blob_hash = request.args.get('hash')
    commit_hash = request.args.get('commit')

    db = get_db()

    if blob_hash:
        cur = db.execute('SELECT * FROM blobs WHERE blob_hash = ?', (blob_hash,))
        blob = cur.fetchone()
        if not blob:
            return jsonify({'error': 'Memory not found'}), 404
        return jsonify({
            'blob_hash': blob['blob_hash'],
            'content': blob['content'],
            'content_type': blob['content_type'],
            'created_at': blob['created_at'],
            'byte_size': blob['byte_size']
        })

    elif commit_hash:
        cur = db.execute(
            '''SELECT c.*, b.content, b.content_type
               FROM commits c
               JOIN tree_entries t ON c.tree_hash = t.tree_hash
               JOIN blobs b ON t.blob_hash = b.blob_hash
               WHERE c.commit_hash = ?''',
            (commit_hash,)
        )
        commit = cur.fetchone()
        if not commit:
            return jsonify({'error': 'Commit not found'}), 404
        return jsonify(dict(commit))

    return jsonify({'error': 'Hash or commit required'}), 400

@app.route('/v2/quick-brief', methods=['GET'])
def quick_brief():
    """Get a context brief for current state."""
    branch = request.args.get('branch', 'command-center')

    db = get_db()
    cur = db.execute('SELECT * FROM branches WHERE name = ?', (branch,))
    branch_info = cur.fetchone()

    if not branch_info:
        return jsonify({'error': f'Branch {branch} not found'}), 404

    cur = db.execute(
        '''SELECT commit_hash, message, created_at, author
           FROM commits ORDER BY created_at DESC LIMIT 5'''
    )
    recent_commits = [dict(row) for row in cur.fetchall()]

    cur = db.execute(
        '''SELECT id as session_id, committed_to_branch as branch, actions_summary as summary, synced_at
           FROM sessions WHERE commit_hash IS NULL ORDER BY synced_at DESC LIMIT 5'''
    )
    pending_sessions = [dict(row) for row in cur.fetchall()]

    cur = db.execute('SELECT name, description FROM branches')
    branches = [dict(row) for row in cur.fetchall()]

    return jsonify({
        'current_branch': branch,
        'branch_description': branch_info['description'],
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
    created_by = data.get('created_by', 'claude')
    reasoning = data.get('reasoning', '')

    if not all([source_blob, target_blob, source_branch, target_branch]):
        return jsonify({'error': 'source_blob, target_blob, source_branch, target_branch required'}), 400

    valid_types = ['resonance', 'causal', 'contradiction', 'elaboration', 'application']
    if link_type not in valid_types:
        return jsonify({'error': f'Invalid link_type. Must be one of: {valid_types}'}), 400

    db = get_db()
    now = datetime.utcnow().isoformat() + 'Z'

    try:
        db.execute(
            '''INSERT INTO cross_references
               (source_blob, target_blob, source_branch, target_branch,
                link_type, weight, created_by, reasoning, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (source_blob, target_blob, source_branch, target_branch,
             link_type, weight, created_by, reasoning, now)
        )
        db.commit()

        return jsonify({
            'status': 'linked',
            'source_blob': source_blob,
            'target_blob': target_blob,
            'link_type': link_type,
            'created_at': now
        }), 201

    except sqlite3.IntegrityError as e:
        if 'UNIQUE' in str(e):
            return jsonify({'error': 'Link already exists between these blobs'}), 409
        return jsonify({'error': str(e)}), 400

@app.route('/v2/links', methods=['GET'])
def list_links():
    """List cross-references with optional filtering."""
    blob = request.args.get('blob')
    branch = request.args.get('branch')
    link_type = request.args.get('type')
    created_by = request.args.get('created_by')
    limit = request.args.get('limit', 50, type=int)

    db = get_db()

    sql = 'SELECT * FROM cross_references WHERE 1=1'
    params = []

    if blob:
        sql += ' AND (source_blob = ? OR target_blob = ?)'
        params.extend([blob, blob])

    if branch:
        sql += ' AND (source_branch = ? OR target_branch = ?)'
        params.extend([branch, branch])

    if link_type:
        sql += ' AND link_type = ?'
        params.append(link_type)

    if created_by:
        sql += ' AND created_by = ?'
        params.append(created_by)

    sql += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)

    cur = db.execute(sql, params)
    links = [dict(row) for row in cur.fetchall()]

    return jsonify({'links': links, 'count': len(links)})

@app.route('/v2/graph', methods=['GET'])
def get_graph():
    """Get graph representation for visualization."""
    branch = request.args.get('branch')
    limit = request.args.get('limit', 100, type=int)

    db = get_db()

    if branch:
        nodes_sql = '''
            SELECT DISTINCT b.blob_hash, b.content_type, b.created_at,
                   substr(b.content, 1, 200) as preview
            FROM blobs b
            JOIN tree_entries t ON b.blob_hash = t.blob_hash
            JOIN commits c ON t.tree_hash = c.tree_hash
            JOIN branches br ON c.commit_hash = br.head_commit OR c.parent_hash IS NOT NULL
            WHERE br.name = ?
            LIMIT ?
        '''
        cur = db.execute(nodes_sql, (branch, limit))
    else:
        nodes_sql = '''
            SELECT blob_hash, content_type, created_at,
                   substr(content, 1, 200) as preview
            FROM blobs ORDER BY created_at DESC LIMIT ?
        '''
        cur = db.execute(nodes_sql, (limit,))

    nodes = []
    for row in cur.fetchall():
        nodes.append({
            'id': row['blob_hash'],
            'type': row['content_type'],
            'created_at': row['created_at'],
            'preview': row['preview']
        })

    if branch:
        edges_sql = '''
            SELECT * FROM cross_references
            WHERE source_branch = ? OR target_branch = ? LIMIT ?
        '''
        cur = db.execute(edges_sql, (branch, branch, limit))
    else:
        edges_sql = 'SELECT * FROM cross_references LIMIT ?'
        cur = db.execute(edges_sql, (limit,))

    edges = []
    for row in cur.fetchall():
        edges.append({
            'source': row['source_blob'],
            'target': row['target_blob'],
            'type': row['link_type'],
            'weight': row['weight'],
            'reasoning': row['reasoning']
        })

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

    db = get_db()

    sql = '''
        SELECT blob_hash, link_count, content_type, preview, branches
        FROM (
            SELECT
                b.blob_hash,
                b.content_type,
                substr(b.content, 1, 500) as preview,
                (SELECT COUNT(*) FROM cross_references cr
                 WHERE cr.source_blob = b.blob_hash OR cr.target_blob = b.blob_hash) as link_count,
                (SELECT GROUP_CONCAT(DISTINCT
                    CASE WHEN cr2.source_blob = b.blob_hash THEN cr2.target_branch
                         ELSE cr2.source_branch END)
                 FROM cross_references cr2
                 WHERE cr2.source_blob = b.blob_hash OR cr2.target_blob = b.blob_hash) as branches
            FROM blobs b
        )
        WHERE link_count >= ?
        ORDER BY link_count DESC
        LIMIT ?
    '''

    cur = db.execute(sql, (min_links, limit))
    insights = []

    for row in cur.fetchall():
        insights.append({
            'blob_hash': row['blob_hash'],
            'link_count': row['link_count'],
            'content_type': row['content_type'],
            'preview': row['preview'],
            'connected_branches': row['branches'].split(',') if row['branches'] else []
        })

    cross_branch_sql = '''
        SELECT cr.*,
               substr(b1.content, 1, 200) as source_preview,
               substr(b2.content, 1, 200) as target_preview
        FROM cross_references cr
        JOIN blobs b1 ON cr.source_blob = b1.blob_hash
        JOIN blobs b2 ON cr.target_blob = b2.blob_hash
        WHERE cr.source_branch != cr.target_branch
        ORDER BY cr.weight DESC, cr.created_at DESC
        LIMIT ?
    '''
    cur = db.execute(cross_branch_sql, (limit,))
    cross_branch_links = [dict(row) for row in cur.fetchall()]

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
    now = datetime.utcnow().isoformat() + 'Z'
    branch = get_branch_for_project(project)
    content_str = json.dumps(content) if isinstance(content, dict) else str(content)

    db.execute(
        '''INSERT OR REPLACE INTO sessions
           (session_id, branch, content, summary, synced_at, status)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (session_id, branch, content_str, summary, now, 'synced')
    )
    db.commit()

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

    db = get_db()

    sql = 'SELECT * FROM sessions WHERE 1=1'
    params = []

    if branch:
        sql += ' AND branch = ?'
        params.append(branch)

    if status:
        sql += ' AND status = ?'
        params.append(status)

    sql += ' ORDER BY synced_at DESC LIMIT ?'
    params.append(limit)

    cur = db.execute(sql, params)
    sessions = [dict(row) for row in cur.fetchall()]

    return jsonify({'sessions': sessions, 'count': len(sessions)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
