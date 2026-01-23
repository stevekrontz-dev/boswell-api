#!/usr/bin/env python3
"""Add routing check to create_commit"""

with open('app.py', 'r') as f:
    content = f.read()

old = '''            except Exception as e:
                print(f"[EMBEDDING] Failed to store embedding: {e}", file=sys.stderr)

        tree_hash = compute_hash(f"{branch}:{blob_hash}:{now}")'''

new = '''            except Exception as e:
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
                    if row['centroid']:
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

        tree_hash = compute_hash(f"{branch}:{blob_hash}:{now}")'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print('Added routing check to create_commit')
