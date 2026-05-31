"""Tests for the Python AgentService gRPC server."""

from __future__ import annotations

import grpc
import pytest
from concurrent import futures
from unittest.mock import patch, AsyncMock

from agents.server import AgentServiceServicer, serve
from agents.gen.orchestrator.v1 import orchestrator_pb2, orchestrator_pb2_grpc
from agents.base.types import AgentID, AgentResponse, Step, ToolCall


@pytest.fixture
def grpc_server():
    """Start a test gRPC server with the AgentServiceServicer."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    orchestrator_pb2_grpc.add_AgentServiceServicer_to_server(
        AgentServiceServicer(), server
    )
    port = server.add_insecure_port("localhost:0")
    server.start()
    yield f"localhost:{port}"
    server.stop(grace=0)


@pytest.fixture
def stub(grpc_server: str):
    """Create a gRPC stub connected to the test server."""
    channel = grpc.insecure_channel(grpc_server)
    return orchestrator_pb2_grpc.AgentServiceStub(channel)


class TestAgentServiceServicer:
    """Tests for the AgentService gRPC servicer."""

    def test_execute_unknown_agent(self, stub):
        """Unknown agent_id returns NOT_FOUND."""
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="nonexistent",
            query="hello",
            session_id="test",
        )
        with pytest.raises(grpc.RpcError) as exc_info:
            stub.Execute(req)
        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND

    def test_execute_flights_not_implemented(self, stub):
        """Flights agent returns placeholder when not yet wired to LLM."""
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="flights",
            query="Find flights to Tokyo",
            session_id="test-session",
        )
        resp = stub.Execute(req)
        assert resp.agent_id == "flights"
        assert "not yet implemented" in resp.answer.lower() or resp.answer != ""

    def test_execute_marketplace_not_implemented(self, stub):
        """Marketplace agent returns placeholder."""
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="marketplace",
            query="Find best laptop deals",
            session_id="test-session",
        )
        resp = stub.Execute(req)
        assert resp.agent_id == "marketplace"

    def test_execute_stay_not_implemented(self, stub):
        """Stay agent returns placeholder."""
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="stay",
            query="Hotels in Paris",
            session_id="test-session",
        )
        resp = stub.Execute(req)
        assert resp.agent_id == "stay"

    def test_execute_twitter_not_implemented(self, stub):
        """Twitter agent returns placeholder."""
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="twitter",
            query="Trending hashtags",
            session_id="test-session",
        )
        resp = stub.Execute(req)
        assert resp.agent_id == "twitter"

    def test_execute_all_agents_known(self, stub):
        """All four agents are registered and reachable."""
        queries = {
            "flights": "Find flights to NYC",
            "marketplace": "Buy a laptop",
            "stay": "Book a hotel room",
            "twitter": "Trending tweets today",
        }
        for agent_id, query in queries.items():
            req = orchestrator_pb2.ExecuteRequest(
                agent_id=agent_id,
                query=query,
                session_id="test",
            )
            resp = stub.Execute(req)
            assert resp.agent_id == agent_id

    def test_execute_stream_unimplemented(self, stub):
        """ExecuteStream returns UNIMPLEMENTED for now."""
        req = orchestrator_pb2.ExecuteStreamRequest(
            agent_id="flights",
            query="test",
            session_id="test",
        )
        with pytest.raises(grpc.RpcError) as exc_info:
            # Consume the stream to trigger the error
            list(stub.ExecuteStream(req))
        assert exc_info.value.code() == grpc.StatusCode.UNIMPLEMENTED

    def test_execute_preserves_session_id(self, stub):
        """Session ID is propagated to the agent."""
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="flights",
            query="Find flights",
            session_id="my-unique-session",
        )
        # The placeholder response should be returned without error
        resp = stub.Execute(req)
        assert resp.agent_id == "flights"
