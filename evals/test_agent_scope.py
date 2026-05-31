"""Tests that each agent rejects out-of-scope queries."""

from __future__ import annotations

import grpc
import pytest
from concurrent import futures

from agents.server import AgentServiceServicer
from agents.gen.orchestrator.v1 import orchestrator_pb2, orchestrator_pb2_grpc


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


class TestFlightsRejectsOutOfScope:
    """Flights agent should reject non-flight queries."""

    @pytest.mark.parametrize("query", [
        "Book a hotel in Paris",
        "Find the best laptop deals",
        "What are the trending hashtags on Twitter?",
        "What is the meaning of life?",
        "Help me cook pasta",
        "Tell me about stocks and crypto",
    ])
    def test_rejects_irrelevant_query(self, stub, query: str):
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="flights",
            query=query,
            session_id="test",
        )
        with pytest.raises(grpc.RpcError) as exc_info:
            stub.Execute(req)
        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert "out of scope" in exc_info.value.details().lower()

    @pytest.mark.parametrize("query", [
        "Find flights from NYC to Tokyo",
        "What airlines fly to London?",
        "Cheapest airfare to San Francisco",
        "Show me departure times from LAX",
    ])
    def test_accepts_in_scope_query(self, stub, query: str):
        """In-scope queries should NOT raise INVALID_ARGUMENT."""
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="flights",
            query=query,
            session_id="test",
        )
        # Should not raise INVALID_ARGUMENT (may raise other due to NotImplementedError placeholder)
        resp = stub.Execute(req)
        assert resp.agent_id == "flights"


class TestMarketplaceRejectsOutOfScope:
    """Marketplace agent should reject non-shopping queries."""

    @pytest.mark.parametrize("query", [
        "Find flights to London",
        "Book a hotel room for tonight",
        "Trending tweets today",
        "What is quantum computing?",
        "Play a song",
        "What time is sunset?",
    ])
    def test_rejects_irrelevant_query(self, stub, query: str):
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="marketplace",
            query=query,
            session_id="test",
        )
        with pytest.raises(grpc.RpcError) as exc_info:
            stub.Execute(req)
        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert "out of scope" in exc_info.value.details().lower()

    @pytest.mark.parametrize("query", [
        "Find the best price for a MacBook",
        "Compare laptop deals under $1000",
        "Where can I buy a new phone?",
        "Show me product listings for headphones",
    ])
    def test_accepts_in_scope_query(self, stub, query: str):
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="marketplace",
            query=query,
            session_id="test",
        )
        resp = stub.Execute(req)
        assert resp.agent_id == "marketplace"


class TestStayRejectsOutOfScope:
    """Stay agent should reject non-accommodation queries."""

    @pytest.mark.parametrize("query", [
        "Book a flight to NYC",
        "Find me a laptop deal",
        "Trending hashtags right now",
        "What is the weather like?",
        "Help me write an email",
        "Convert 100 USD to EUR",
    ])
    def test_rejects_irrelevant_query(self, stub, query: str):
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="stay",
            query=query,
            session_id="test",
        )
        with pytest.raises(grpc.RpcError) as exc_info:
            stub.Execute(req)
        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert "out of scope" in exc_info.value.details().lower()

    @pytest.mark.parametrize("query", [
        "Find a hotel in downtown Tokyo",
        "Best Airbnb for 3 nights in Paris",
        "Check room availability at the resort",
        "Book accommodation near the airport",
    ])
    def test_accepts_in_scope_query(self, stub, query: str):
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="stay",
            query=query,
            session_id="test",
        )
        resp = stub.Execute(req)
        assert resp.agent_id == "stay"


class TestTwitterRejectsOutOfScope:
    """Twitter agent should reject non-social-media queries."""

    @pytest.mark.parametrize("query", [
        "Find flights to Berlin",
        "Book a hotel in Rome",
        "Compare prices for running shoes",
        "Solve this math equation",
        "Translate this to French",
        "What should I have for dinner?",
    ])
    def test_rejects_irrelevant_query(self, stub, query: str):
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="twitter",
            query=query,
            session_id="test",
        )
        with pytest.raises(grpc.RpcError) as exc_info:
            stub.Execute(req)
        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert "out of scope" in exc_info.value.details().lower()

    @pytest.mark.parametrize("query", [
        "What's trending on Twitter today?",
        "Analyze the sentiment of this tweet",
        "Find posts with #AI hashtag",
        "Who are the top influencers in tech on social media?",
    ])
    def test_accepts_in_scope_query(self, stub, query: str):
        req = orchestrator_pb2.ExecuteRequest(
            agent_id="twitter",
            query=query,
            session_id="test",
        )
        resp = stub.Execute(req)
        assert resp.agent_id == "twitter"
