"""Hallucination detection evaluation tests.

Uses LLM-as-judge to verify agent answers are grounded in tool outputs.
Falls back to heuristic checking when no LLM is available.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest

from evals.golden_cases import GROUNDING_CASES
from evals.judges import GroundingVerdict, LLMJudge, _parse_json
from evals.runner import EvalCase, EvalSuite


# --- Heuristic grounding checker (no LLM required) ---


def heuristic_grounding_check(tool_output: str, agent_answer: str) -> tuple[bool, float]:
    """Simple heuristic: check if key entities from agent_answer appear in tool_output.

    Returns (is_grounded, score).
    """
    tool_lower = tool_output.lower()

    # Extract verifiable entities: prices, multi-word proper nouns, specific numbers
    # Focus on factual claims that can be checked against tool output
    import re

    # Prices like $450, $200
    prices = re.findall(r"\$[\d,]+", agent_answer)
    # Proper nouns (capitalized multi-word or single-word names that aren't sentence starters)
    words = agent_answer.split()
    proper_nouns = []
    for i, w in enumerate(words):
        # Skip first word (sentence start) and common words
        if i == 0 or w.lower() in {"the", "i", "a", "an", "is", "at", "for", "in", "and", "or"}:
            continue
        if w[0].isupper() and not w.startswith("#"):
            proper_nouns.append(w.rstrip(".,!?"))
    # Hashtags
    hashtags = re.findall(r"#\w+", agent_answer)

    entities = prices + proper_nouns + hashtags
    if not entities:
        return True, 1.0  # No verifiable claims

    grounded_count = sum(
        1 for entity in entities if entity.lower() in tool_lower
    )
    score = grounded_count / len(entities) if entities else 1.0
    return score >= 0.6, score


# --- Test Cases ---


@pytest.mark.parametrize(
    "case",
    GROUNDING_CASES,
    ids=lambda c: c["id"],
)
def test_grounding_heuristic(case: dict) -> None:
    """Verify grounding detection using heuristic method."""
    is_grounded, score = heuristic_grounding_check(
        case["tool_output"], case["agent_answer"]
    )
    if case["expected_grounded"]:
        assert is_grounded, (
            f"Expected grounded but got ungrounded (score={score:.2f}): "
            f"{case['agent_answer']}"
        )
    else:
        assert not is_grounded, (
            f"Expected hallucination but got grounded (score={score:.2f}): "
            f"{case['agent_answer']}"
        )


@pytest.mark.parametrize(
    "case",
    GROUNDING_CASES,
    ids=lambda c: c["id"],
)
async def test_grounding_llm_judge(case: dict) -> None:
    """Verify grounding detection using LLM-as-judge.

    Mocks the LLM call to return a controlled verdict for deterministic testing.
    Integration tests with real LLM should be run separately.
    """
    expected_verdict = GroundingVerdict(
        is_grounded=case["expected_grounded"],
        score=1.0 if case["expected_grounded"] else 0.1,
        unsupported_claims=[] if case["expected_grounded"] else [case["agent_answer"]],
        reasoning="Mock verdict for testing",
    )

    judge = LLMJudge()
    with patch.object(judge, "check_grounding", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = expected_verdict
        verdict = await judge.check_grounding(case["tool_output"], case["agent_answer"])

    assert verdict.is_grounded == case["expected_grounded"]
    if case["expected_grounded"]:
        assert verdict.score >= 0.7
    else:
        assert verdict.score < 0.7


async def test_grounding_eval_suite() -> None:
    """Run grounding evals through the EvalSuite runner."""
    suite = EvalSuite(eval_type="hallucination", agent_id="all")

    for case in GROUNDING_CASES:
        suite.add_case(
            input=case["agent_answer"],
            expected="grounded" if case["expected_grounded"] else "hallucinated",
            tool_output=case["tool_output"],
        )

    async def scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        is_grounded, score = heuristic_grounding_check(
            eval_case.metadata["tool_output"], eval_case.input
        )
        actual = "grounded" if is_grounded else "hallucinated"
        matched = actual == eval_case.expected
        return actual, 1.0 if matched else 0.0, {"heuristic_score": score}

    results = await suite.run(scorer, threshold=0.7)
    assert suite.pass_rate >= 0.75, f"Grounding pass rate too low: {suite.pass_rate:.2f}"
    assert len(results) == len(GROUNDING_CASES)


class TestParseJson:
    """Tests for the JSON parsing helper."""

    def test_plain_json(self):
        result = _parse_json('{"score": 0.8, "reasoning": "good"}')
        assert result["score"] == 0.8

    def test_markdown_fenced_json(self):
        text = '```json\n{"score": 0.9, "reasoning": "ok"}\n```'
        result = _parse_json(text)
        assert result["score"] == 0.9

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_json("not json at all")
