-- Migration 018: FSRS-6 Dual-Strength Decay Model
-- Replaces simple strength decay with Bjork's "New Theory of Disuse":
--   storage_strength: How well-encoded. Grows monotonically. NEVER decays.
--   retrieval_strength: How accessible right now. Decays with time, resets on access.
--   stability: How resistant to forgetting. Grows MORE when a fading memory is accessed.
-- Formula: R(t) = (1 + t/(9*S))^(-1) where S=stability, t=days since last access
--
-- Honors sacred directive bf4b68532a81: no memory is ever deleted.
-- storage_strength only grows — this is the safety guarantee.

ALTER TABLE trails ADD COLUMN IF NOT EXISTS storage_strength FLOAT DEFAULT 1.0;
ALTER TABLE trails ADD COLUMN IF NOT EXISTS retrieval_strength FLOAT DEFAULT 1.0;
ALTER TABLE trails ADD COLUMN IF NOT EXISTS stability FLOAT DEFAULT 1.0;

-- Backfill: storage_strength from traversal history, retrieval from FSRS-6 formula
UPDATE trails SET
  storage_strength = LEAST(GREATEST(LOG(2, GREATEST(traversal_count,1)+1) * GREATEST(strength,1.0), 1.0), 20.0),
  stability = GREATEST(LOG(2, GREATEST(traversal_count,1)+1) * GREATEST(strength,1.0), 1.0),
  retrieval_strength = POWER(
    1.0 + EXTRACT(EPOCH FROM (NOW()-COALESCE(last_traversed,created_at)))/86400.0
      / (9.0 * GREATEST(LOG(2, GREATEST(traversal_count,1)+1) * GREATEST(strength,1.0), 1.0)),
    -1.0)
WHERE storage_strength = 1.0 AND traversal_count > 0;

CREATE INDEX IF NOT EXISTS idx_trails_retrieval ON trails(retrieval_strength DESC);
CREATE INDEX IF NOT EXISTS idx_trails_storage ON trails(storage_strength DESC);
