"""Memory layer — PgVector-backed embedding storage and retrieval.

Provides per-agent isolated memory namespaces and conversation history per session.
Supports TTL-based retention via expires_at columns.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from langsmith import traceable
from pydantic import BaseModel, Field

from agents.base.safety import redact_text, redact_value


class MemoryEntry(BaseModel):
    """A stored memory with embedding vector."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    content: str
    namespace: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)
    ttl_hours: int | None = None  # If set, expires after this many hours


class ConversationEntry(BaseModel):
    """A stored conversation turn."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    agent_id: str
    query: str
    response: str
    latency_ms: int | None = None
    ttl_hours: int | None = None  # If set, expires after this many hours


class MemorySearchResult(BaseModel):
    """A memory entry with similarity score."""

    content: str
    metadata: dict[str, Any]
    similarity: float


class Memory:
    """PgVector-backed memory store for agents.

    Each agent has an isolated namespace. Conversation history is scoped by session_id.

    Env vars:
        DATABASE_URL: PostgreSQL connection string (default: postgresql://localhost:5432/orchestrator)
    """

    def __init__(self, dsn: str = "postgresql://localhost:5432/orchestrator"):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Initialize the connection pool."""
        self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()

    @traceable(name="memory.store")
    async def store(self, entry: MemoryEntry, embedding: list[float]) -> str:
        """Store a memory entry with its embedding vector.

        Args:
            entry: The memory content and metadata.
            embedding: 1536-dim embedding vector.

        Returns:
            The stored entry's UUID.
        """
        expires_at = None
        if entry.ttl_hours:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=entry.ttl_hours)

        safe_entry = entry.model_copy(
            update={
                "content": redact_text(entry.content),
                "metadata": redact_value(entry.metadata),
            }
        )

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memories (id, agent_id, namespace, content, embedding, metadata, expires_at)
                VALUES ($1, $2, $3, $4, $5::vector, $6::jsonb, $7)
                """,
                safe_entry.id,
                safe_entry.agent_id,
                safe_entry.namespace,
                safe_entry.content,
                _vector_literal(embedding),
                _json_dumps(safe_entry.metadata),
                expires_at,
            )
        return safe_entry.id

    @traceable(name="memory.search")
    async def search(
        self,
        agent_id: str,
        query_embedding: list[float],
        limit: int = 5,
        namespace: str = "default",
    ) -> list[MemorySearchResult]:
        """Search memories by cosine similarity within an agent's namespace.

        Args:
            agent_id: Restrict search to this agent's memories.
            query_embedding: 1536-dim embedding of the query.
            limit: Max results to return.
            namespace: Memory namespace to search within.

        Returns:
            List of matching memories ordered by similarity (descending).
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT content, metadata,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM memories
                WHERE agent_id = $2
                  AND namespace = $3
                  AND deleted_at IS NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY embedding <=> $1::vector
                LIMIT $4
                """,
                _vector_literal(query_embedding),
                agent_id,
                namespace,
                limit,
            )
        return [
            MemorySearchResult(
                content=row["content"],
                metadata=_json_loads(row["metadata"]),
                similarity=float(row["similarity"]),
            )
            for row in rows
        ]

    @traceable(name="memory.store_conversation")
    async def store_conversation(self, entry: ConversationEntry) -> str:
        """Store a conversation turn."""
        expires_at = None
        if entry.ttl_hours:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=entry.ttl_hours)

        safe_entry = entry.model_copy(
            update={
                "query": redact_text(entry.query),
                "response": redact_text(entry.response),
            }
        )

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (id, session_id, agent_id, query, response, latency_ms, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                safe_entry.id,
                safe_entry.session_id,
                safe_entry.agent_id,
                safe_entry.query,
                safe_entry.response,
                safe_entry.latency_ms,
                expires_at,
            )
        return safe_entry.id

    @traceable(name="memory.get_conversation_history")
    async def get_conversation_history(
        self, session_id: str, limit: int = 20
    ) -> list[ConversationEntry]:
        """Retrieve recent conversation history for a session."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, agent_id, query, response, latency_ms
                FROM conversations
                WHERE session_id = $1
                  AND deleted_at IS NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY created_at DESC
                LIMIT $2
                """,
                session_id,
                limit,
            )
        return [
            ConversationEntry(
                id=str(row["id"]),
                session_id=row["session_id"],
                agent_id=row["agent_id"],
                query=row["query"],
                response=row["response"],
                latency_ms=row["latency_ms"],
            )
            for row in reversed(rows)  # Return in chronological order
        ]

    @traceable(name="memory.cleanup_expired")
    async def cleanup_expired(self) -> int:
        """Soft-delete expired memories and conversations. Returns count of affected rows."""
        async with self._pool.acquire() as conn:
            result1 = await conn.execute(
                """
                UPDATE memories SET deleted_at = NOW()
                WHERE expires_at < NOW() AND deleted_at IS NULL
                """
            )
            result2 = await conn.execute(
                """
                UPDATE conversations SET deleted_at = NOW()
                WHERE expires_at < NOW() AND deleted_at IS NULL
                """
            )
        count1 = int(result1.split()[-1]) if result1 else 0
        count2 = int(result2.split()[-1]) if result2 else 0
        return count1 + count2

    @traceable(name="memory.purge_deleted")
    async def purge_deleted(self, older_than_days: int = 30) -> int:
        """Hard-delete rows that were soft-deleted more than N days ago."""
        async with self._pool.acquire() as conn:
            result1 = await conn.execute(
                """
                DELETE FROM memories
                WHERE deleted_at < NOW() - ($1 || ' days')::interval
                """,
                str(older_than_days),
            )
            result2 = await conn.execute(
                """
                DELETE FROM conversations
                WHERE deleted_at < NOW() - ($1 || ' days')::interval
                """,
                str(older_than_days),
            )
        count1 = int(result1.split()[-1]) if result1 else 0
        count2 = int(result2.split()[-1]) if result2 else 0
        return count1 + count2

    @traceable(name="memory.delete_by_agent")
    async def delete_by_agent(self, agent_id: str) -> int:
        """Soft-delete all memories for a specific agent."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE memories SET deleted_at = NOW()
                WHERE agent_id = $1 AND deleted_at IS NULL
                """,
                agent_id,
            )
        return int(result.split()[-1]) if result else 0


def _vector_literal(embedding: list[float]) -> str:
    """Convert embedding list to pgvector literal format."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _json_dumps(data: dict[str, Any]) -> str:
    import json
    return json.dumps(data)


def _json_loads(data: Any) -> dict[str, Any]:
    import json
    if isinstance(data, str):
        return json.loads(data)
    return dict(data) if data else {}
