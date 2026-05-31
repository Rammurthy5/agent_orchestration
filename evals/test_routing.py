"""Routing evaluation tests — validate intent → agent classification."""

from __future__ import annotations

import pytest

from agents.base.types import AgentID


ROUTING_CASES = [
    ("Find cheapest flights to Tokyo", AgentID.FLIGHTS),
    ("Book a flight from JFK to LAX", AgentID.FLIGHTS),
    ("What airline flies direct to London?", AgentID.FLIGHTS),
    ("Find me a hotel in Paris", AgentID.STAY),
    ("Best accommodation near the beach", AgentID.STAY),
    ("Budget hostel in Bangkok", AgentID.STAY),
    ("Compare prices for a laptop", AgentID.MARKETPLACE),
    ("I want to buy a new phone", AgentID.MARKETPLACE),
    ("Best deal on headphones", AgentID.MARKETPLACE),
    ("Trending hashtags on Twitter", AgentID.TWITTER),
    ("Analyze sentiment of tweets about crypto", AgentID.TWITTER),
    ("Generate a tweet about sustainability", AgentID.TWITTER),
]


@pytest.mark.parametrize("query,expected_agent", ROUTING_CASES)
def test_routing_classification(query: str, expected_agent: AgentID) -> None:
    """Verify the Go router would classify this query to the expected agent.

    NOTE: This is a Python-side dataset for eval tracking.
    Integration tests will call the Go router via gRPC.
    """
    # TODO: Call Go router via gRPC once proto stubs are generated
    # For now, validate the dataset is well-formed
    assert query
    assert expected_agent in AgentID
