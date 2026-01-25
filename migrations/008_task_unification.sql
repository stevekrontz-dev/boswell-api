-- TASK UNIFICATION MIGRATION
-- Links tasks table to memory system via blob_hash
-- Author: CW (2026-01-25)
-- Context: Tasks and memories were two disconnected systems causing orphans

-- Step 1: Add blob_hash column
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS blob_hash TEXT;

-- Step 2: Create index for lookups
CREATE INDEX IF NOT EXISTS idx_tasks_blob_hash ON tasks(blob_hash);

-- Step 3: Add foreign key constraint (soft - blob might not exist yet for old tasks)
-- Note: Not enforcing FK because some old tasks may not have corresponding blobs
-- ALTER TABLE tasks ADD CONSTRAINT fk_tasks_blob FOREIGN KEY (blob_hash) REFERENCES blobs(blob_hash);

-- Verification query:
-- SELECT id, description, blob_hash FROM tasks WHERE blob_hash IS NULL LIMIT 10;
