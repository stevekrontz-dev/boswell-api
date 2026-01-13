"""
Boswell SaaS Usage Enforcement
Owner: CC2
Workstream: W2P4

Decorators and helpers for enforcing plan limits:
- Returns 402 Payment Required when limits exceeded
- Includes upgrade URL for easy conversion
"""

from functools import wraps
from flask import request, jsonify, g
import os

# Base URL for upgrade links
BASE_URL = os.environ.get('BASE_URL', 'https://delightful-imagination-production-f6a1.up.railway.app')


def limit_exceeded_response(limit_type: str, current: int, limit: int, plan_id: str):
    """
    Generate a 402 Payment Required response with upgrade info.

    Args:
        limit_type: Type of limit exceeded ('commit', 'branch', 'storage')
        current: Current usage
        limit: The limit that was hit
        plan_id: Current plan ID

    Returns:
        Flask response tuple (jsonify, status_code)
    """
    from .plans import get_upgrade_recommendation

    upgrade_plan = get_upgrade_recommendation(plan_id, limit_type)
    checkout_url = f"{BASE_URL}/v2/billing/checkout" if upgrade_plan else None

    messages = {
        'commit': f'Monthly commit limit reached ({current}/{limit}). Upgrade to continue.',
        'branch': f'Branch limit reached ({current}/{limit}). Upgrade for unlimited branches.',
        'storage': f'Storage limit reached ({current:.1f}/{limit} MB). Upgrade for more storage.'
    }

    return jsonify({
        'error': 'Limit exceeded',
        'message': messages.get(limit_type, f'{limit_type} limit reached'),
        'limit_type': limit_type,
        'current': current,
        'limit': limit,
        'plan': plan_id,
        'upgrade_to': upgrade_plan,
        'upgrade_url': checkout_url
    }), 402


def check_commit_limit(get_db_func, get_cursor_func, default_tenant: str):
    """
    Decorator factory to check commit limits before allowing operation.

    Args:
        get_db_func: Function to get database connection
        get_cursor_func: Function to get database cursor
        default_tenant: Default tenant ID

    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from .usage import get_tenant_usage, get_tenant_plan
            from .plans import get_plan_limits

            tenant_id = request.headers.get('X-Tenant-ID', default_tenant)
            cur = get_cursor_func()

            try:
                plan_id = get_tenant_plan(cur, tenant_id)
                limits = get_plan_limits(plan_id)
                usage = get_tenant_usage(cur, tenant_id)

                commit_limit = limits.get('commit_limit')
                current_commits = usage.get('commits', 0)

                # Check if limit is set and exceeded
                if commit_limit is not None and current_commits >= commit_limit:
                    cur.close()
                    # Log the limit hit for analytics
                    print(f"[BILLING] Commit limit hit: tenant={tenant_id}, plan={plan_id}, usage={current_commits}/{commit_limit}", flush=True)
                    return limit_exceeded_response('commit', current_commits, commit_limit, plan_id)

                cur.close()
                return f(*args, **kwargs)

            except Exception as e:
                cur.close()
                print(f"[BILLING] Error checking commit limit: {e}", flush=True)
                # On error, allow the operation (fail open for now)
                return f(*args, **kwargs)

        return decorated
    return decorator


def check_branch_limit(get_db_func, get_cursor_func, default_tenant: str):
    """
    Decorator factory to check branch limits before allowing creation.

    Args:
        get_db_func: Function to get database connection
        get_cursor_func: Function to get database cursor
        default_tenant: Default tenant ID

    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from .usage import get_tenant_usage, get_tenant_plan
            from .plans import get_plan_limits

            tenant_id = request.headers.get('X-Tenant-ID', default_tenant)
            cur = get_cursor_func()

            try:
                plan_id = get_tenant_plan(cur, tenant_id)
                limits = get_plan_limits(plan_id)
                usage = get_tenant_usage(cur, tenant_id)

                branch_limit = limits.get('branch_limit')
                current_branches = usage.get('branches', 0)

                # Check if limit is set and exceeded
                if branch_limit is not None and current_branches >= branch_limit:
                    cur.close()
                    # Log the limit hit for analytics
                    print(f"[BILLING] Branch limit hit: tenant={tenant_id}, plan={plan_id}, usage={current_branches}/{branch_limit}", flush=True)
                    return limit_exceeded_response('branch', current_branches, branch_limit, plan_id)

                cur.close()
                return f(*args, **kwargs)

            except Exception as e:
                cur.close()
                print(f"[BILLING] Error checking branch limit: {e}", flush=True)
                # On error, allow the operation (fail open for now)
                return f(*args, **kwargs)

        return decorated
    return decorator


