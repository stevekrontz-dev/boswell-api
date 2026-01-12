"""
Boswell Audit Service
Phase 3: Comprehensive request logging for compliance and security
"""

import time
import json
import uuid
from datetime import datetime
from functools import wraps
from flask import request, g

# Action type constants
class AuditAction:
    # Memory operations
    COMMIT_CREATE = 'COMMIT_CREATE'
    COMMIT_READ = 'COMMIT_READ'
    BRANCH_CREATE = 'BRANCH_CREATE'
    BRANCH_CHECKOUT = 'BRANCH_CHECKOUT'
    BLOB_READ = 'BLOB_READ'
    SEARCH = 'SEARCH'
    LINK_CREATE = 'LINK_CREATE'
    LINK_READ = 'LINK_READ'
    REFLECT = 'REFLECT'

    # Auth operations
    AUTH_SUCCESS = 'AUTH_SUCCESS'
    AUTH_FAILURE = 'AUTH_FAILURE'
    API_KEY_CREATE = 'API_KEY_CREATE'
    API_KEY_REVOKE = 'API_KEY_REVOKE'

    # System operations
    AUDIT_QUERY = 'AUDIT_QUERY'
    STARTUP = 'STARTUP'
    HEALTH_CHECK = 'HEALTH_CHECK'


def get_request_metadata():
    """Extract metadata from the current request."""
    return {
        'ip': request.headers.get('X-Forwarded-For', request.remote_addr),
        'user_agent': request.headers.get('User-Agent', '')[:500],  # Truncate long UAs
        'method': request.method,
        'path': request.path,
        'query_params': dict(request.args),
        'request_size_bytes': request.content_length or 0,
    }


def log_audit(cursor, tenant_id, action, resource_type, resource_id=None,
              response_status=200, duration_ms=0, user_id=None, api_key_id=None,
              extra_metadata=None):
    """
    Log an audit event to the database.

    Args:
        cursor: Database cursor
        tenant_id: UUID of the tenant
        action: Action type (use AuditAction constants)
        resource_type: Type of resource (branch, commit, blob, etc.)
        resource_id: Optional ID of the specific resource
        response_status: HTTP status code
        duration_ms: Request duration in milliseconds
        user_id: Optional user UUID (Phase 4)
        api_key_id: Optional API key UUID
        extra_metadata: Additional metadata to merge with request metadata
    """
    try:
        metadata = get_request_metadata()
        if extra_metadata:
            metadata.update(extra_metadata)

        cursor.execute("""
            INSERT INTO audit_logs
            (tenant_id, user_id, api_key_id, action, resource_type, resource_id,
             request_metadata, response_status, duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            tenant_id,
            user_id,
            api_key_id,
            action,
            resource_type,
            resource_id,
            json.dumps(metadata),
            response_status,
            duration_ms
        ))
    except Exception as e:
        # Don't let audit logging failures break the API
        import sys
        print(f"[AUDIT] Warning: Failed to log audit event: {e}", file=sys.stderr)


def audit_middleware(get_cursor_func, get_tenant_func):
    """
    Flask middleware decorator factory for automatic audit logging.

    Usage:
        @app.before_request
        def before():
            g.audit_start = time.time()

        @app.after_request
        def after(response):
            audit_request(response)
            return response
    """
    def audit_request(response):
        """Log the request after it completes."""
        # Skip health checks and static files
        if request.path in ('/health', '/favicon.ico'):
            return

        # Calculate duration
        start_time = getattr(g, 'audit_start', None)
        duration_ms = int((time.time() - start_time) * 1000) if start_time else 0

        # Determine action and resource from path
        action, resource_type, resource_id = parse_request_action(request)

        # Log the audit event
        try:
            cur = get_cursor_func()
            tenant_id = get_tenant_func()
            log_audit(
                cursor=cur,
                tenant_id=tenant_id,
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
            import sys
            print(f"[AUDIT] Middleware error: {e}", file=sys.stderr)

    return audit_request


def parse_request_action(req):
    """
    Parse the request to determine action type and resource.
    Returns: (action, resource_type, resource_id)
    """
    path = req.path
    method = req.method

    # API endpoint mappings
    if '/commit' in path:
        if method == 'POST':
            return AuditAction.COMMIT_CREATE, 'commit', None
        return AuditAction.COMMIT_READ, 'commit', path.split('/')[-1] if '/' in path else None

    if '/branch' in path:
        if method == 'POST':
            return AuditAction.BRANCH_CREATE, 'branch', None
        return AuditAction.BRANCH_CHECKOUT, 'branch', path.split('/')[-1] if '/' in path else None

    if '/search' in path:
        return AuditAction.SEARCH, 'search', req.args.get('query', '')[:100]

    if '/recall' in path or '/blob' in path:
        return AuditAction.BLOB_READ, 'blob', path.split('/')[-1] if '/' in path else None

    if '/link' in path:
        if method == 'POST':
            return AuditAction.LINK_CREATE, 'link', None
        return AuditAction.LINK_READ, 'link', None

    if '/reflect' in path:
        return AuditAction.REFLECT, 'reflection', None

    if '/log' in path:
        return AuditAction.COMMIT_READ, 'log', req.args.get('branch', 'unknown')

    if '/head' in path:
        return AuditAction.COMMIT_READ, 'head', req.args.get('branch', 'unknown')

    if '/audit' in path:
        return AuditAction.AUDIT_QUERY, 'audit', None

    if '/health' in path:
        return AuditAction.HEALTH_CHECK, 'health', None

    # Default fallback
    return f'{method}_UNKNOWN', 'unknown', path


# Query functions for audit log retrieval
def query_audit_logs(cursor, tenant_id, filters=None, limit=100, offset=0):
    """
    Query audit logs with optional filters.

    Filters:
        - action: Filter by action type
        - resource_type: Filter by resource type
        - start_time: Start of time range (ISO format)
        - end_time: End of time range (ISO format)
        - status_min: Minimum status code (e.g., 400 for errors only)
    """
    filters = filters or {}

    query = """
        SELECT id, timestamp, action, resource_type, resource_id,
               response_status, duration_ms, request_metadata
        FROM audit_logs
        WHERE tenant_id = %s
    """
    params = [tenant_id]

    if filters.get('action'):
        query += " AND action = %s"
        params.append(filters['action'])

    if filters.get('resource_type'):
        query += " AND resource_type = %s"
        params.append(filters['resource_type'])

    if filters.get('start_time'):
        query += " AND timestamp >= %s"
        params.append(filters['start_time'])

    if filters.get('end_time'):
        query += " AND timestamp <= %s"
        params.append(filters['end_time'])

    if filters.get('status_min'):
        query += " AND response_status >= %s"
        params.append(filters['status_min'])

    query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    cursor.execute(query, params)
    return cursor.fetchall()


def get_audit_stats(cursor, tenant_id, hours=24):
    """Get audit statistics for the last N hours."""
    cursor.execute("""
        SELECT
            COUNT(*) as total_requests,
            COUNT(*) FILTER (WHERE response_status >= 400) as error_count,
            AVG(duration_ms)::integer as avg_duration_ms,
            MAX(duration_ms) as max_duration_ms,
            COUNT(DISTINCT action) as unique_actions
        FROM audit_logs
        WHERE tenant_id = %s
          AND timestamp > NOW() - INTERVAL '%s hours'
    """, (tenant_id, hours))
    return cursor.fetchone()
