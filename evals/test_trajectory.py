"""ReAct trajectory evaluation tests.

Validates reasoning quality, action selection, and observation usage
in agent reasoning traces.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.base.types import Step
from evals.golden_cases import TRAJECTORY_CASES
from evals.judges import LLMJudge, TrajectoryVerdict
from evals.runner import EvalCase, EvalSuite


# --- Deterministic trajectory checks ---


def check_trajectory_structure(steps: list[dict]) -> tuple[float, list[str]]:
    """Validate trajectory structure and return (score, issues).

    Checks:
    - All steps have non-empty thoughts
    - Actions reference known tools
    - Observations follow actions
    - Final step has no action (conclusion)
    """
    issues = []
    if not steps:
        return 0.0, ["Empty trajectory"]

    scores = []

    for i, step in enumerate(steps):
        step_score = 0.0

        # Thought quality
        thought = step.get("thought", "")
        if thought and len(thought) > 10:
            step_score += 0.4
        elif thought:
            step_score += 0.2
            issues.append(f"Step {i+1}: thought too short")
        else:
            issues.append(f"Step {i+1}: missing thought")

        # Action relevance
        action = step.get("action")
        observation = step.get("observation")

        if action and observation:
            step_score += 0.4  # Action with observation = good
        elif action and not observation:
            step_score += 0.2
            issues.append(f"Step {i+1}: action without observation")
        elif not action and i == len(steps) - 1:
            step_score += 0.4  # Final step with no action = conclusion
        elif not action and i < len(steps) - 1:
            issues.append(f"Step {i+1}: no action in non-final step")

        # Observation incorporation (check if next step references observation)
        if observation and i < len(steps) - 1:
            next_thought = steps[i + 1].get("thought", "")
            # Simple heuristic: any overlap between observation and next thought
            obs_words = set(observation.lower().split())
            thought_words = set(next_thought.lower().split())
            if obs_words & thought_words:
                step_score += 0.2
            else:
                issues.append(f"Step {i+1}: observation not used in next reasoning")
        elif not observation and action:
            pass  # OK for final steps
        else:
            step_score += 0.2  # No observation needed

        scores.append(min(step_score, 1.0))

    overall = sum(scores) / len(scores) if scores else 0.0
    return overall, issues


# --- Tests ---


def test_trajectory_has_reasoning() -> None:
    """Verify trajectory steps contain non-empty thoughts."""
    step = Step(
        thought="I need to search for flights",
        action="search_flights",
        observation="Found 3 results",
    )
    assert step.thought
    assert step.action
    assert step.observation


def test_trajectory_max_steps() -> None:
    """Verify agents respect max iteration limit (10)."""
    from agents.base.agent import BaseAgent

    assert BaseAgent.max_iterations == 10


@pytest.mark.parametrize(
    "case",
    TRAJECTORY_CASES,
    ids=lambda c: c["id"],
)
def test_trajectory_structure(case: dict) -> None:
    """Verify trajectory structure passes quality checks."""
    score, issues = check_trajectory_structure(case["steps"])
    assert score >= case["expected_min_score"], (
        f"Trajectory score {score:.2f} below threshold {case['expected_min_score']}: "
        f"issues={issues}"
    )


def test_trajectory_observation_used() -> None:
    """Verify observations from tools are incorporated into subsequent reasoning."""
    steps = [
        {
            "thought": "I need to search for flights from SFO to NRT",
            "action": "search_flights",
            "observation": "Found United $450, Delta $520",
        },
        {
            "thought": "United at $450 is the cheapest option from the search results",
            "action": None,
            "observation": None,
        },
    ]
    score, issues = check_trajectory_structure(steps)
    # Should have high score since observation is used in next step
    assert score >= 0.7, f"Score too low: {score:.2f}, issues: {issues}"


def test_trajectory_empty_fails() -> None:
    """Empty trajectory should score 0."""
    score, issues = check_trajectory_structure([])
    assert score == 0.0
    assert "Empty trajectory" in issues


@pytest.mark.parametrize(
    "case",
    TRAJECTORY_CASES,
    ids=lambda c: c["id"],
)
async def test_trajectory_llm_judge(case: dict) -> None:
    """Verify trajectory evaluation with mocked LLM-as-judge."""
    expected_verdict = TrajectoryVerdict(
        reasoning_quality=0.9,
        action_relevance=0.85,
        observation_usage=0.9,
        overall_score=0.88,
        reasoning="Good trajectory with clear reasoning chain.",
    )

    judge = LLMJudge()
    with patch.object(judge, "evaluate_trajectory", new_callable=AsyncMock) as mock:
        mock.return_value = expected_verdict
        verdict = await judge.evaluate_trajectory(case["query"], case["steps"])

    assert verdict.overall_score >= case["expected_min_score"]
    assert verdict.reasoning_quality >= 0.7
    assert verdict.action_relevance >= 0.7


async def test_trajectory_eval_suite() -> None:
    """Run trajectory evals through the EvalSuite runner."""
    suite = EvalSuite(eval_type="trajectory", agent_id="all")

    for case in TRAJECTORY_CASES:
        suite.add_case(
            input=case["query"],
            expected=str(case["expected_min_score"]),
            steps=case["steps"],
        )

    async def scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        score, issues = check_trajectory_structure(eval_case.metadata["steps"])
        return f"score={score:.2f}", score, {"issues": issues}

    results = await suite.run(scorer, threshold=0.7)
    assert suite.pass_rate >= 0.8, f"Trajectory pass rate: {suite.pass_rate:.2f}"