def check_storage_limit(get_db_func, get_cursor_func, default_tenant: str, content_size_bytes: int = 0):
    """
    Decorator factory to check storage limits before allowing blob creation.

    Note: This is more complex as we need to check if adding new content
    would exceed the limit. For now, we check current usage only.

    Args:
        get_db_func: Function to get database connection
        get_cursor_func: Function to get database cursor
        default_tenant: Default tenant ID
        content_size_bytes: Size of content being added (for pre-check)

    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from .usage import get_tenant_usage, get_tenant_plan
            from .plans import get_plan_limits

            tenant_id = request.headers.get('X-Tenant-ID', default_tenant)
            cur = get_cursor_func()

            try:
                plan_id = get_tenant_plan(cur, tenant_id)
                limits = get_plan_limits(plan_id)
                usage = get_tenant_usage(cur, tenant_id)

                storage_limit = limits.get('storage_limit_mb')
                current_storage = usage.get('storage_mb', 0)

                # Check if limit is set and exceeded
                if storage_limit is not None and current_storage >= storage_limit:
                    cur.close()
                    print(f"[BILLING] Storage limit hit: tenant={tenant_id}, plan={plan_id}, usage={current_storage}/{storage_limit}MB", flush=True)
                    return limit_exceeded_response('storage', current_storage, storage_limit, plan_id)

                cur.close()
                return f(*args, **kwargs)

            except Exception as e:
                cur.close()
                print(f"[BILLING] Error checking storage limit: {e}", flush=True)
                return f(*args, **kwargs)

        return decorated
    return decorator


# Convenience function for inline limit checking (non-decorator usage)
def enforce_commit_limit(cursor, tenant_id: str):
    """
    Check commit limit and return error response if exceeded.

    Args:
        cursor: Database cursor
        tenant_id: The tenant identifier

    Returns:
        None if allowed, or (response, status_code) tuple if blocked
    """
    from .usage import get_tenant_usage, get_tenant_plan
    from .plans import get_plan_limits

    plan_id = get_tenant_plan(cursor, tenant_id)
    limits = get_plan_limits(plan_id)
    usage = get_tenant_usage(cursor, tenant_id)

    commit_limit = limits.get('commit_limit')
    current_commits = usage.get('commits', 0)

    if commit_limit is not None and current_commits >= commit_limit:
        print(f"[BILLING] Commit limit hit: tenant={tenant_id}, plan={plan_id}, usage={current_commits}/{commit_limit}", flush=True)
        return limit_exceeded_response('commit', current_commits, commit_limit, plan_id)

    return None


def enforce_branch_limit(cursor, tenant_id: str):
    """
    Check branch limit and return error response if exceeded.

    Args:
        cursor: Database cursor
        tenant_id: The tenant identifier

    Returns:
        None if allowed, or (response, status_code) tuple if blocked
    """
    from .usage import get_tenant_usage, get_tenant_plan
    from .plans import get_plan_limits

    plan_id = get_tenant_plan(cursor, tenant_id)
    limits = get_plan_limits(plan_id)
    usage = get_tenant_usage(cursor, tenant_id)

    branch_limit = limits.get('branch_limit')
    current_branches = usage.get('branches', 0)

    if branch_limit is not None and current_branches >= branch_limit:
        print(f"[BILLING] Branch limit hit: tenant={tenant_id}, plan={plan_id}, usage={current_branches}/{branch_limit}", flush=True)
        return limit_exceeded_response('branch', current_branches, branch_limit, plan_id)

    return None
