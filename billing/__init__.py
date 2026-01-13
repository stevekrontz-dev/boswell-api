"""
Boswell SaaS Billing Module
Owner: CC2
Workstream: W2 (Billing & Stripe)

This module handles:
- Plan definitions and pricing
- Stripe integration (webhooks, checkout sessions)
- Usage tracking and limit enforcement
"""

from billing.plans import PLANS, get_plan, get_plan_limits, get_plan_by_stripe_price
from billing.db import (
    create_subscription,
    update_subscription,
    get_subscription,
    get_tenant_plan,
    is_subscription_active
)

__all__ = [
    'PLANS', 'get_plan', 'get_plan_limits', 'get_plan_by_stripe_price',
    'create_subscription', 'update_subscription', 'get_subscription',
    'get_tenant_plan', 'is_subscription_active'
]
