"""
Boswell SaaS Stripe Webhook Handler
Owner: CC2
Workstream: W2P2

Handles Stripe webhook events for subscription lifecycle:
- checkout.session.completed: New subscription created
- customer.subscription.updated: Plan changed or renewed
- customer.subscription.deleted: Subscription cancelled
"""

import os
import json
import stripe
from flask import Blueprint, request, jsonify
from datetime import datetime

# Initialize Stripe with secret key
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

billing_bp = Blueprint('billing', __name__, url_prefix='/v2/billing')


def get_db_functions():
    """Import db functions lazily to avoid circular imports."""
    from app import get_db, get_cursor, DEFAULT_TENANT
    return get_db, get_cursor, DEFAULT_TENANT


@billing_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """
    Handle Stripe webhook events.

    Stripe sends events to this endpoint when subscription changes occur.
    We verify the signature and process accordingly.
    """
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    if not WEBHOOK_SECRET:
        print("[STRIPE] WARNING: STRIPE_WEBHOOK_SECRET not configured", flush=True)
        return jsonify({'error': 'Webhook secret not configured'}), 500

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except ValueError as e:
        print(f"[STRIPE] Invalid payload: {e}", flush=True)
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        print(f"[STRIPE] Invalid signature: {e}", flush=True)
        return jsonify({'error': 'Invalid signature'}), 400

    event_type = event['type']
    event_data = event['data']['object']

    print(f"[STRIPE] Received event: {event_type}", flush=True)

    try:
        if event_type == 'checkout.session.completed':
            handle_checkout_completed(event_data)
        elif event_type == 'customer.subscription.updated':
            handle_subscription_updated(event_data)
        elif event_type == 'customer.subscription.deleted':
            handle_subscription_deleted(event_data)
        else:
            print(f"[STRIPE] Unhandled event type: {event_type}", flush=True)

        return jsonify({'status': 'success'}), 200

    except Exception as e:
        print(f"[STRIPE] Error processing {event_type}: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


def handle_checkout_completed(session):
    """
    Handle successful checkout session.
    Creates or updates subscription record for the tenant.
    """
    get_db, get_cursor, DEFAULT_TENANT = get_db_functions()

    customer_id = session.get('customer')
    subscription_id = session.get('subscription')
    tenant_id = session.get('client_reference_id') or DEFAULT_TENANT

    if not subscription_id:
        print(f"[STRIPE] checkout.session.completed without subscription_id", flush=True)
        return

    # Fetch full subscription details from Stripe
    subscription = stripe.Subscription.retrieve(subscription_id)

    # Get the plan from price ID
    price_id = subscription['items']['data'][0]['price']['id']
    plan_id = get_plan_from_price(price_id)

    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'

    try:
        # Upsert subscription record
        cur.execute('''
            INSERT INTO subscriptions (
                tenant_id, stripe_customer_id, stripe_subscription_id,
                plan_id, status, current_period_start, current_period_end,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE SET
                stripe_customer_id = EXCLUDED.stripe_customer_id,
                stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                plan_id = EXCLUDED.plan_id,
                status = EXCLUDED.status,
                current_period_start = EXCLUDED.current_period_start,
                current_period_end = EXCLUDED.current_period_end,
                updated_at = EXCLUDED.updated_at
        ''', (
            tenant_id,
            customer_id,
            subscription_id,
            plan_id,
            subscription['status'],
            datetime.fromtimestamp(subscription['current_period_start']).isoformat(),
            datetime.fromtimestamp(subscription['current_period_end']).isoformat(),
            now,
            now
        ))

        db.commit()
        print(f"[STRIPE] Created/updated subscription for tenant {tenant_id}: {plan_id}", flush=True)

    except Exception as e:
        db.rollback()
        print(f"[STRIPE] Error saving subscription: {e}", flush=True)
        raise
    finally:
        cur.close()


def handle_subscription_updated(subscription):
    """
    Handle subscription updates (plan changes, renewals).
    """
    get_db, get_cursor, DEFAULT_TENANT = get_db_functions()

    subscription_id = subscription['id']
    customer_id = subscription['customer']
    status = subscription['status']

    # Get the plan from price ID
    price_id = subscription['items']['data'][0]['price']['id']
    plan_id = get_plan_from_price(price_id)

    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'

    try:
        cur.execute('''
            UPDATE subscriptions SET
                plan_id = %s,
                status = %s,
                current_period_start = %s,
                current_period_end = %s,
                updated_at = %s
            WHERE stripe_subscription_id = %s
            RETURNING tenant_id
        ''', (
            plan_id,
            status,
            datetime.fromtimestamp(subscription['current_period_start']).isoformat(),
            datetime.fromtimestamp(subscription['current_period_end']).isoformat(),
            now,
            subscription_id
        ))

        row = cur.fetchone()
        db.commit()

        if row:
            print(f"[STRIPE] Updated subscription {subscription_id}: {plan_id} ({status})", flush=True)
        else:
            print(f"[STRIPE] Subscription {subscription_id} not found in database", flush=True)

    except Exception as e:
        db.rollback()
        print(f"[STRIPE] Error updating subscription: {e}", flush=True)
        raise
    finally:
        cur.close()


def handle_subscription_deleted(subscription):
    """
    Handle subscription cancellation.
    Downgrades tenant to free plan.
    """
    get_db, get_cursor, DEFAULT_TENANT = get_db_functions()

    subscription_id = subscription['id']

    db = get_db()
    cur = get_cursor()
    now = datetime.utcnow().isoformat() + 'Z'

    try:
        cur.execute('''
            UPDATE subscriptions SET
                plan_id = 'free',
                status = 'canceled',
                canceled_at = %s,
                updated_at = %s
            WHERE stripe_subscription_id = %s
            RETURNING tenant_id
        ''', (now, now, subscription_id))

        row = cur.fetchone()
        db.commit()

        if row:
            print(f"[STRIPE] Subscription {subscription_id} canceled, downgraded to free", flush=True)
        else:
            print(f"[STRIPE] Subscription {subscription_id} not found for cancellation", flush=True)

    except Exception as e:
        db.rollback()
        print(f"[STRIPE] Error canceling subscription: {e}", flush=True)
        raise
    finally:
        cur.close()


def get_plan_from_price(price_id: str) -> str:
    """
    Map Stripe price ID to internal plan ID.
    """
    from billing.plans import PLANS

    for plan_id, plan in PLANS.items():
        if plan.get('stripe_price_id') == price_id:
            return plan_id

    # Default to pro if unknown price
    return 'pro'


# Health check endpoint for billing module
@billing_bp.route('/health', methods=['GET'])
def billing_health():
    """Health check for billing module."""
    return jsonify({
        'status': 'ok',
        'module': 'billing',
        'stripe_configured': bool(stripe.api_key),
        'webhook_secret_configured': bool(WEBHOOK_SECRET)
    })
