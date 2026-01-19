#!/usr/bin/env python3
"""Add routing check to create_commit"""

with open('app.py', 'r') as f:
    content = f.read()

# Find the insertion point - after the initial validation
old = '''    if not content:
        return jsonify({'error': 'Content required'}), 400

    # W2P4: Check commit limit before creating'''

new = '''    if not content:
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

    # W2P4: Check commit limit before creating'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print('Added routing check to create_commit')
