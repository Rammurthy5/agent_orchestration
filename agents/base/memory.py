"""Memory layer — PgVector-backed embedding storage and retrieval.

Provides per-agent isolated memory namespaces and conversation history per session.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
from langsmith import traceable
from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """A stored memory with embedding vector."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationEntry(BaseModel):
    """A stored conversation turn."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    agent_id: str
    query: str
    response: str
    latency_ms: int | None = None


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
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memories (id, agent_id, content, embedding, metadata)
                VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                """,
                entry.id,
                entry.agent_id,
                entry.content,
                _vector_literal(embedding),
                _json_dumps(entry.metadata),
            )
        return entry.id

    @traceable(name="memory.search")
    async def search(
        self,
        agent_id: str,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[MemorySearchResult]:
        """Search memories by cosine similarity within an agent's namespace.

        Args:
            agent_id: Restrict search to this agent's memories.
            query_embedding: 1536-dim embedding of the query.
            limit: Max results to return.

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
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                _vector_literal(query_embedding),
                agent_id,
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
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (id, session_id, agent_id, query, response, latency_ms)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                entry.id,
                entry.session_id,
                entry.agent_id,
                entry.query,
                entry.response,
                entry.latency_ms,
            )
        return entry.id

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
