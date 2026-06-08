"""Regression tests for flight booking link propagation."""

from __future__ import annotations

from agents.base.llm import LLMResponse, LLMToolCall, Message, ToolSpec
from agents.base.types import AgentRequest
from agents.flights import FlightsAgent
from tools.flights import FlightResult


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def complete(self, messages: list[Message], tools: list[ToolSpec] | None = None, temperature: float = 0.0) -> LLMResponse:
        self.calls += 1
        if tools is not None:
            return LLMResponse(
                content="",
                tool_call=LLMToolCall(
                    name="search_flights",
                    arguments={"origin": "JFK", "destination": "LAX", "departure_date": "2026-07-10"},
                ),
            )
        prompt = messages[-1].content if messages else ""
        if "Do you have enough information" in prompt:
            return LLMResponse(content="NO - I still need the tool output.")
        if "Synthesize a final answer" in prompt:
            return LLMResponse(content="Booking link included.")
        return LLMResponse(content="Use search_flights.")


class FakeTravelAdapter:
    async def search_flights(self, params):
        return [
            FlightResult(
                airline="SkyAir",
                origin=params.origin,
                destination=params.destination,
                departure_time="2026-07-10T08:00:00Z",
                arrival_time="2026-07-10T11:00:00Z",
                duration_minutes=360,
                price_usd=199.0,
                stops=0,
                booking_url="https://www.google.com/travel/flights?q=JFK%20LAX",
            )
        ]

    async def compare_routes(self, route_ids):
        raise NotImplementedError


class FailingTravelAdapter(FakeTravelAdapter):
    async def search_flights(self, params):
        raise RuntimeError("boom")


async def test_flights_agent_passes_booking_links_into_final_answer() -> None:
    agent = FlightsAgent(llm=FakeLLM(), adapter=FakeTravelAdapter())
    response = await agent.run(
        AgentRequest(query="Find flights from JFK to LAX", session_id="flight-booking-1")
    )

    assert response.tool_calls
    assert "booking_url" in response.steps[0].observation
    assert "Booking link" in response.answer


async def test_flights_agent_appends_search_link_on_tool_error() -> None:
    agent = FlightsAgent(llm=FakeLLM(), adapter=FailingTravelAdapter())
    response = await agent.run(
        AgentRequest(query="Find flights from JFK to LAX", session_id="flight-booking-2")
    )

    assert response.tool_calls
    assert "Live flight search was unavailable" in response.answer
    assert "Search link:" in response.answer
