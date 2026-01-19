

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
        if row['embedding']:
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
        if row['centroid']:
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

