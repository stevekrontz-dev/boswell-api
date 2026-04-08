-- Migration 022: Commit Agent source tag
-- Plan B (Commit Agent v1.0) auto-creates supersession links at write time.
-- This column makes those auto-links filterable, reversible, and distinguishable
-- from human-curated supersession links. Required for guard rail #1 of Plan B.
--
-- Plan source: bf298d68 / 2f947c3a / 552c7205 (Boswell)
-- Plan file: C:\Users\Steve\.claude\plans\keen-watching-kettle.md
--
-- Backfill: every existing row gets 'manual' (the default), so no data churn.
-- New rows from /v2/commit_checked will set source='commit_agent'.

ALTER TABLE cross_references
    ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'manual';

-- Partial index — most rows will be 'manual', so index 'commit_agent' rows
-- specifically for fast filterable cleanup queries. Use CONCURRENTLY in the
-- manual runner; the auto-ensure function applies the column only.
-- This statement is idempotent via IF NOT EXISTS but won't run inside a
-- transaction (CONCURRENTLY restriction). The standalone runner handles it.
