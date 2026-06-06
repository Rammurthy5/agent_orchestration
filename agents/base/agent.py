"""Abstract base agent implementing the ReAct loop."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

from langsmith import traceable

from agents.base.llm import LLMClient, LLMResponse, Message, ToolSpec
from agents.base.types import (
    AgentID,
    AgentRequest,
    AgentResponse,
    OutOfScopeError,
    ReflectionResult,
    Step,
    ToolCall,
)


class BaseAgent(ABC):
    """Abstract base class for all specialized agents.

    Subclasses must implement the ReAct methods:
    reasoning, tool_selection, execute, reflect, final_answer.
    """

    agent_id: AgentID
    max_iterations: int = 10

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def _load_system_prompt(self) -> str:
        """Load the system prompt from this agent's prompts/ directory."""
        agent_dir = Path(__file__).parent.parent / self.agent_id.value / "prompts" / "system.md"
        return agent_dir.read_text()

    def _build_tool_specs(self) -> list[ToolSpec]:
        """Return available tools as LLM ToolSpec objects. Override in subclasses."""
        return []

    def _build_messages(
        self, request: AgentRequest, steps: list[Step], extra: str | None = None
    ) -> list[Message]:
        """Build conversation messages from request and ReAct history."""
        messages = [Message(role="system", content=self._load_system_prompt())]
        messages.append(Message(role="user", content=request.query))

        for step in steps:
            messages.append(Message(role="assistant", content=f"Thought: {step.thought}"))
            if step.action and step.observation:
                # Use assistant role for observation replay to avoid invalid tool message shape.
                messages.append(
                    Message(
                        role="assistant",
                        content=f"Observation from {step.action}: {step.observation}",
                    )
                )

        if extra:
            messages.append(Message(role="user", content=extra))

        return messages

    @traceable(name="agent.run")
    async def run(self, request: AgentRequest) -> AgentResponse:
        """Execute the full ReAct loop for a request."""
        self.validate_query(request)
        start = time.perf_counter()
        steps: list[Step] = []
        tool_calls: list[ToolCall] = []

        for _ in range(self.max_iterations):
            thought = await self.reasoning(request, steps)

            tool_call = await self.tool_selection(thought, request, steps)
            if tool_call is None:
                break

            observation = await self.execute(tool_call)
            tool_call.result = observation
            tool_calls.append(tool_call)

            step = Step(
                thought=thought,
                action=tool_call.tool_name,
                observation=observation,
                tool_call=tool_call,
            )
            steps.append(step)

            reflection = await self.reflect(steps, request)
            if not reflection.should_continue:
                break

        answer = await self.final_answer(steps, request)
        latency_ms = int((time.perf_counter() - start) * 1000)

        return AgentResponse(
            agent_id=self.agent_id,
            answer=answer,
            steps=steps,
            tool_calls=tool_calls,
            latency_ms=latency_ms,
        )

    @abstractmethod
    @traceable(name="agent.reasoning")
    async def reasoning(
        self, request: AgentRequest, steps: list[Step]
    ) -> str:
        """Generate a thought based on the current state."""
        ...

    def validate_query(self, request: AgentRequest) -> None:
        """Validate that the query is within this agent's domain.

        Subclasses must override `_domain_keywords` to define their scope.
        Raises OutOfScopeError if the query has no overlap with the domain.
        """
        keywords = self._domain_keywords()
        if not keywords:
            return
        query_lower = request.query.lower()
        if not any(kw in query_lower for kw in keywords):
            raise OutOfScopeError(self.agent_id.value, request.query)

    def _domain_keywords(self) -> list[str]:
        """Return keywords that define this agent's domain. Override in subclasses."""
        return []

    @abstractmethod
    @traceable(name="agent.tool_selection")
    async def tool_selection(
        self, thought: str, request: AgentRequest, steps: list[Step]
    ) -> ToolCall | None:
        """Select a tool to invoke, or None to finalize."""
        ...

    @abstractmethod
    @traceable(name="agent.execute")
    async def execute(self, tool_call: ToolCall) -> str:
        """Execute the selected tool and return the observation."""
        ...

    @abstractmethod
    @traceable(name="agent.reflect")
    async def reflect(
        self, steps: list[Step], request: AgentRequest
    ) -> ReflectionResult:
        """Reflect on progress and decide whether to continue."""
        ...

    @abstractmethod
    @traceable(name="agent.final_answer")
    async def final_answer(
        self, steps: list[Step], request: AgentRequest
    ) -> str:
        """Synthesize the final answer from collected steps."""
        ...
