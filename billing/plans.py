"""
Boswell SaaS Plan Definitions
Owner: CC2
Workstream: W2P1

Plan tiers:
- Free: Limited commits and branches, no payment required
- Pro: Higher limits, single user, monthly subscription
- Team: Unlimited, per-seat pricing, for organizations
"""

import os
from typing import Optional, Dict, Any

# Stripe Price IDs from environment (set in Railway)
# These are created in Stripe Dashboard (test mode first, then live)
STRIPE_PRICE_PRO = os.environ.get('STRIPE_PRICE_PRO', 'price_test_pro')
STRIPE_PRICE_TEAM = os.environ.get('STRIPE_PRICE_TEAM', 'price_test_team')


PLANS: Dict[str, Dict[str, Any]] = {
    'free': {
        'id': 'free',
        'name': 'Free',
        'description': 'Get started with Boswell memory',
        'price': 0,  # cents
        'interval': None,  # no billing
        'commit_limit': 1000,  # per month
        'branch_limit': 3,
        'storage_limit_mb': 100,
        'retention_days': 30,  # memories older than 30 days may be archived
        'features': [
            '1,000 commits per month',
            '3 cognitive branches',
            '100 MB storage',
            '30-day memory retention',
            'Community support'
        ],
        'stripe_price_id': None,  # no Stripe product for free tier
        'stripe_product_id': None
    },
    'pro': {
        'id': 'pro',
        'name': 'Pro',
        'description': 'For power users who need more memory',
        'price': 1900,  # $19/month in cents
        'interval': 'month',
        'commit_limit': 50000,  # per month
        'branch_limit': None,  # unlimited
        'storage_limit_mb': 5000,  # 5 GB
        'retention_days': None,  # unlimited retention
        'features': [
            '50,000 commits per month',
            'Unlimited branches',
            '5 GB storage',
            'Unlimited retention',
            'Priority support',
            'API access'
        ],
        'stripe_price_id': STRIPE_PRICE_PRO,
        'stripe_product_id': os.environ.get('STRIPE_PRODUCT_PRO')
    },
    'team': {
        'id': 'team',
        'name': 'Team',
        'description': 'For teams building together',
        'price': 4900,  # $49/seat/month in cents
        'interval': 'month',
        'price_per': 'seat',  # per-seat pricing
        'commit_limit': None,  # unlimited
        'branch_limit': None,  # unlimited
        'storage_limit_mb': None,  # unlimited
        'retention_days': None,  # unlimited
        'features': [
            'Unlimited commits',
            'Unlimited branches',
            'Unlimited storage',
            'Unlimited retention',
            'Shared team memory',
            'SSO integration',
            'Dedicated support',
            'Custom integrations'
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
