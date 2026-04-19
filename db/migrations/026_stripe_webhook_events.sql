-- 026_stripe_webhook_events.sql
-- Dedup table for Stripe webhook events.
--
-- C1 fix: previously stripe_webhook() dispatched by event.type without
-- checking whether the event.id had already been processed. Stripe retries
-- on any non-2xx response (up to 3 days, exponential backoff). If a handler
-- partially succeeded — e.g. provisioned a tenant, then 500'd on the
-- subscription UPSERT — Stripe's retry would re-run the handler and
-- re-provision, because the tenant-side state is already there but the
-- event was never recorded as "processed."
--
-- Shape: one row per stripe event.id. INSERT with ON CONFLICT DO NOTHING;
-- if rowcount = 0 the event has been seen before — the handler returns 200
-- immediately without dispatch.
--
-- event_type is stored for audit only. received_at is used to age out old
-- rows (separate cleanup job if/when this table grows large).
--
-- Idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    event_id      TEXT PRIMARY KEY,
    event_type    TEXT NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at  TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_received
    ON stripe_webhook_events (received_at);

COMMENT ON TABLE stripe_webhook_events IS
    'Stripe webhook idempotency log — one row per Stripe event.id. First insert wins; retries are no-ops.';
