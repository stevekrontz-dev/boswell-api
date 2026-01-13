"""
Billing Database Functions
Owner: CC2
Workstream: W2P2

Database operations for subscriptions and billing.
"""

from datetime import datetime
from typing import Optional, Dict, Any


def create_subscription(
    cur,
    tenant_id: str,
    stripe_subscription_id: str,
    stripe_customer_id: str,
    plan_id: str,
    status: str = 'active',
    current_period_start: datetime = None,
    current_period_end: datetime = None
) -> Dict[str, Any]:
    """
    Create a new subscription record.

    Args:
        cur: Database cursor
        tenant_id: Tenant UUID
        stripe_subscription_id: Stripe subscription ID (sub_xxx)
        stripe_customer_id: Stripe customer ID (cus_xxx)
        plan_id: Plan ID ('free', 'pro', 'team')
        status: Subscription status
        current_period_start: Period start datetime
        current_period_end: Period end datetime

    Returns:
        Created subscription dict
    """
    cur.execute(
        '''INSERT INTO subscriptions
           (tenant_id, stripe_subscription_id, stripe_customer_id, plan_id, status,
            current_period_start, current_period_end)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (tenant_id) DO UPDATE SET
               stripe_subscription_id = EXCLUDED.stripe_subscription_id,
               stripe_customer_id = EXCLUDED.stripe_customer_id,
               plan_id = EXCLUDED.plan_id,
               status = EXCLUDED.status,
               current_period_start = EXCLUDED.current_period_start,
               current_period_end = EXCLUDED.current_period_end,
               updated_at = NOW()
           RETURNING *''',
        (tenant_id, stripe_subscription_id, stripe_customer_id, plan_id, status,
         current_period_start, current_period_end)
    )
    return dict(cur.fetchone())


def update_subscription(
    cur,
    stripe_subscription_id: str,
    status: Optional[str] = None,
    plan_id: Optional[str] = None,
    current_period_start: Optional[datetime] = None,
    current_period_end: Optional[datetime] = None,
    canceled_at: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """
    Update an existing subscription.

    Args:
        cur: Database cursor
        stripe_subscription_id: Stripe subscription ID
        status: New status (if changing)
        plan_id: New plan ID (if changing)
        current_period_start: New period start
        current_period_end: New period end
        canceled_at: Cancellation timestamp

    Returns:
        Updated subscription dict or None if not found
    """
    # Build dynamic UPDATE
    updates = []
    params = []

    if status is not None:
        updates.append('status = %s')
        params.append(status)

    if plan_id is not None:
        updates.append('plan_id = %s')
        params.append(plan_id)

    if current_period_start is not None:
        updates.append('current_period_start = %s')
        params.append(current_period_start)

    if current_period_end is not None:
        updates.append('current_period_end = %s')
        params.append(current_period_end)

    if canceled_at is not None:
        updates.append('canceled_at = %s')
        params.append(canceled_at)

    if not updates:
        return None

    updates.append('updated_at = NOW()')
    params.append(stripe_subscription_id)

    sql = f'''UPDATE subscriptions
              SET {', '.join(updates)}
              WHERE stripe_subscription_id = %s
              RETURNING *'''

    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def get_subscription(cur, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Get subscription for a tenant.

    Args:
        cur: Database cursor
        tenant_id: Tenant UUID

    Returns:
        Subscription dict or None
    """
    cur.execute(
        'SELECT * FROM subscriptions WHERE tenant_id = %s',
        (tenant_id,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def get_subscription_by_stripe_id(cur, stripe_subscription_id: str) -> Optional[Dict[str, Any]]:
    """
    Get subscription by Stripe subscription ID.

    Args:
        cur: Database cursor
        stripe_subscription_id: Stripe subscription ID

    Returns:
        Subscription dict or None
    """
    cur.execute(
        'SELECT * FROM subscriptions WHERE stripe_subscription_id = %s',
        (stripe_subscription_id,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def get_tenant_by_stripe_customer(cur, stripe_customer_id: str) -> Optional[Dict[str, Any]]:
    """
    Get tenant by Stripe customer ID.

    Args:
        cur: Database cursor
        stripe_customer_id: Stripe customer ID

    Returns:
        Tenant dict or None
    """
    # First check subscriptions table
    cur.execute(
        'SELECT tenant_id FROM subscriptions WHERE stripe_customer_id = %s',
        (stripe_customer_id,)
    )
    row = cur.fetchone()
    if row:
        cur.execute('SELECT * FROM tenants WHERE id = %s', (row['tenant_id'],))
        tenant = cur.fetchone()
        return dict(tenant) if tenant else None

    # Also check tenants table directly (stripe_customer_id might be stored there)
    cur.execute(
        'SELECT * FROM tenants WHERE stripe_customer_id = %s',
        (stripe_customer_id,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def get_tenant_plan(cur, tenant_id: str) -> str:
    """
    Get the current plan for a tenant.

    Args:
        cur: Database cursor
        tenant_id: Tenant UUID

    Returns:
        Plan ID ('free', 'pro', 'team')
    """
    subscription = get_subscription(cur, tenant_id)
    if subscription and subscription.get('status') == 'active':
        return subscription.get('plan_id', 'free')
    return 'free'


def is_subscription_active(cur, tenant_id: str) -> bool:
    """
    Check if tenant has an active subscription.

    Args:
        cur: Database cursor
        tenant_id: Tenant UUID

    Returns:
        True if active subscription exists
    """
    subscription = get_subscription(cur, tenant_id)
    if not subscription:
        return False
    return subscription.get('status') in ('active', 'trialing')
