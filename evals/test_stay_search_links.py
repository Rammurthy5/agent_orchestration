"""Regression tests for hotel search link fallback propagation."""

from __future__ import annotations

from agents.base.llm import LLMResponse, LLMToolCall, Message, ToolSpec
from agents.base.types import AgentRequest
from agents.stay import StayAgent
from tools.stay import HotelResult


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def complete(self, messages: list[Message], tools: list[ToolSpec] | None = None, temperature: float = 0.0) -> LLMResponse:
        self.calls += 1
        if tools is not None:
            return LLMResponse(
                content="",
                tool_call=LLMToolCall(
                    name="search_hotels",
                    arguments={
                        "location": "Munich",
                        "check_in": "2026-06-12",
                        "check_out": "2026-06-13",
                        "guests": 2,
                        "max_price_per_night": 300,
                    },
                ),
            )
        prompt = messages[-1].content if messages else ""
        if "Do you have enough information" in prompt:
            return LLMResponse(content="NO - I still need the tool output.")
        if "Synthesize a final answer" in prompt:
            return LLMResponse(content="I found a few options.")
        return LLMResponse(content="Use search_hotels.")


class FakeTravelAdapter:
    async def search_hotels(self, params):
        return [
            HotelResult(
                hotel_id="h1",
                name="Munich Central Hotel",
                location="Munich",
                price_per_night_usd=180.0,
                rating=4.4,
                amenities=["wifi", "breakfast"],
                booking_url="https://example.com/munich-central-hotel",
            )
        ]

    async def check_availability(self, hotel_id, check_in, check_out):
        raise NotImplementedError


async def test_stay_agent_passes_search_link_into_final_answer() -> None:
    agent = StayAgent(llm=FakeLLM(), adapter=FakeTravelAdapter())
    response = await agent.run(
        AgentRequest(query="Find me a place to stay in Munich", session_id="stay-link-1")
    )

    assert response.tool_calls
    assert "search_url" not in response.steps[0].observation
    assert "booking_url" in response.steps[0].observation
    assert "Booking link" in response.answer


async def test_stay_agent_appends_search_link_on_tool_error() -> None:
    class FailingTravelAdapter(FakeTravelAdapter):
        async def search_hotels(self, params):
            raise RuntimeError("boom")

    agent = StayAgent(llm=FakeLLM(), adapter=FailingTravelAdapter())
    response = await agent.run(
        AgentRequest(query="Find me a place to stay in Munich", session_id="stay-link-2")
    )

    assert response.tool_calls
    assert "Live hotel search was unavailable" in response.answer
    assert "boom" in response.answer
    assert "Search link:" in response.answer
