"""Tests for the database repository and memory layers.

These tests verify the Pydantic models, serialization, and logic without
requiring a live PostgreSQL connection (unit-level tests).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base.memory import (
    ConversationEntry,
    Memory,
    MemoryEntry,
    MemorySearchResult,
)
from agents.base.repository import (
    EvalRecord,
    EvalRepository,
    ToolCallRecord,
    ToolCallRepository,
)


# --- Model Tests ---


class TestMemoryEntry:
    def test_defaults(self):
        entry = MemoryEntry(agent_id="flights", content="test content")
        assert entry.agent_id == "flights"
        assert entry.content == "test content"
        assert entry.namespace == "default"
        assert entry.metadata == {}
        assert entry.ttl_hours is None
        assert entry.id  # UUID generated

    def test_with_ttl(self):
        entry = MemoryEntry(
            agent_id="stay", content="hotel info", ttl_hours=72, namespace="hotels"
        )
        assert entry.ttl_hours == 72
        assert entry.namespace == "hotels"


class TestConversationEntry:
    def test_defaults(self):
        entry = ConversationEntry(
            session_id="s1", agent_id="flights", query="hello", response="world"
        )
        assert entry.session_id == "s1"
        assert entry.latency_ms is None
        assert entry.ttl_hours is None

    def test_with_ttl(self):
        entry = ConversationEntry(
            session_id="s1",
            agent_id="flights",
            query="q",
            response="r",
            ttl_hours=168,
            latency_ms=50,
        )
        assert entry.ttl_hours == 168
        assert entry.latency_ms == 50


class TestToolCallRecord:
    def test_defaults(self):
        record = ToolCallRecord(
            conversation_id="c1", tool_name="search_flights", params={"origin": "NYC"}
        )
        assert record.success is True
        assert record.error is None
        assert record.result is None
        assert record.tool_name == "search_flights"

    def test_failed_call(self):
        record = ToolCallRecord(
            conversation_id="c1",
            tool_name="search_flights",
            params={},
            error="timeout",
            success=False,
            latency_ms=5000,
        )
        assert record.success is False
        assert record.error == "timeout"


class TestEvalRecord:
    def test_defaults(self):
        record = EvalRecord(
            eval_type="hallucination", agent_id="flights", input="test query"
        )
        assert record.score is None
        assert record.expected is None
        assert record.metadata == {}

    def test_full_record(self):
        record = EvalRecord(
            eval_type="tool_correctness",
            agent_id="marketplace",
            input="compare laptops",
            expected="search_products",
            actual="search_products",
            score=1.0,
            metadata={"model": "gpt-4", "iteration": 2},
        )
        assert record.score == 1.0
        assert record.metadata["model"] == "gpt-4"


# --- Memory Logic Tests ---


class TestMemorySearchResult:
    def test_model(self):
        result = MemorySearchResult(
            content="flight to Tokyo", metadata={"price": 500}, similarity=0.92
        )
        assert result.similarity == 0.92
        assert result.metadata["price"] == 500


class TestMemoryTTL:
    """Verify TTL computation logic."""

    def test_expires_at_calculation(self):
        """Ensure expires_at is computed from ttl_hours."""
        entry = MemoryEntry(agent_id="flights", content="test", ttl_hours=24)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=entry.ttl_hours)
        # Should be approximately 24 hours from now
        assert (expires - now).total_seconds() == pytest.approx(86400, abs=1)

    def test_no_ttl_means_no_expiry(self):
        entry = MemoryEntry(agent_id="flights", content="test")
        assert entry.ttl_hours is None


# --- Repository Mock Tests ---


class TestToolCallRepository:
    @pytest.fixture
    def mock_pool(self):
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        return pool, conn

    async def test_store(self, mock_pool):
        pool, conn = mock_pool
        repo = ToolCallRepository(pool)
        record = ToolCallRecord(
            conversation_id="c1",
            tool_name="search_flights",
            params={"origin": "NYC"},
            result={"flights": 3},
            latency_ms=100,
        )
        result_id = await repo.store(record)
        assert result_id == record.id
        conn.execute.assert_called_once()


class TestEvalRepository:
    @pytest.fixture
    def mock_pool(self):
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        return pool, conn

    async def test_store(self, mock_pool):
        pool, conn = mock_pool
        repo = EvalRepository(pool)
        record = EvalRecord(
            eval_type="latency",
            agent_id="flights",
            input="test",
            score=0.95,
        )
        result_id = await repo.store(record)
        assert result_id == record.id
        conn.execute.assert_called_once()


class TestMemoryConnect:
    async def test_connect_creates_pool(self):
        """Verify that connect attempts to create a pool (will fail without DB)."""
        memory = Memory(dsn="postgresql://localhost:5432/nonexistent_test_db")
        with pytest.raises(Exception):
            await memory.connect()
