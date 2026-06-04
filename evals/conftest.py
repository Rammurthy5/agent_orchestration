"""Shared pytest fixtures for evaluation tests."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

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


class EvalResultCollector:
    """Collects eval results during a pytest session for persistence."""

    def __init__(self):
        self.results: list[dict] = []

    def record(
        self,
        eval_type: str,
        agent_id: str,
        input_text: str,
        expected: str | None,
        actual: str | None,
        score: float,
        passed: bool,
        metadata: dict | None = None,
    ) -> None:
        self.results.append({
            "eval_type": eval_type,
            "agent_id": agent_id,
            "input": input_text,
            "expected": expected,
            "actual": actual,
            "score": score,
            "passed": passed,
            "metadata": metadata or {},
            "timestamp": time.time(),
        })

    def summary(self) -> dict:
        """Return a summary of collected results."""
        if not self.results:
            return {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0}
        passed = sum(1 for r in self.results if r["passed"])
        return {
            "total": len(self.results),
            "passed": passed,
            "failed": len(self.results) - passed,
            "pass_rate": passed / len(self.results),
        }


@pytest.fixture(scope="session")
def eval_collector() -> EvalResultCollector:
    """Session-scoped collector for eval results."""
    return EvalResultCollector()


def pytest_sessionfinish(session, exitstatus):
    """Write eval results to JSON file after test session completes."""
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    # Collect results from any EvalResultCollector fixtures
    # This is a fallback — primary persistence is via the EvalSuite.run() method
    results_file = results_dir / f"eval_run_{int(time.time())}.json"

    # Gather test outcomes from pytest
    test_results = []
    if hasattr(session, "_eval_results"):
        test_results = session._eval_results

    if test_results:
        results_file.write_text(json.dumps(test_results, indent=2, default=str))


@pytest.fixture
def assert_eval_score():
    """Fixture that provides score assertion with clear error messages."""

    def _assert(score: float, threshold: float, context: str = ""):
        assert score >= threshold, (
            f"Eval score {score:.3f} below threshold {threshold:.3f}"
            + (f" — {context}" if context else "")
        )

    return _assert
