-- Add embedding column to blobs table for semantic search
-- Must run after 008_enable_pgvector.sql

ALTER TABLE blobs ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Create index for fast similarity search
CREATE INDEX IF NOT EXISTS blobs_embedding_idx ON blobs USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
