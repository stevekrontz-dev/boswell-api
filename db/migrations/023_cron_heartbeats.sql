-- Migration 023: Cron heartbeats table
-- Tracks the last successful run of each cron service so admin_alerts can
-- detect silent failures (Mar 31 → Apr 4 2026 embedding backfill blackout
-- went undetected for 96 hours because the cron exited 0 silently when
-- there was no work).
--
-- Plan source: atomic-prancing-teacup.md (CC + CW + Steve, Apr 8 2026)
-- Sacred rule: c36afb57 ("NO SILENT FAILURES") — every cron logs what it did,
-- exit 0 means success not silence, swallowed exceptions banned.
--
-- This migration is also applied at runtime via ensure_cron_heartbeats_schema()
-- in app.py — first call from any cron endpoint creates the table idempotently.
-- The SQL file exists for documentation and fresh installs.

CREATE TABLE IF NOT EXISTS cron_heartbeats (
    service TEXT PRIMARY KEY,
    last_run_at TIMESTAMPTZ NOT NULL,
    last_status TEXT NOT NULL,         -- 'ok' | 'no_work' | 'error'
    last_message TEXT,
    work_done_count INT DEFAULT 0,
    expected_interval_minutes INT NOT NULL DEFAULT 5
);

-- Index for the staleness query in admin_alerts (Alert 6)
CREATE INDEX IF NOT EXISTS idx_cron_heartbeats_last_run
    ON cron_heartbeats (last_run_at);
