"""
Boswell SaaS Billing Module
Owner: CC2
Workstream: W2 (Billing & Stripe)

This module handles:
- Plan definitions and pricing
- Stripe integration (webhooks, checkout sessions)
- Usage tracking and limit enforcement
"""

from .plans import PLANS, get_plan, get_plan_limits

__all__ = ['PLANS', 'get_plan', 'get_plan_limits']
