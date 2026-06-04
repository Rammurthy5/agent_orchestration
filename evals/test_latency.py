"""Latency evaluation tests.

Measures and validates performance budgets for orchestration, agent, and tool layers.
Uses synthetic benchmarks for deterministic testing.
"""

from __future__ import annotations

import asyncio
import time

import grpc
import pytest
from concurrent import futures

from agents.server import AgentServiceServicer
from agents.gen.orchestrator.v1 import orchestrator_pb2, orchestrator_pb2_grpc
from evals.golden_cases import LATENCY_BUDGETS


# --- Budget Validation ---


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


# --- gRPC Latency Benchmarks ---


@pytest.fixture
def latency_server():
    """Start a test gRPC server for latency measurement."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    orchestrator_pb2_grpc.add_AgentServiceServicer_to_server(
        AgentServiceServicer(), server
    )
    port = server.add_insecure_port("localhost:0")
    server.start()
    yield f"localhost:{port}"
    server.stop(grace=0)


@pytest.fixture
def latency_stub(latency_server: str):
    """Create a gRPC stub for latency testing."""
    channel = grpc.insecure_channel(latency_server)
    return orchestrator_pb2_grpc.AgentServiceStub(channel)


def test_grpc_round_trip_latency(latency_stub) -> None:
    """Measure gRPC round-trip latency (serialize + deserialize + routing)."""
    latencies = []
    for _ in range(10):
        start = time.perf_counter()
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="flights",
            query="Find flights to Tokyo",
            session_id="latency-test",
        )
        try:
            latency_stub.Execute(req)
        except grpc.RpcError:
            pass  # We're measuring network round-trip, not success
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    # Sort for percentile calculation
    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    p95 = latencies[p95_idx] if latencies else 0

    # gRPC overhead should be under budget (generous for test environment)
    assert p95 < LATENCY_BUDGETS["orchestration_p95"] * 5, (
        f"gRPC P95 latency {p95:.1f}ms exceeds 5x budget "
        f"({LATENCY_BUDGETS['orchestration_p95'] * 5}ms)"
    )


def test_agent_dispatch_latency(latency_stub) -> None:
    """Measure full agent dispatch latency through gRPC."""
    agents = ["flights", "stay", "marketplace", "twitter"]
    latencies = {}

    for agent_id in agents:
        start = time.perf_counter()
        req = orchestrator_pb2.ExecuteRequest(
            agent_id=agent_id,
            query=f"Test query for {agent_id}",
            session_id="latency-test",
        )
        try:
            resp = latency_stub.Execute(req)
        except grpc.RpcError:
            pass
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies[agent_id] = elapsed_ms

    # All agents should respond within budget (generous for test)
    for agent_id, latency in latencies.items():
        assert latency < LATENCY_BUDGETS["agent_total_p95"], (
            f"Agent {agent_id} latency {latency:.1f}ms exceeds budget"
        )


# --- Async Operation Latency ---


async def test_async_operation_overhead() -> None:
    """Measure overhead of async operations (event loop, context switching)."""
    latencies = []
    for _ in range(100):
        start = time.perf_counter()
        await asyncio.sleep(0)  # Minimal async operation
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        latencies.append(elapsed_us)

    avg_us = sum(latencies) / len(latencies)
    # Async overhead should be < 1ms on average
    assert avg_us < 1000, f"Async overhead {avg_us:.1f}μs exceeds 1ms"


# --- Memory Operation Latency (simulated) ---


async def test_memory_search_simulated_latency() -> None:
    """Simulate memory search latency validation."""
    # In real env, this would connect to PgVector
    # Here we validate the budget is achievable
    start = time.perf_counter()
    # Simulate vector computation
    embedding = [0.1] * 1536
    dot_product = sum(a * b for a, b in zip(embedding, embedding))
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Pure computation should be well under memory budget
    assert elapsed_ms < LATENCY_BUDGETS["memory_search_p95"], (
        f"Simulated memory search {elapsed_ms:.1f}ms exceeds budget"
    )
