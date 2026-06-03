-- Retention policy and schema enhancements
-- Adds TTL support, soft-delete, and cleanup infrastructure

-- Add retention columns to conversations
ALTER TABLE conversations ADD COLUMN expires_at TIMESTAMPTZ;
ALTER TABLE conversations ADD COLUMN deleted_at TIMESTAMPTZ;

CREATE INDEX idx_conversations_expires ON conversations (expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_conversations_created ON conversations (created_at);

-- Add retention columns to memories
ALTER TABLE memories ADD COLUMN namespace TEXT NOT NULL DEFAULT 'default';
ALTER TABLE memories ADD COLUMN expires_at TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN deleted_at TIMESTAMPTZ;

CREATE INDEX idx_memories_namespace ON memories (agent_id, namespace);
CREATE INDEX idx_memories_expires ON memories (expires_at) WHERE expires_at IS NOT NULL;

-- Add error tracking to tool_calls
ALTER TABLE tool_calls ADD COLUMN error TEXT;
ALTER TABLE tool_calls ADD COLUMN success BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX idx_tool_calls_created ON tool_calls (created_at);

-- Retention cleanup function: deletes expired rows
CREATE OR REPLACE FUNCTION cleanup_expired_rows() RETURNS void AS $$
BEGIN
    -- Soft-delete expired conversations
    UPDATE conversations
    SET deleted_at = NOW()
    WHERE expires_at < NOW() AND deleted_at IS NULL;

    -- Soft-delete expired memories
    UPDATE memories
    SET deleted_at = NOW()
    WHERE expires_at < NOW() AND deleted_at IS NULL;

    -- Hard-delete rows soft-deleted more than 30 days ago
    DELETE FROM conversations WHERE deleted_at < NOW() - INTERVAL '30 days';
    DELETE FROM memories WHERE deleted_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- Migration tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_migrations (version, name) VALUES (1, '001_initial') ON CONFLICT DO NOTHING;
INSERT INTO schema_migrations (version, name) VALUES (2, '002_retention') ON CONFLICT DO NOTHING;
