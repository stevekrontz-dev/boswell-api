-- Migration 017: Hybrid Search (BM25 + pgvector via Reciprocal Rank Fusion)
-- Adds tsvector column for PostgreSQL full-text search on blobs table.
-- Safe to run multiple times (idempotent).

-- Step 1: Add tsvector column for full-text search
ALTER TABLE blobs ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Step 2: Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_blobs_search_vector ON blobs USING GIN (search_vector);

-- Step 3: Trigger to auto-populate tsvector on INSERT/UPDATE
-- The blobs.content column is TEXT containing JSON. We extract key fields
-- via casting to jsonb, plus index the raw content as fallback.
CREATE OR REPLACE FUNCTION blobs_search_vector_update() RETURNS trigger AS $$
BEGIN
  BEGIN
    NEW.search_vector := to_tsvector('english',
      COALESCE(NEW.content::jsonb->>'message', '') || ' ' ||
      COALESCE(NEW.content::jsonb->>'summary', '') || ' ' ||
      COALESCE(NEW.content::jsonb->>'title', '') || ' ' ||
      COALESCE(NEW.content, '')
    );
  EXCEPTION WHEN OTHERS THEN
    -- If content is not valid JSON, just index the raw text
    NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
  END;
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS blobs_search_vector_trigger ON blobs;
CREATE TRIGGER blobs_search_vector_trigger
  BEFORE INSERT OR UPDATE ON blobs
  FOR EACH ROW
  EXECUTE FUNCTION blobs_search_vector_update();

-- Step 4: Backfill existing blobs
-- Uses the same logic as the trigger, with exception handling for non-JSON content.
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN SELECT blob_hash, content FROM blobs WHERE search_vector IS NULL LOOP
    BEGIN
      UPDATE blobs SET search_vector = to_tsvector('english',
        COALESCE(r.content::jsonb->>'message', '') || ' ' ||
        COALESCE(r.content::jsonb->>'summary', '') || ' ' ||
        COALESCE(r.content::jsonb->>'title', '') || ' ' ||
        COALESCE(r.content, '')
      ) WHERE blob_hash = r.blob_hash;
    EXCEPTION WHEN OTHERS THEN
      UPDATE blobs SET search_vector = to_tsvector('english', COALESCE(r.content, ''))
        WHERE blob_hash = r.blob_hash;
    END;
  END LOOP;
END $$;
