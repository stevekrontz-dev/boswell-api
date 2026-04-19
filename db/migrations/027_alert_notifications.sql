-- 027_alert_notifications.sql
-- Dedup table for outbound alert emails so a recurring condition doesn't
-- spam the recipient on every poll. Paired with the /v2/health/alert-check
-- endpoint.
--
-- alert_key is a stable string identifying the alert instance (e.g.
-- 'cron_silent::nightly-maintenance-cron'). Two pollers that see the same
-- alert resolve to the same row.
--
-- Sending rule: email fires when last_notified_at is NULL or older than the
-- endpoint's throttle window. resolved_at is set when the underlying
-- condition no longer appears in admin_alerts — allows a "back online"
-- email on next occurrence instead of staying dedup-suppressed forever.
--
-- Idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS alert_notifications (
    alert_key          TEXT PRIMARY KEY,
    alert_type         TEXT NOT NULL,
    severity           TEXT NOT NULL,
    message            TEXT,
    first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_notified_at   TIMESTAMPTZ NULL,
    notification_count INT NOT NULL DEFAULT 0,
    resolved_at        TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_alert_notifications_unresolved
    ON alert_notifications (resolved_at)
    WHERE resolved_at IS NULL;

COMMENT ON TABLE alert_notifications IS
    'Outbound alert dedup log — one row per stable alert_key. Email is re-sent when last_notified_at is NULL or older than the throttle window.';
