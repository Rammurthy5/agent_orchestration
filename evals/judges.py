"""LLM-as-judge scoring module for evaluation pipelines.

Provides reusable judge functions that use an LLM to evaluate agent outputs
against criteria like grounding, relevance, and correctness.
"""

from __future__ import annotations

import json
from typing import Any

from langsmith import traceable
from pydantic import BaseModel, Field

from agents.base.llm import LLMClient, Message


class JudgeScore(BaseModel):
    """Result from an LLM judge evaluation."""

    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    criteria: str
    passed: bool = False


class GroundingVerdict(BaseModel):
    """Result of hallucination/grounding check."""

    is_grounded: bool
    score: float = Field(ge=0.0, le=1.0)
    unsupported_claims: list[str] = Field(default_factory=list)
    reasoning: str


class ToolSelectionVerdict(BaseModel):
    """Result of tool selection correctness check."""

    correct_tool: bool
    correct_params: bool
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str


class TrajectoryVerdict(BaseModel):
    """Result of trajectory quality evaluation."""

    reasoning_quality: float = Field(ge=0.0, le=1.0)
    action_relevance: float = Field(ge=0.0, le=1.0)
    observation_usage: float = Field(ge=0.0, le=1.0)
    overall_score: float = Field(ge=0.0, le=1.0)
    reasoning: str


_GROUNDING_PROMPT = """You are an evaluation judge. Determine if the agent's answer is grounded in the provided tool output.

TOOL OUTPUT (source of truth):
{tool_output}

AGENT ANSWER:
{agent_answer}

Evaluate whether EVERY claim in the agent's answer is directly supported by the tool output.

Respond in JSON format:
{{
  "is_grounded": true/false,
  "score": 0.0-1.0 (1.0 = fully grounded, 0.0 = completely fabricated),
  "unsupported_claims": ["list of claims not in tool output"],
  "reasoning": "brief explanation"
}}"""

_TOOL_SELECTION_PROMPT = """You are an evaluation judge. Determine if the agent selected the correct tool with correct parameters.

USER QUERY: {query}
EXPECTED TOOL: {expected_tool}
EXPECTED PARAMS: {expected_params}
ACTUAL TOOL: {actual_tool}
ACTUAL PARAMS: {actual_params}

Evaluate:
1. Was the correct tool selected?
2. Were the parameters reasonable for the query?

Respond in JSON format:
{{
  "correct_tool": true/false,
  "correct_params": true/false,
  "score": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

_TRAJECTORY_PROMPT = """You are an evaluation judge. Evaluate the quality of this agent's ReAct reasoning trajectory.

USER QUERY: {query}

TRAJECTORY:
{trajectory}

Evaluate on these dimensions:
1. reasoning_quality: Are the thoughts logical and well-structured? (0-1)
2. action_relevance: Are the actions appropriate for the query? (0-1)
3. observation_usage: Does the agent incorporate observations into subsequent reasoning? (0-1)

Respond in JSON format:
{{
  "reasoning_quality": 0.0-1.0,
  "action_relevance": 0.0-1.0,
  "observation_usage": 0.0-1.0,
  "overall_score": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

_RELEVANCE_PROMPT = """You are an evaluation judge. Score the relevance and helpfulness of the agent's answer.

USER QUERY: {query}
AGENT ANSWER: {answer}

Score from 0.0 to 1.0 where:
- 1.0 = perfectly relevant, complete, and helpful
- 0.5 = partially relevant but incomplete
- 0.0 = completely irrelevant

Respond in JSON format:
{{
  "score": 0.0-1.0,
  "reasoning": "brief explanation",
  "criteria": "relevance",
  "passed": true/false (true if score >= 0.7)
}}"""


class LLMJudge:
    """LLM-based judge for evaluating agent outputs.

    Uses a separate LLM call to evaluate quality, grounding, and correctness.
    Can use a different model from the agent (e.g., gpt-4o for judging).
    """

    def __init__(self, llm: LLMClient | None = None):
        self._llm = llm or LLMClient()

    async def close(self) -> None:
        await self._llm.close()

    @traceable(name="judge.grounding")
    async def check_grounding(
        self, tool_output: str, agent_answer: str
    ) -> GroundingVerdict:
        """Check if agent answer is grounded in tool output (hallucination detection)."""
        prompt = _GROUNDING_PROMPT.format(
            tool_output=tool_output, agent_answer=agent_answer
        )
        response = await self._llm.complete(
            messages=[Message(role="user", content=prompt)], temperature=0.0
        )
        return GroundingVerdict(**_parse_json(response.content))

    @traceable(name="judge.tool_selection")
    async def check_tool_selection(
        self,
        query: str,
        expected_tool: str,
        expected_params: dict[str, Any],
        actual_tool: str,
        actual_params: dict[str, Any],
    ) -> ToolSelectionVerdict:
        """Evaluate if the agent selected the correct tool with correct parameters."""
        prompt = _TOOL_SELECTION_PROMPT.format(
            query=query,
            expected_tool=expected_tool,
            expected_params=json.dumps(expected_params),
            actual_tool=actual_tool,
            actual_params=json.dumps(actual_params),
        )
        response = await self._llm.complete(
            messages=[Message(role="user", content=prompt)], temperature=0.0
        )
        return ToolSelectionVerdict(**_parse_json(response.content))

    @traceable(name="judge.trajectory")
    async def evaluate_trajectory(
        self, query: str, steps: list[dict[str, str]]
    ) -> TrajectoryVerdict:
        """Evaluate the quality of a ReAct reasoning trajectory."""
        trajectory_text = "\n".join(
            f"Step {i+1}:\n  Thought: {s.get('thought', 'N/A')}\n  Action: {s.get('action', 'N/A')}\n  Observation: {s.get('observation', 'N/A')}"
            for i, s in enumerate(steps)
        )
        prompt = _TRAJECTORY_PROMPT.format(query=query, trajectory=trajectory_text)
        response = await self._llm.complete(
            messages=[Message(role="user", content=prompt)], temperature=0.0
        )
        return TrajectoryVerdict(**_parse_json(response.content))

    @traceable(name="judge.relevance")
    async def score_relevance(self, query: str, answer: str) -> JudgeScore:
        """Score the relevance and helpfulness of an agent answer."""
        prompt = _RELEVANCE_PROMPT.format(query=query, answer=answer)
        response = await self._llm.complete(
            messages=[Message(role="user", content=prompt)], temperature=0.0
        )
        return JudgeScore(**_parse_json(response.content))


def _parse_json(text: str) -> dict[str, Any]:
    """Parse JSON from LLM response, handling markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown fences
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        text = text.strip()
    return json.loads(text)
