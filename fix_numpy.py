#!/usr/bin/env python3
"""Fix numpy array boolean check"""

with open('app.py', 'r') as f:
    content = f.read()

old = '''    embeddings = []
    for row in cur.fetchall():
        if row['embedding']:
            embeddings.append(row['embedding'])'''

new = '''    embeddings = []
    for row in cur.fetchall():
        if row['embedding'] is not None:
            embeddings.append(row['embedding'])'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print('Fixed numpy array boolean check')
