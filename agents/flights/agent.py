"""Flights agent — searches flights, compares routes, optimizes cost/time."""

from __future__ import annotations

import json
import time

from langsmith import traceable

from adapters.travel_hacking import TravelHackingAdapter
from agents.base import (
    AgentID,
    AgentRequest,
    BaseAgent,
    ReflectionResult,
    Step,
    ToolCall,
)
from agents.base.llm import LLMClient, ToolSpec
from agents.flights.tools import AVAILABLE_TOOLS
from tools.flights import FlightSearchParams


class FlightsAgent(BaseAgent):
    """Specialized agent for flight search and route optimization."""

    agent_id = AgentID.FLIGHTS

    def __init__(self, llm: LLMClient | None = None, adapter: TravelHackingAdapter | None = None):
        super().__init__(llm=llm)
        self.adapter = adapter or TravelHackingAdapter()

    def _domain_keywords(self) -> list[str]:
        return [
            "flight", "fly", "airline", "airport", "boarding",
            "departure", "arrival", "layover", "connecting",
            "plane", "aviation", "itinerary", "airfare",
        ]

    def _build_tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=t["name"], description=t["description"], parameters=t["parameters"])
            for t in AVAILABLE_TOOLS
        ]

    @traceable(name="flights.reasoning")
    async def reasoning(self, request: AgentRequest, steps: list[Step]) -> str:
        messages = self._build_messages(request, steps)
        response = await self.llm.complete(messages)
        return response.content

    @traceable(name="flights.tool_selection")
    async def tool_selection(
        self, thought: str, request: AgentRequest, steps: list[Step]
    ) -> ToolCall | None:
        messages = self._build_messages(
            request, steps, extra=f"Based on this thought: {thought}\nSelect a tool or respond."
        )
        response = await self.llm.complete(messages, tools=self._build_tool_specs())

        if response.tool_call is None:
            return None

        return ToolCall(
            tool_name=response.tool_call.name,
            parameters=response.tool_call.arguments,
        )

    @traceable(name="flights.execute")
    async def execute(self, tool_call: ToolCall) -> str:
        start = time.perf_counter()
        try:
            if tool_call.tool_name == "search_flights":
                params = FlightSearchParams(**tool_call.parameters)
                results = await self.adapter.search_flights(params)
                observation = json.dumps([r.model_dump() for r in results], default=str)
            elif tool_call.tool_name == "compare_routes":
                routes = tool_call.parameters.get("routes", [])
                result = await self.adapter.compare_routes(routes)
                observation = result.model_dump_json()
            else:
                observation = f"Unknown tool: {tool_call.tool_name}"
        except Exception as e:
            observation = f"Tool error: {e}"
        finally:
            tool_call.latency_ms = int((time.perf_counter() - start) * 1000)

        return observation

    @traceable(name="flights.reflect")
    async def reflect(self, steps: list[Step], request: AgentRequest) -> ReflectionResult:
        if not steps:
            return ReflectionResult(should_continue=True, reason="No steps yet")

        messages = self._build_messages(
            request,
            steps,
            extra="Do you have enough information to answer? Reply YES or NO with a reason.",
        )
        response = await self.llm.complete(messages)
        should_continue = "NO" not in response.content.upper()[:10]
        return ReflectionResult(should_continue=should_continue, reason=response.content)

    @traceable(name="flights.final_answer")
    async def final_answer(self, steps: list[Step], request: AgentRequest) -> str:
        messages = self._build_messages(
            request,
            steps,
            extra="Synthesize a final answer for the user based on the tool results above.",
        )
        response = await self.llm.complete(messages)
        return response.content

