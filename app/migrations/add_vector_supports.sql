-- Add vector support to PostgreSQL
CREATE EXTENSION IF NOT EXISTS vector;

-- Content chunks table for storing semantic pieces of each subtopic
CREATE TABLE content_chunks (
    id SERIAL PRIMARY KEY,
    subtopic_id INTEGER NOT NULL REFERENCES subtopics(id) ON DELETE CASCADE,
    chunk_type VARCHAR(50) NOT NULL, -- 'definition', 'example', 'application', 'procedure'
    content TEXT NOT NULL,
    embedding vector(1536), -- 1536 dimensions from Azure OpenAI text-embedding-ada-002
    token_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Index for fast vector similarity searches
    CONSTRAINT valid_chunk_type CHECK (chunk_type IN ('definition', 'example', 'application', 'procedure', 'concept'))
);

-- Vector similarity index - this makes vector searches fast
CREATE INDEX content_chunks_embedding_idx ON content_chunks USING ivfflat (embedding vector_cosine_ops);

-- Regular indexes for filtering
CREATE INDEX content_chunks_subtopic_idx ON content_chunks(subtopic_id);
CREATE INDEX content_chunks_type_idx ON content_chunks(chunk_type);