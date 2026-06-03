-- Agent Orchestration Platform: Initial Schema
-- PostgreSQL 15+ with pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;

-- Conversations table: stores all user interactions
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    query TEXT NOT NULL,
    response TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversations_session ON conversations (session_id);
CREATE INDEX idx_conversations_agent ON conversations (agent_id);

-- Agent memory with vector embeddings for semantic retrieval
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_memories_agent ON memories (agent_id);
CREATE INDEX idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);

-- Tool call audit log
CREATE TABLE tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    tool_name TEXT NOT NULL,
    params JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tool_calls_conversation ON tool_calls (conversation_id);

-- Evaluation results for tracking agent quality
CREATE TABLE eval_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_type TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    input TEXT NOT NULL,
    expected TEXT,
    actual TEXT,
    score REAL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_eval_results_type ON eval_results (eval_type);
CREATE INDEX idx_eval_results_agent ON eval_results (agent_id);
