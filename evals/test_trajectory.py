"""ReAct trajectory evaluation tests."""

from __future__ import annotations

import pytest

from agents.base.types import Step


def test_trajectory_has_reasoning() -> None:
    """Verify trajectory steps contain non-empty thoughts."""
    # TODO: Run agent and validate trajectory once LLM integration is complete
    step = Step(thought="I need to search for flights", action="search_flights", observation="Found 3 results")
    assert step.thought
    assert step.action


def test_trajectory_max_steps() -> None:
    """Verify agents respect max iteration limit."""
    # BaseAgent.max_iterations = 10
    # TODO: Test with mock LLM that never stops
    pass


def test_trajectory_observation_used() -> None:
    """Verify observations from tools are incorporated into subsequent reasoning."""
    # TODO: Implement with LLM-as-judge scoring
    pass
