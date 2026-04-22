-- 028_plan_closeout_lookup.sql
-- Indexes supporting boswell_update_plan — plan lifecycle status via
-- plan_closeout memories, read from the commit log (not a sidecar table).
--
-- Design ratified via CC/CW /argue 2026-04-21: rather than mutate the
-- immutable plan blob or maintain a parallel plan_state table, the plan's
-- effective status is the status field on the newest plan_closeout memory
-- for that blob_hash (within the same tenant). Landscape and startup queries
-- use a correlated subquery with COALESCE fallback to the plan's embedded
-- status, then 'active' as the final literal tail (no silent nulls).
--
-- blobs.content is TEXT and not guaranteed to be valid JSON for
-- content_type='memory' — some memories are plain strings (raw transcript
-- text starting with '[Session...'), some look like JSON but are malformed
-- (bad trailing characters). A bare content::jsonb cast fails on those
-- rows, which happens whenever a query evaluates the cast predicate across
-- the blob table.
--
-- Fix: safe_jsonb_field(text, text) — IMMUTABLE helper that catches
-- invalid_text_representation and returns NULL. Every JSONB field access in
-- plan_closeout-land goes through this function. Planner can still use the
-- function in partial-index predicates because it's declared IMMUTABLE.
--
-- Two indexes, both partial on plan_closeout memories only:
--   1. Lookup index — supports the landscape/startup correlated subquery.
--      Composite (tenant_id, plan_blob, created_at DESC) matches the query's
--      WHERE + ORDER BY without a separate sort step.
--   2. Unique constraint — idempotency guarantee for boswell_update_plan.
--      Second commit of the same (tenant_id, plan_blob, type, status) tuple
--      raises unique_violation, which the view catches and treats as
--      idempotent-success. Documented edge case: second call with a different
--      'reason' value is rejected and the second reason is lost. Status is
--      the operational field; reason is decoration.
--
-- Pre-flight: a DO block audits existing plan_closeout memories for
-- duplicates BEFORE creating the unique constraint. If any tenant has dupes
-- from earlier shadow-closeout experimentation, the migration aborts with a
-- readable error so the operator can reconcile (silt older, keep newest)
-- before retrying. No silent failures.
--
-- Idempotent via CREATE OR REPLACE and IF NOT EXISTS.

-- 0. Safe JSONB field access — returns NULL on parse failure instead of
--    aborting the statement.
CREATE OR REPLACE FUNCTION safe_jsonb_field(src text, field text)
RETURNS text AS $$
BEGIN
    RETURN (src::jsonb)->>field;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION safe_jsonb_field(text, text) IS
    'Error-swallowing wrapper around (text::jsonb)->>''field''. Returns NULL for content that is not valid JSON. IMMUTABLE so it works inside partial index predicates.';

-- 1. Lookup index for landscape/startup subquery.
CREATE INDEX IF NOT EXISTS idx_plan_closeout_lookup
    ON blobs (tenant_id, safe_jsonb_field(content, 'plan_blob'), created_at DESC)
    WHERE content_type = 'memory'
      AND safe_jsonb_field(content, 'type') = 'plan_closeout';

-- 2. Pre-flight duplicate audit — fail loud if any tenant has dupes.
DO $$
DECLARE
    dupe_count INT;
    dupe_sample TEXT;
BEGIN
    SELECT COUNT(*) INTO dupe_count
    FROM (
        SELECT tenant_id,
               safe_jsonb_field(content, 'plan_blob') AS plan_blob,
               safe_jsonb_field(content, 'type')      AS t,
               safe_jsonb_field(content, 'status')    AS s,
               COUNT(*) AS n
        FROM blobs
        WHERE content_type = 'memory'
          AND safe_jsonb_field(content, 'type') = 'plan_closeout'
        GROUP BY 1, 2, 3, 4
        HAVING COUNT(*) > 1
    ) dupes;

    IF dupe_count > 0 THEN
        SELECT string_agg(format('%s/%s/%s/%s x%s', tenant_id, plan_blob, t, s, n), '; ')
          INTO dupe_sample
          FROM (
            SELECT tenant_id,
                   safe_jsonb_field(content, 'plan_blob') AS plan_blob,
                   safe_jsonb_field(content, 'type')      AS t,
                   safe_jsonb_field(content, 'status')    AS s,
                   COUNT(*) AS n
            FROM blobs
            WHERE content_type = 'memory'
              AND safe_jsonb_field(content, 'type') = 'plan_closeout'
            GROUP BY 1, 2, 3, 4
            HAVING COUNT(*) > 1
            LIMIT 5
          ) s;
        RAISE EXCEPTION
          'Migration 028 aborted: % duplicate plan_closeout tuples across (tenant_id, plan_blob, type, status). Reconcile before applying the unique constraint (silt older, keep newest). Sample: %',
          dupe_count, dupe_sample;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 3. Unique constraint — idempotency at the storage layer.
CREATE UNIQUE INDEX IF NOT EXISTS uq_plan_closeout_idempotent
    ON blobs (
        tenant_id,
        safe_jsonb_field(content, 'plan_blob'),
        safe_jsonb_field(content, 'type'),
        safe_jsonb_field(content, 'status')
    )
    WHERE content_type = 'memory'
      AND safe_jsonb_field(content, 'type') = 'plan_closeout';

COMMENT ON INDEX idx_plan_closeout_lookup IS
    'Partial B-tree supporting the plan-status correlated subquery in /v2/startup and /v2/tasks/landscape. Per-tenant + plan_blob lookup with created_at DESC ordering. Uses safe_jsonb_field() to tolerate non-JSON memory content.';

COMMENT ON INDEX uq_plan_closeout_idempotent IS
    'Partial unique constraint enforcing that boswell_update_plan is idempotent per (tenant, plan, type, status). Unique_violation on retry is caught and returned as idempotent-success.';
