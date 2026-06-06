"""Tests that each agent rejects out-of-scope queries."""

from __future__ import annotations

import pytest
import grpc
from unittest.mock import AsyncMock

from agents.base.types import AgentID, AgentResponse, ToolCall
from agents.server import AgentServiceServicer


class AbortError(Exception):
    def __init__(self, code, details):
        super().__init__(details)
        self.code = code
        self.details = details


class DummyContext:
    def abort(self, code, details):
        raise AbortError(code, details)


@pytest.fixture
def servicer():
    """Create a direct AgentServiceServicer for unit-style scope checks."""
    return AgentServiceServicer()


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
    def test_rejects_irrelevant_query(self, servicer, query: str):
        with pytest.raises(AbortError) as exc_info:
            servicer.Execute(
                type("Req", (), {"agent_id": "flights", "query": query, "session_id": "test", "metadata": {}})(),
                DummyContext(),
            )
        assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT
        assert "out of scope" in str(exc_info.value).lower()

    @pytest.mark.parametrize("query", [
        "Find flights from NYC to Tokyo",
        "What airlines fly to London?",
        "Cheapest airfare to San Francisco",
        "Show me departure times from LAX",
    ])
    def test_accepts_in_scope_query(self, servicer, query: str):
        """In-scope queries should NOT raise INVALID_ARGUMENT."""
        servicer._agents[AgentID.FLIGHTS].run = AsyncMock(
            return_value=AgentResponse(agent_id=AgentID.FLIGHTS, answer="ok")
        )
        servicer._memory.store_conversation = AsyncMock()
        resp = servicer.Execute(
            type("Req", (), {"agent_id": "flights", "query": query, "session_id": "test", "metadata": {}})(),
            DummyContext(),
        )
        assert resp.agent_id == "flights"


class TestMarketplaceAcceptsAllQueries:
    """Marketplace agent is the fallback — accepts all queries routed to it."""

    @pytest.mark.parametrize("query", [
        "Find flights to London",
        "Book a hotel room for tonight",
        "Trending tweets today",
        "Find the best price for a MacBook",
        "Compare laptop deals under $1000",
        "Where can I buy a new phone?",
        "Show me product listings for headphones",
    ])
    def test_accepts_any_query(self, servicer, query: str):
        servicer._agents[AgentID.MARKETPLACE].run = AsyncMock(
            return_value=AgentResponse(agent_id=AgentID.MARKETPLACE, answer="ok")
        )
        servicer._memory.store_conversation = AsyncMock()
        resp = servicer.Execute(
            type("Req", (), {"agent_id": "marketplace", "query": query, "session_id": "test", "metadata": {}})(),
            DummyContext(),
        )
        assert resp.agent_id == "marketplace"

    @pytest.mark.parametrize("query", [
        "Find the best price for a MacBook",
        "Compare laptop deals under $1000",
        "Where can I buy a new phone?",
        "Show me product listings for headphones",
    ])
    def test_accepts_in_scope_query(self, servicer, query: str):
        servicer._agents[AgentID.MARKETPLACE].run = AsyncMock(
            return_value=AgentResponse(agent_id=AgentID.MARKETPLACE, answer="ok")
        )
        servicer._memory.store_conversation = AsyncMock()
        resp = servicer.Execute(
            type("Req", (), {"agent_id": "marketplace", "query": query, "session_id": "test", "metadata": {}})(),
            DummyContext(),
        )
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
    def test_rejects_irrelevant_query(self, servicer, query: str):
        with pytest.raises(AbortError) as exc_info:
            servicer.Execute(
                type("Req", (), {"agent_id": "stay", "query": query, "session_id": "test", "metadata": {}})(),
                DummyContext(),
            )
        assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT
        assert "out of scope" in str(exc_info.value).lower()

    @pytest.mark.parametrize("query", [
        "Find a hotel in downtown Tokyo",
        "Best Airbnb for 3 nights in Paris",
        "Check room availability at the resort",
        "Book accommodation near the airport",
    ])
    def test_accepts_in_scope_query(self, servicer, query: str):
        servicer._agents[AgentID.STAY].run = AsyncMock(
            return_value=AgentResponse(agent_id=AgentID.STAY, answer="ok")
        )
        servicer._memory.store_conversation = AsyncMock()
        resp = servicer.Execute(
            type("Req", (), {"agent_id": "stay", "query": query, "session_id": "test", "metadata": {}})(),
            DummyContext(),
        )
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
    def test_rejects_irrelevant_query(self, servicer, query: str):
        with pytest.raises(AbortError) as exc_info:
            servicer.Execute(
                type("Req", (), {"agent_id": "twitter", "query": query, "session_id": "test", "metadata": {}})(),
                DummyContext(),
            )
        assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT
        assert "out of scope" in str(exc_info.value).lower()

    @pytest.mark.parametrize("query", [
        "What's trending on Twitter today?",
        "Analyze the sentiment of this tweet",
        "Find posts with #AI hashtag",
        "Who are the top influencers in tech on social media?",
    ])
    def test_accepts_in_scope_query(self, servicer, query: str):
        servicer._agents[AgentID.TWITTER].run = AsyncMock(
            return_value=AgentResponse(agent_id=AgentID.TWITTER, answer="ok")
        )
        servicer._memory.store_conversation = AsyncMock()
        resp = servicer.Execute(
            type("Req", (), {"agent_id": "twitter", "query": query, "session_id": "test", "metadata": {}})(),
            DummyContext(),
        )
        assert resp.agent_id == "twitter"
