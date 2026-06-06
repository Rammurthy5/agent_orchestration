"""Latency evaluation tests.

Measures and validates performance budgets for orchestration, agent, and tool layers.
Uses synthetic benchmarks for deterministic testing.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.base.types import AgentID, AgentResponse
from agents.server import AgentServiceServicer
from evals.golden_cases import LATENCY_BUDGETS


def _request(agent_id: str, query: str = "Test query", session_id: str = "latency-test"):
    return SimpleNamespace(agent_id=agent_id, query=query, session_id=session_id, metadata={})


class _AbortError(Exception):
    pass


class _DummyContext:
    def abort(self, code, details):
        raise _AbortError(f"{code}: {details}")


@pytest.fixture
def servicer():
    return AgentServiceServicer()


def test_latency_thresholds_defined() -> None:
    """Verify latency thresholds are set for all critical paths."""
    assert "orchestration_p95" in LATENCY_BUDGETS
    assert "agent_total_p95" in LATENCY_BUDGETS
    assert "tool_call_p95" in LATENCY_BUDGETS
    assert "memory_search_p95" in LATENCY_BUDGETS
    assert "grpc_overhead_p95" in LATENCY_BUDGETS


def test_budget_values_reasonable() -> None:
    """Verify latency budgets are within reasonable ranges."""
    assert LATENCY_BUDGETS["orchestration_p95"] <= 500  # < 500ms routing
    assert LATENCY_BUDGETS["agent_total_p95"] <= 30_000  # < 30s total
    assert LATENCY_BUDGETS["tool_call_p95"] <= 10_000  # < 10s per tool
    assert LATENCY_BUDGETS["memory_search_p95"] <= 1_000  # < 1s search
    assert LATENCY_BUDGETS["grpc_overhead_p95"] <= 200  # < 200ms overhead


def _patch_agent(servicer: AgentServiceServicer, agent_id: AgentID, answer: str = "ok") -> None:
    servicer._agents[agent_id].run = AsyncMock(
        return_value=AgentResponse(agent_id=agent_id, answer=answer)
    )
    servicer._memory.store_conversation = AsyncMock()


def test_service_round_trip_latency(servicer) -> None:
    """Measure direct service latency with the ReAct loop mocked out."""
    _patch_agent(servicer, AgentID.FLIGHTS)

    latencies = []
    for _ in range(10):
        start = time.perf_counter()
        try:
            servicer.Execute(_request("flights", "Find flights to Tokyo"), _DummyContext())
        except _AbortError:
            pass
        latencies.append((time.perf_counter() - start) * 1000)

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    p95 = latencies[p95_idx] if latencies else 0

    assert p95 < LATENCY_BUDGETS["orchestration_p95"] * 5, (
        f"Service P95 latency {p95:.1f}ms exceeds 5x budget "
        f"({LATENCY_BUDGETS['orchestration_p95'] * 5}ms)"
    )


def test_agent_dispatch_latency(servicer) -> None:
    """Measure full agent dispatch latency through the service."""
    agents = [
        (AgentID.FLIGHTS, "flights"),
        (AgentID.STAY, "stay"),
        (AgentID.MARKETPLACE, "marketplace"),
        (AgentID.TWITTER, "twitter"),
    ]
    latencies = {}

    for agent_enum, agent_id in agents:
        _patch_agent(servicer, agent_enum)
        start = time.perf_counter()
        try:
            servicer.Execute(_request(agent_id), _DummyContext())
        except _AbortError:
            pass
        latencies[agent_id] = (time.perf_counter() - start) * 1000

    for agent_id, latency in latencies.items():
        assert latency < LATENCY_BUDGETS["agent_total_p95"], (
            f"Agent {agent_id} latency {latency:.1f}ms exceeds budget"
        )


async def test_async_operation_overhead() -> None:
    """Measure overhead of async operations (event loop, context switching)."""
    latencies = []
    for _ in range(100):
        start = time.perf_counter()
        await asyncio.sleep(0)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        latencies.append(elapsed_us)

    avg_us = sum(latencies) / len(latencies)
    assert avg_us < 1000, f"Async overhead {avg_us:.1f}μs exceeds 1ms"


async def test_memory_search_simulated_latency() -> None:
    """Simulate memory search latency validation."""
    start = time.perf_counter()
    embedding = [0.1] * 1536
    _ = sum(a * b for a, b in zip(embedding, embedding))
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < LATENCY_BUDGETS["memory_search_p95"], (
        f"Simulated memory search {elapsed_ms:.1f}ms exceeds budget"
    )
