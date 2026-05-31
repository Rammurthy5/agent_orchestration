"""Abstract base agent implementing the ReAct loop."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from langsmith import traceable

from agents.base.types import (
    AgentID,
    AgentRequest,
    AgentResponse,
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

    @traceable(name="agent.run")
    async def run(self, request: AgentRequest) -> AgentResponse:
        """Execute the full ReAct loop for a request."""
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
