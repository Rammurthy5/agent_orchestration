"""Shared pytest fixtures for evaluation tests."""

from __future__ import annotations

import pytest

from agents.base.types import AgentID, AgentRequest


@pytest.fixture
def sample_requests() -> dict[AgentID, AgentRequest]:
    """Sample requests mapped to their expected agent."""
    return {
        AgentID.FLIGHTS: AgentRequest(
            query="Find cheapest flights to Tokyo",
            session_id="test-session-1",
        ),
        AgentID.MARKETPLACE: AgentRequest(
            query="Compare prices for MacBook Pro",
            session_id="test-session-2",
        ),
        AgentID.STAY: AgentRequest(
            query="Find a hotel in Paris for next weekend",
            session_id="test-session-3",
        ),
        AgentID.TWITTER: AgentRequest(
            query="What are the trending hashtags about AI?",
            session_id="test-session-4",
        ),
    }
