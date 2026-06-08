"""Stay agent — hotel recommendations, availability, budget optimization."""

from __future__ import annotations

import json
import time
from urllib.parse import quote_plus

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
from agents.stay.tools import AVAILABLE_TOOLS
from tools.stay import HotelSearchParams


class StayAgent(BaseAgent):
    """Specialized agent for hotel search and accommodation booking."""

    agent_id = AgentID.STAY

    def __init__(self, llm: LLMClient | None = None, adapter: TravelHackingAdapter | None = None):
        super().__init__(llm=llm)
        self.adapter = adapter or TravelHackingAdapter(profile="stay")

    def _domain_keywords(self) -> list[str]:
        return [
            "hotel", "stay", "accommodation", "room", "booking",
            "hostel", "resort", "airbnb", "check-in", "check-out",
            "lodging", "motel", "suite", "reservation", "night",
        ]

    def _build_tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=t["name"], description=t["description"], parameters=t["parameters"])
            for t in AVAILABLE_TOOLS
        ]

    @traceable(name="stay.reasoning")
    async def reasoning(self, request: AgentRequest, steps: list[Step]) -> str:
        messages = self._build_messages(request, steps)
        response = await self.llm.complete(messages)
        return response.content

    @traceable(name="stay.tool_selection")
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

    @traceable(name="stay.execute")
    async def execute(self, tool_call: ToolCall) -> str:
        start = time.perf_counter()
        try:
            if tool_call.tool_name == "search_hotels":
                params = HotelSearchParams(**tool_call.parameters)
                results = await self.adapter.search_hotels(params)
                observation = json.dumps([r.model_dump() for r in results], default=str)
            elif tool_call.tool_name == "check_availability":
                hotel_id = tool_call.parameters.get("hotel_id", "")
                check_in = tool_call.parameters.get("check_in", "")
                check_out = tool_call.parameters.get("check_out", "")
                result = await self.adapter.check_availability(hotel_id, check_in, check_out)
                observation = result.model_dump_json()
            else:
                observation = f"Unknown tool: {tool_call.tool_name}"
        except Exception as e:
            if tool_call.tool_name == "search_hotels":
                params = HotelSearchParams(**tool_call.parameters)
                observation = json.dumps(
                    {
                        "error": str(e),
                        "search_url": self._build_hotel_search_url(params),
                    }
                )
            else:
                observation = f"Tool error: {e}"
        finally:
            tool_call.latency_ms = int((time.perf_counter() - start) * 1000)

        return observation

    @traceable(name="stay.reflect")
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

    @traceable(name="stay.final_answer")
    async def final_answer(self, steps: list[Step], request: AgentRequest) -> str:
        messages = self._build_messages(
            request,
            steps,
            extra="Synthesize a final answer for the user based on the tool results above.",
        )
        response = await self.llm.complete(messages)
        return self._append_fallback_search_link(response.content, steps)

    def _build_hotel_search_url(self, params: HotelSearchParams) -> str:
        query = (
            f"hotels in {params.location} "
            f"{params.check_in} to {params.check_out} "
            f"{params.guests} guests"
        )
        if params.max_price_per_night is not None:
            query += f" under {params.max_price_per_night} per night"
        return "https://www.google.com/search?q=" + quote_plus(query)

    def _append_fallback_search_link(self, answer: str, steps: list[Step]) -> str:
        if not steps or not steps[-1].observation:
            return answer

        try:
            payload = json.loads(steps[-1].observation)
        except Exception:
            return answer

        if not isinstance(payload, dict):
            return answer

        search_url = payload.get("search_url")
        if not search_url or search_url in answer:
            return answer

        fallback_note = "Live hotel search was unavailable, so here is a direct search link instead."
        if answer.strip():
            return f"{answer}\n\n{fallback_note}\nSearch link: {search_url}"
        return f"{fallback_note}\nSearch link: {search_url}"
