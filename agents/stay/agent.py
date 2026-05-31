"""Stay agent — hotel recommendations, availability, budget optimization."""

from agents.base import (
    AgentID,
    AgentRequest,
    BaseAgent,
    ReflectionResult,
    Step,
    ToolCall,
)


class StayAgent(BaseAgent):
    """Specialized agent for hotel search and accommodation booking."""

    agent_id = AgentID.STAY

    async def reasoning(self, request: AgentRequest, steps: list[Step]) -> str:
        raise NotImplementedError

    async def tool_selection(
        self, thought: str, request: AgentRequest, steps: list[Step]
    ) -> ToolCall | None:
        raise NotImplementedError

    async def execute(self, tool_call: ToolCall) -> str:
        raise NotImplementedError

    async def reflect(self, steps: list[Step], request: AgentRequest) -> ReflectionResult:
        raise NotImplementedError

    async def final_answer(self, steps: list[Step], request: AgentRequest) -> str:
        raise NotImplementedError
