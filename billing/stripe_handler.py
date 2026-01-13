"""
Stripe Webhook Handler
Owner: CC2
Workstream: W2P2

Handles Stripe webhook events:
- checkout.session.completed: New subscription created
- customer.subscription.updated: Plan changed or status updated
- customer.subscription.deleted: Subscription cancelled
"""

import os
import json
import stripe
from datetime import datetime
from flask import Blueprint, request, jsonify

# Stripe configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

# These will be injected by init_stripe_webhooks()
_get_db = None
_get_cursor = None


def init_stripe_webhooks(get_db_func, get_cursor_func):
    """Initialize the stripe webhooks blueprint with database functions."""
    global _get_db, _get_cursor
    _get_db = get_db_func
    _get_cursor = get_cursor_func
    return stripe_bp


stripe_bp = Blueprint('stripe', __name__, url_prefix='/v2/billing')


@stripe_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """
    Handle incoming Stripe webhooks.

    Verifies signature and routes to appropriate handler.
    """
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    if not STRIPE_WEBHOOK_SECRET:
        return jsonify({'error': 'Webhook secret not configured'}), 500

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return jsonify({'error': 'Invalid signature'}), 400

    # Route to handler based on event type
    event_type = event['type']
    event_data = event['data']['object']

    handlers = {
        'checkout.session.completed': handle_checkout_completed,
        'customer.subscription.updated': handle_subscription_updated,
        'customer.subscription.deleted': handle_subscription_deleted,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler(event_data)
        except Exception as e:
            # Log error but return 200 to prevent Stripe retries
            import sys
            print(f"[STRIPE] Error handling {event_type}: {e}", file=sys.stderr)
            return jsonify({'error': str(e)}), 500

    return jsonify({'status': 'received', 'type': event_type})


def handle_checkout_completed(session):
    """
    Handle checkout.session.completed event.

    Creates a new subscription record when a customer completes checkout.
    """
    from billing.db import create_subscription, get_tenant_by_stripe_customer
    from billing.plans import get_plan_by_stripe_price

    customer_id = session.get('customer')
    subscription_id = session.get('subscription')

    if not subscription_id:
        # One-time payment, not a subscription
        return

    # Get tenant from customer ID
    tenant = get_tenant_by_stripe_customer(_get_cursor(), customer_id)
    if not tenant:
        import sys
        print(f"[STRIPE] No tenant found for customer {customer_id}", file=sys.stderr)
        return

    # Get subscription details from Stripe
    subscription = stripe.Subscription.retrieve(subscription_id)
    price_id = subscription['items']['data'][0]['price']['id']

    # Map price to plan
    plan = get_plan_by_stripe_price(price_id)
    plan_id = plan['id'] if plan else 'pro'  # Default to pro if unknown

    # Create subscription record
    db = _get_db()
    cur = _get_cursor()

    create_subscription(
        cur=cur,
        tenant_id=tenant['id'],
        stripe_subscription_id=subscription_id,
        stripe_customer_id=customer_id,
        plan_id=plan_id,
        status='active',
        current_period_start=datetime.fromtimestamp(subscription['current_period_start']),
        current_period_end=datetime.fromtimestamp(subscription['current_period_end'])
    )

    db.commit()
    cur.close()


def handle_subscription_updated(subscription):
    """
    Handle customer.subscription.updated event.

    Updates subscription status and plan when changed.
    """
    from billing.db import update_subscription
    from billing.plans import get_plan_by_stripe_price

    subscription_id = subscription['id']
    status = subscription['status']  # active, past_due, canceled, etc.
    price_id = subscription['items']['data'][0]['price']['id']

    # Map price to plan
    plan = get_plan_by_stripe_price(price_id)
    plan_id = plan['id'] if plan else None

    db = _get_db()
    cur = _get_cursor()

    update_subscription(
        cur=cur,
        stripe_subscription_id=subscription_id,
        status=status,
        plan_id=plan_id,
        current_period_start=datetime.fromtimestamp(subscription['current_period_start']),
        current_period_end=datetime.fromtimestamp(subscription['current_period_end'])
    )

    db.commit()
    cur.close()


def handle_subscription_deleted(subscription):
    """
    Handle customer.subscription.deleted event.

    Marks subscription as canceled.
    """
    from billing.db import update_subscription

    subscription_id = subscription['id']

    db = _get_db()
    cur = _get_cursor()

    update_subscription(
        cur=cur,
        stripe_subscription_id=subscription_id,
        status='canceled',
        canceled_at=datetime.utcnow()
    )

    db.commit()
    cur.close()
