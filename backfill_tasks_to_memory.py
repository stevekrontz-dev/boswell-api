#!/usr/bin/env python3
"""
Backfill existing tasks into memory system.

Tasks created before the dual-write feature are orphaned from semantic search.
This script creates memory commits for all existing tasks.
"""

import os
import json
import hashlib
import psycopg2
import psycopg2.extras
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL')
DEFAULT_TENANT = '00000000-0000-0000-0000-000000000001'

# OpenAI for embeddings
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
openai_client = None

def get_openai_client():
    global openai_client
    if openai_client is None and OPENAI_API_KEY:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return openai_client

def generate_embedding(text):
    client = get_openai_client()
    if not client:
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
        print(f"  [EMBEDDING ERROR] {e}")
        return None

def compute_hash(data):
    return hashlib.sha256(data.encode()).hexdigest()

def backfill_tasks():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return
    
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Set tenant context
    cur.execute(f"SET app.current_tenant = '{DEFAULT_TENANT}'")
    
    # Get all tasks
    cur.execute('''
        SELECT id, description, branch, assigned_to, status, priority, metadata, created_at
        FROM tasks
        WHERE tenant_id = %s
        ORDER BY created_at ASC
    ''', (DEFAULT_TENANT,))
    
    tasks = cur.fetchall()
    print(f"Found {len(tasks)} tasks to backfill")
    
    backfilled = 0
    skipped = 0
    
    for task in tasks:
        task_id = str(task['id'])
        
        # Check if already has memory (tag exists)
        cur.execute('''
            SELECT 1 FROM tags 
            WHERE tenant_id = %s AND tag = %s
            LIMIT 1
        ''', (DEFAULT_TENANT, f"task:{task_id}"))
        
        if cur.fetchone():
            print(f"  [SKIP] Task {task_id} already has memory")
            skipped += 1
            continue
        
        branch = task['branch'] or 'command-center'
        created_at = task['created_at'].isoformat() + 'Z' if task['created_at'] else datetime.utcnow().isoformat() + 'Z'
        
        # Build memory content
        memory_content = {
            'type': 'task_created',
            'task_id': task_id,
            'description': task['description'],
            'branch': branch,
            'priority': task['priority'],
            'assigned_to': task['assigned_to'],
            'status': task['status'],
            'metadata': task['metadata'] if task['metadata'] else {}
        }
        content_str = json.dumps(memory_content)
        blob_hash = compute_hash(content_str)
        
        print(f"  [BACKFILL] Task {task_id}: {task['description'][:50]}...")
        
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
        
        # Get branch head
        cur.execute('SELECT head_commit FROM branches WHERE name = %s AND tenant_id = %s', (branch, DEFAULT_TENANT))
        branch_row = cur.fetchone()
        
        if branch_row:
            parent_hash = branch_row['head_commit'] if branch_row['head_commit'] != 'GENESIS' else None
        else:
            # Create branch if doesn't exist
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
        ''', (commit_hash, DEFAULT_TENANT, tree_hash, parent_hash, 'backfill-script', message, created_at))
        
        # Update branch head
        cur.execute('''
            UPDATE branches SET head_commit = %s WHERE name = %s AND tenant_id = %s
        ''', (commit_hash, branch, DEFAULT_TENANT))
        
        # Add tag for lookup
        cur.execute('''
            INSERT INTO tags (tenant_id, blob_hash, tag, created_at)
            VALUES (%s, %s, %s, %s)
        ''', (DEFAULT_TENANT, blob_hash, f"task:{task_id}", created_at))
        
        backfilled += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"\nDone. Backfilled: {backfilled}, Skipped: {skipped}")

if __name__ == '__main__':
    backfill_tasks()
