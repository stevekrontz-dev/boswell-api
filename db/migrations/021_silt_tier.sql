-- Migration 021: SILT Tier — geological memory depth
-- Based on Steve's canonical whiteboard drawing (IMG_9925.jpeg, March 29 2026)
-- Two types of silt, two provenances. Nothing is ever deleted.
--
-- Bookmark SILT: bookmarks that failed consolidation. Never became commits.
-- Commit SILT: committed memories whose trails all archived. Faded naturally.

-- Add 'silt' status to candidate_memories for bookmark silt
-- (consolidation NO path → bookmark silt)
ALTER TYPE candidate_status ADD VALUE IF NOT EXISTS 'silt' AFTER 'expired';

-- Add silt fields to commits for per-branch commit silt
-- NULL = active (default), 'silted' = decayed to geological depth
ALTER TABLE commits ADD COLUMN IF NOT EXISTS silt_status VARCHAR(20);
ALTER TABLE commits ADD COLUMN IF NOT EXISTS silted_at TIMESTAMPTZ;
ALTER TABLE commits ADD COLUMN IF NOT EXISTS silt_reason TEXT;

-- Index for silt queries (partial — only non-null rows)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_commits_silt
ON commits(silt_status) WHERE silt_status IS NOT NULL;
