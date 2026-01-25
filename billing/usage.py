"""
Boswell SaaS Usage Tracking
Owner: CC2
Workstream: W2P4

Tracks usage metrics per tenant for limit enforcement:
- Commits per month
- Branch count
- Storage in MB
"""

from datetime import datetime
from typing import Dict, Any, Optional, Tuple


def get_tenant_usage(cursor, tenant_id: str) -> Dict[str, Any]:
    """
    Get current period usage for a tenant.

    Args:
        cursor: Database cursor
        tenant_id: The tenant identifier

    Returns:
        Dictionary with commits, branches, storage_mb counts
    """
    commits = 0
    branches = 0
    storage_mb = 0.0

    try:
        # Use savepoint to prevent transaction corruption on error
        cursor.execute("SAVEPOINT usage_commits")
        # Count commits this month
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM commits
            WHERE tenant_id = %s
            AND created_at >= date_trunc('month', CURRENT_TIMESTAMP)
        """, (tenant_id,))
        row = cursor.fetchone()
        commits = row['cnt'] if row else 0
        cursor.execute("RELEASE SAVEPOINT usage_commits")
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT usage_commits")

    try:
        cursor.execute("SAVEPOINT usage_branches")
        # Count branches
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM branches WHERE tenant_id = %s
        """, (tenant_id,))
        row = cursor.fetchone()
        branches = row['cnt'] if row else 0
        cursor.execute("RELEASE SAVEPOINT usage_branches")
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT usage_branches")

    try:
        cursor.execute("SAVEPOINT usage_storage")
        # Calculate storage (approximate from blob sizes)
        cursor.execute("""
            SELECT COALESCE(SUM(byte_size), 0) / 1048576.0 as storage
            FROM blobs WHERE tenant_id = %s
        """, (tenant_id,))
        row = cursor.fetchone()
        storage_mb = round(row['storage'] if row else 0, 2)
        cursor.execute("RELEASE SAVEPOINT usage_storage")
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT usage_storage")

    return {
        'commits': commits,
        'branches': branches,
        'storage_mb': storage_mb
    }


def get_tenant_plan(cursor, tenant_id: str) -> str:
    """
    Get the current plan for a tenant.

    Args:
        cursor: Database cursor
        tenant_id: The tenant identifier

    Returns:
        Plan ID string ('free', 'pro', 'team')
    """
    # First check users table (source of truth for plan from Stripe webhooks)
    try:
        cursor.execute("SAVEPOINT tenant_plan_users")
        cursor.execute("""
            SELECT subscription_tier FROM users
            WHERE tenant_id = %s AND status = 'active'
            LIMIT 1
        """, (tenant_id,))
        row = cursor.fetchone()
        cursor.execute("RELEASE SAVEPOINT tenant_plan_users")
        if row and row.get('subscription_tier'):
            return row['subscription_tier']
    except Exception:
        try:
            cursor.execute("ROLLBACK TO SAVEPOINT tenant_plan_users")
        except Exception:
            pass

    # Fall back to subscriptions table (legacy)
    try:
        cursor.execute("SAVEPOINT tenant_plan_subs")
        cursor.execute("""
            SELECT plan_id FROM subscriptions
            WHERE tenant_id = %s AND status = 'active'
        """, (tenant_id,))
        row = cursor.fetchone()
        cursor.execute("RELEASE SAVEPOINT tenant_plan_subs")
        if row and row.get('plan_id'):
            return row['plan_id']
    except Exception:
        try:
            cursor.execute("ROLLBACK TO SAVEPOINT tenant_plan_subs")
        except Exception:
            pass  # Savepoint may not exist

    return 'free'  # Default to free tier


def check_limit(current: int, limit: Optional[int]) -> Tuple[bool, Optional[int]]:
    """
    Check if a limit has been exceeded.

    Args:
        current: Current usage count
        limit: The limit (None means unlimited)

    Returns:
        Tuple of (is_allowed, remaining)
        - is_allowed: True if under limit
        - remaining: How many left (None if unlimited)
    """
    if limit is None:
        return True, None  # unlimited

    remaining = limit - current
    is_allowed = current < limit
    return is_allowed, max(0, remaining)


def get_usage_summary(cursor, tenant_id: str) -> Dict[str, Any]:
    """
    Get full usage summary with plan limits and percentages.

    Args:
        cursor: Database cursor
        tenant_id: The tenant identifier

    Returns:
        Dictionary with usage, limits, and percentages
    """
    from .plans import PLANS, get_plan_limits

    # Get current plan
    plan_id = get_tenant_plan(cursor, tenant_id)
    plan = PLANS.get(plan_id, PLANS['free'])
    limits = get_plan_limits(plan_id)

    # Get current usage
    usage = get_tenant_usage(cursor, tenant_id)

    # Calculate percentages
    def calc_pct(current, limit):
        if limit is None:
            return 0  # unlimited
        return min(100, round((current / max(limit, 1)) * 100, 1))

    return {
        'plan': {
            'id': plan['id'],
            'name': plan['name']
        },
        'usage': usage,
        'limits': limits,
        'percentages': {
            'commits': calc_pct(usage['commits'], limits['commit_limit']),
            'branches': calc_pct(usage['branches'], limits['branch_limit']),
            'storage': calc_pct(usage['storage_mb'], limits['storage_limit_mb'])
        },
        'at_limit': {
            'commits': limits['commit_limit'] is not None and usage['commits'] >= limits['commit_limit'],
            'branches': limits['branch_limit'] is not None and usage['branches'] >= limits['branch_limit'],
            'storage': limits['storage_limit_mb'] is not None and usage['storage_mb'] >= limits['storage_limit_mb']
        }
    }
