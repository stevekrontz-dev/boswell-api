"""
Boswell SaaS Plan Definitions
Owner: CC2
Workstream: W2P1

Plan tiers:
- Free: Demo the magic, very limited
- Starter $29/mo: Hobby/prototype, one project
- Pro $149/mo: Production continuity infrastructure (default recommendation)
- Team $999/mo: Org-ready, SSO/RBAC/audit
"""

import os
from typing import Optional, Dict, Any

# Stripe Price IDs from environment (set in Railway)
STRIPE_PRICE_STARTER = os.environ.get('STRIPE_PRICE_STARTER', 'price_test_starter')
STRIPE_PRICE_PRO = os.environ.get('STRIPE_PRICE_PRO', 'price_test_pro')
STRIPE_PRICE_TEAM = os.environ.get('STRIPE_PRICE_TEAM', 'price_test_team')


PLANS: Dict[str, Dict[str, Any]] = {
    'free': {
        'id': 'free',
        'name': 'Free',
        'description': 'See the magic',
        'price': 0,
        'interval': None,
        'commit_limit': 50,
        'branch_limit': 1,
        'storage_limit_mb': 50,
        'retention_days': 30,
        'identity_limit': 1,
        'features': [
            '50 memory operations / month',
            '1 project',
            'Basic search',
            'No overages — it just stops'
        ],
        'stripe_price_id': None,
        'stripe_product_id': None
    },
    'starter': {
        'id': 'starter',
        'name': 'Starter',
        'description': 'Ship something real',
        'price': 2900,  # $29/month in cents
        'interval': 'month',
        'commit_limit': 1000,
        'branch_limit': 5,
        'storage_limit_mb': 1000,
        'retention_days': None,
        'identity_limit': 10,
        'features': [
            '1,000 memory operations / month',
            '1 deployed project',
            '10 identities',
            'Smart search',
            'Claude.ai, Claude Code & API'
        ],
        'stripe_price_id': STRIPE_PRICE_STARTER,
        'stripe_product_id': os.environ.get('STRIPE_PRODUCT_STARTER')
    },
    'pro': {
        'id': 'pro',
        'name': 'Pro',
        'description': 'Continuity infrastructure',
        'price': 14900,  # $149/month in cents
        'interval': 'month',
        'commit_limit': None,
        'branch_limit': None,
        'storage_limit_mb': None,
        'retention_days': None,
        'identity_limit': None,
        'features': [
            'Unlimited memory operations',
            'Unlimited projects & identities',
            'Webhooks & automation',
            'Analytics dashboard',
            'Advanced retention policies',
            'Priority support'
        ],
        'stripe_price_id': STRIPE_PRICE_PRO,
        'stripe_product_id': os.environ.get('STRIPE_PRODUCT_PRO')
    },
    'team': {
        'id': 'team',
        'name': 'Team',
        'description': 'Org-ready',
        'price': 99900,  # $999/month in cents
        'interval': 'month',
        'commit_limit': None,
        'branch_limit': None,
        'storage_limit_mb': None,
        'retention_days': None,
        'identity_limit': None,
        'features': [
            'Everything in Pro',
            'Shared workspace',
            'SSO, RBAC & audit logs',
            'Higher rate limits',
            'Onboarding support',
            'Compliance-ready deployment'
        ],
        'stripe_price_id': STRIPE_PRICE_TEAM,
        'stripe_product_id': os.environ.get('STRIPE_PRODUCT_TEAM')
    }
}


def get_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a plan by ID.

    Args:
        plan_id: The plan identifier ('free', 'pro', 'team')

    Returns:
        Plan dictionary or None if not found
    """
    return PLANS.get(plan_id)


def get_plan_limits(plan_id: str) -> Dict[str, Any]:
    """
    Get just the limits for a plan.

    Args:
        plan_id: The plan identifier

    Returns:
        Dictionary of limits, or free tier limits if plan not found
    """
    plan = PLANS.get(plan_id, PLANS['free'])
    return {
        'commit_limit': plan.get('commit_limit'),
        'branch_limit': plan.get('branch_limit'),
        'storage_limit_mb': plan.get('storage_limit_mb'),
        'retention_days': plan.get('retention_days')
    }


def get_plan_by_stripe_price(stripe_price_id: str) -> Optional[Dict[str, Any]]:
    """
    Look up a plan by its Stripe price ID.

    Args:
        stripe_price_id: The Stripe price ID

    Returns:
        Plan dictionary or None if not found
    """
    for plan in PLANS.values():
        if plan.get('stripe_price_id') == stripe_price_id:
            return plan
    return None


def is_limit_exceeded(current: int, limit: Optional[int]) -> bool:
    """
    Check if a limit has been exceeded.

    Args:
        current: Current usage count
        limit: The limit (None means unlimited)

    Returns:
        True if exceeded, False otherwise
    """
    if limit is None:
        return False  # unlimited
    return current >= limit


def get_upgrade_recommendation(plan_id: str, exceeded_limit: str) -> Optional[str]:
    """
    Get the recommended upgrade plan when a limit is exceeded.

    Args:
        plan_id: Current plan ID
        exceeded_limit: Which limit was exceeded ('commit', 'branch', 'storage')

    Returns:
        Recommended plan ID or None if already on highest tier
    """
    if plan_id == 'free':
        return 'pro'
    elif plan_id == 'pro':
        return 'team'
    return None  # already on team


# Plan comparison matrix for marketing/UI
PLAN_COMPARISON = {
    'headers': ['Feature', 'Free', 'Pro', 'Team'],
    'rows': [
        ['Monthly commits', '1,000', '50,000', 'Unlimited'],
        ['Branches', '3', 'Unlimited', 'Unlimited'],
        ['Storage', '100 MB', '5 GB', 'Unlimited'],
        ['Memory retention', '30 days', 'Unlimited', 'Unlimited'],
        ['API access', 'Limited', 'Full', 'Full'],
        ['Support', 'Community', 'Priority', 'Dedicated'],
        ['Team features', '-', '-', 'Included'],
        ['SSO', '-', '-', 'Included'],
        ['Price', '$0', '$19/mo', '$49/seat/mo']
    ]
}
