"""Tool correctness evaluation tests."""

from __future__ import annotations

import pytest

from agents.base.types import AgentID


TOOL_CORRECTNESS_CASES = [
    {
        "agent": AgentID.FLIGHTS,
        "query": "Flights from SFO to NRT on June 15",
        "expected_tool": "search_flights",
        "expected_params": {"origin": "SFO", "destination": "NRT"},
    },
    {
        "agent": AgentID.STAY,
        "query": "Hotels in Tokyo for 2 guests",
        "expected_tool": "search_hotels",
        "expected_params": {"location": "Tokyo", "guests": 2},
    },
    {
        "agent": AgentID.MARKETPLACE,
        "query": "Find laptops under $1000",
        "expected_tool": "search_products",
        "expected_params": {"max_price": 1000},
    },
    {
        "agent": AgentID.TWITTER,
        "query": "What's trending in tech?",
        "expected_tool": "get_trends",
        "expected_params": {},
    },
]


@pytest.mark.parametrize("case", TOOL_CORRECTNESS_CASES, ids=lambda c: c["query"][:30])
def test_tool_selection_correctness(case: dict) -> None:
    """Verify agents select the correct tool with correct parameters.

    TODO: Implement once agents have LLM integration.
    """
    assert case["expected_tool"]
    assert case["agent"] in AgentID
