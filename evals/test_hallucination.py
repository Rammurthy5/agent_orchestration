"""Hallucination detection evaluation tests."""

from __future__ import annotations

import pytest


HALLUCINATION_CASES = [
    {
        "query": "Flights from SFO to NRT",
        "tool_output": "United $450, Delta $520",
        "agent_answer": "The cheapest flight is United at $450",
        "has_hallucination": False,
    },
    {
        "query": "Flights from SFO to NRT",
        "tool_output": "United $450, Delta $520",
        "agent_answer": "The cheapest flight is Spirit at $200",
        "has_hallucination": True,
    },
]


@pytest.mark.parametrize("case", HALLUCINATION_CASES, ids=lambda c: c["agent_answer"][:30])
def test_hallucination_detection(case: dict) -> None:
    """Verify that agent answers are grounded in tool outputs.

    TODO: Implement LLM-as-judge grounding check.
    """
    # Placeholder — will use LLM to verify grounding
    assert isinstance(case["has_hallucination"], bool)
