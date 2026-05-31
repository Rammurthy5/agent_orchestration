"""Flights agent — searches flights, compares routes, optimizes cost/time."""

from agents.base import (
    AgentID,
    AgentRequest,
    BaseAgent,
    ReflectionResult,
    Step,
    ToolCall,
)


class FlightsAgent(BaseAgent):
    """Specialized agent for flight search and route optimization."""

    agent_id = AgentID.FLIGHTS

    def _domain_keywords(self) -> list[str]:
        return [
            "flight", "fly", "airline", "airport", "boarding",
            "departure", "arrival", "layover", "connecting",
            "plane", "aviation", "itinerary", "airfare",
        ]

    async def reasoning(self, request: AgentRequest, steps: list[Step]) -> str:
        # TODO: Integrate LLM reasoning with flight-specific system prompt
        raise NotImplementedError

    async def tool_selection(
        self, thought: str, request: AgentRequest, steps: list[Step]
    ) -> ToolCall | None:
        # TODO: Select from available flight tools based on thought
        raise NotImplementedError

    async def execute(self, tool_call: ToolCall) -> str:
        # TODO: Dispatch to tools/flights.py via adapter
        raise NotImplementedError

    async def reflect(self, steps: list[Step], request: AgentRequest) -> ReflectionResult:
        # TODO: Evaluate if enough information gathered
        raise NotImplementedError

    async def final_answer(self, steps: list[Step], request: AgentRequest) -> str:
        # TODO: Synthesize flight recommendations
        raise NotImplementedError
