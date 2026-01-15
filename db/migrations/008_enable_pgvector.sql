-- Enable pgvector extension for semantic search
-- Run this on Railway Postgres

CREATE EXTENSION IF NOT EXISTS vector;

-- Verify it worked
SELECT * FROM pg_extension WHERE extname = 'vector';
