#!/usr/bin/env python3
"""Fix all numpy array boolean checks"""

with open('app.py', 'r') as f:
    content = f.read()

# Fix in validate_commit_routing
old = '''    for row in cur.fetchall():
        if row['centroid']:
            similarity = cosine_similarity(embedding, row['centroid'])'''

new = '''    for row in cur.fetchall():
        if row['centroid'] is not None:
            similarity = cosine_similarity(embedding, row['centroid'])'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print('Fixed centroid boolean check')
