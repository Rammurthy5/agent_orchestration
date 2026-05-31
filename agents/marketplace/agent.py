"""Marketplace agent — product search, price comparison, recommendations."""

from agents.base import (
    AgentID,
    AgentRequest,
    BaseAgent,
    ReflectionResult,
    Step,
    ToolCall,
)


class MarketplaceAgent(BaseAgent):
    """Specialized agent for product search and price comparison."""

    agent_id = AgentID.MARKETPLACE

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
