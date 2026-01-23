#!/usr/bin/env python3
"""Add routing_suggestion to commit response"""

with open('app.py', 'r') as f:
    content = f.read()

old = '''        return jsonify({
            'status': 'committed',
            'commit_hash': commit_hash,
            'blob_hash': blob_hash,
            'tree_hash': tree_hash,
            'branch': branch,
            'message': message
        }), 201'''

new = '''        response = {
            'status': 'committed',
            'commit_hash': commit_hash,
            'blob_hash': blob_hash,
            'tree_hash': tree_hash,
            'branch': branch,
            'message': message
        }
        if routing_suggestion:
            response['routing_suggestion'] = routing_suggestion
        return jsonify(response), 201'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print('Added routing_suggestion to commit response')
