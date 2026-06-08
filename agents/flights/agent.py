"""Flights agent — searches flights, compares routes, optimizes cost/time."""

from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta
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
from agents.flights.tools import AVAILABLE_TOOLS
from tools.flights import FlightSearchParams


class FlightsAgent(BaseAgent):
    """Specialized agent for flight search and route optimization."""

    agent_id = AgentID.FLIGHTS

    def __init__(self, llm: LLMClient | None = None, adapter: TravelHackingAdapter | None = None):
        super().__init__(llm=llm)
        self.adapter = adapter or TravelHackingAdapter(profile="flights")

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
            fallback = self._build_flight_search_call(request.query)
            if fallback is not None:
                return fallback
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
                observation = json.dumps(
                    [
                        {
                            **r.model_dump(),
                            "booking_url": r.booking_url,
                        }
                        for r in results
                    ],
                    default=str,
                )
            elif tool_call.tool_name == "compare_routes":
                routes = tool_call.parameters.get("routes", [])
                result = await self.adapter.compare_routes(routes)
                observation = result.model_dump_json()
            else:
                observation = f"Unknown tool: {tool_call.tool_name}"
        except Exception as e:
            if tool_call.tool_name == "search_flights":
                params = FlightSearchParams(**tool_call.parameters)
                observation = json.dumps(
                    {
                        "error": str(e),
                        "search_url": self._build_flight_search_url(params),
                    }
                )
            else:
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
            extra=(
                "Synthesize a final answer for the user based on the tool results above. "
                "If any flight result includes a booking_url, include it explicitly as a clickable booking link."
            ),
        )
        response = await self.llm.complete(messages)
        return self._append_fallback_search_link(response.content, steps)

    def _build_flight_search_call(self, query: str) -> ToolCall | None:
        lowered = query.lower()
        if "flight" not in lowered and "airfare" not in lowered and "airline" not in lowered:
            return None

        match = re.search(
            r"from\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:\s+for\s+(?P<when>.+))?$",
            query,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None

        origin = match.group("origin").strip().rstrip(".,")
        destination = match.group("destination").strip().rstrip(".,")
        when = (match.group("when") or "").strip().rstrip(".,")
        departure_date = self._resolve_departure_date(when) if when else ""
        if not departure_date:
            return None

        return ToolCall(
            tool_name="search_flights",
            parameters={
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
            },
        )

    def _resolve_departure_date(self, when: str) -> str:
        lowered = when.lower()
        today = date.today()
        weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }

        if lowered in {"today", "tonight"}:
            return today.isoformat()
        if lowered == "tomorrow":
            return (today + timedelta(days=1)).isoformat()
        if lowered in {"this friday", "coming friday", "next friday"}:
            return self._next_weekday(today, weekday_map["friday"], include_today=False)

        for name, weekday in weekday_map.items():
            if name in lowered:
                return self._next_weekday(today, weekday, include_today=False)

        return ""

    def _next_weekday(self, start: date, target_weekday: int, *, include_today: bool) -> str:
        days_ahead = (target_weekday - start.weekday()) % 7
        if days_ahead == 0 and not include_today:
            days_ahead = 7
        return (start + timedelta(days=days_ahead)).isoformat()

    def _build_flight_search_url(self, params: FlightSearchParams) -> str:
        return "https://www.google.com/travel/flights?q=" + quote_plus(
            f"Flights from {params.origin} to {params.destination} on {params.departure_date}"
        )

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

        fallback_note = "Live flight search was unavailable, so here is a direct search link instead."
        if answer.strip():
            return f"{answer}\n\n{fallback_note}\nSearch link: {search_url}"
        return f"{fallback_note}\nSearch link: {search_url}"
