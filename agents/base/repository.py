"""Database repositories for tool calls and evaluation results.

Provides structured access to the tool_calls and eval_results tables.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import asyncpg
from langsmith import traceable
from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    """A tool execution record."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    tool_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    success: bool = True
    latency_ms: int | None = None


class EvalRecord(BaseModel):
    """An evaluation result record."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    eval_type: str
    agent_id: str
    input: str
    expected: str | None = None
    actual: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRepository:
    """Repository for tool call audit logs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @traceable(name="repo.store_tool_call")
    async def store(self, record: ToolCallRecord) -> str:
        """Store a tool call record."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tool_calls (id, conversation_id, tool_name, params, result, error, success, latency_ms)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
                """,
                record.id,
                record.conversation_id,
                record.tool_name,
                json.dumps(record.params),
                json.dumps(record.result) if record.result else None,
                record.error,
                record.success,
                record.latency_ms,
            )
        return record.id

    @traceable(name="repo.get_tool_calls_by_conversation")
    async def get_by_conversation(self, conversation_id: str) -> list[ToolCallRecord]:
        """Retrieve tool calls for a conversation."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, conversation_id, tool_name, params, result, error, success, latency_ms
                FROM tool_calls
                WHERE conversation_id = $1
                ORDER BY created_at ASC
                """,
                conversation_id,
            )
        return [
            ToolCallRecord(
                id=str(row["id"]),
                conversation_id=str(row["conversation_id"]),
                tool_name=row["tool_name"],
                params=json.loads(row["params"]) if row["params"] else {},
                result=json.loads(row["result"]) if row["result"] else None,
                error=row["error"],
                success=row["success"],
                latency_ms=row["latency_ms"],
            )
            for row in rows
        ]

    @traceable(name="repo.get_tool_calls_by_name")
    async def get_by_tool_name(
        self, tool_name: str, limit: int = 50
    ) -> list[ToolCallRecord]:
        """Retrieve recent tool calls by tool name."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, conversation_id, tool_name, params, result, error, success, latency_ms
                FROM tool_calls
                WHERE tool_name = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                tool_name,
                limit,
            )
        return [
            ToolCallRecord(
                id=str(row["id"]),
                conversation_id=str(row["conversation_id"]),
                tool_name=row["tool_name"],
                params=json.loads(row["params"]) if row["params"] else {},
                result=json.loads(row["result"]) if row["result"] else None,
                error=row["error"],
                success=row["success"],
                latency_ms=row["latency_ms"],
            )
            for row in rows
        ]


class EvalRepository:
    """Repository for evaluation results."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @traceable(name="repo.store_eval")
    async def store(self, record: EvalRecord) -> str:
        """Store an evaluation result."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO eval_results (id, eval_type, agent_id, input, expected, actual, score, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                """,
                record.id,
                record.eval_type,
                record.agent_id,
                record.input,
                record.expected,
                record.actual,
                record.score,
                json.dumps(record.metadata),
            )
        return record.id

    @traceable(name="repo.get_evals_by_agent")
    async def get_by_agent(self, agent_id: str, limit: int = 50) -> list[EvalRecord]:
        """Retrieve recent eval results for an agent."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, eval_type, agent_id, input, expected, actual, score, metadata
                FROM eval_results
                WHERE agent_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                agent_id,
                limit,
            )
        return [
            EvalRecord(
                id=str(row["id"]),
                eval_type=row["eval_type"],
                agent_id=row["agent_id"],
                input=row["input"],
                expected=row["expected"],
                actual=row["actual"],
                score=row["score"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )
            for row in rows
        ]

    @traceable(name="repo.get_evals_by_type")
    async def get_by_type(self, eval_type: str, limit: int = 50) -> list[EvalRecord]:
        """Retrieve recent eval results by type."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, eval_type, agent_id, input, expected, actual, score, metadata
                FROM eval_results
                WHERE eval_type = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                eval_type,
                limit,
            )
        return [
            EvalRecord(
                id=str(row["id"]),
                eval_type=row["eval_type"],
                agent_id=row["agent_id"],
                input=row["input"],
                expected=row["expected"],
                actual=row["actual"],
                score=row["score"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )
            for row in rows
        ]

    @traceable(name="repo.average_score")
    async def average_score(self, agent_id: str, eval_type: str) -> float | None:
        """Get average eval score for an agent and eval type."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT AVG(score) as avg_score
                FROM eval_results
                WHERE agent_id = $1 AND eval_type = $2
                """,
                agent_id,
                eval_type,
            )
        if row and row["avg_score"] is not None:
            return float(row["avg_score"])
        return None
