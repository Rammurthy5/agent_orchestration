"""Tests for deterministic flight query parsing."""

from __future__ import annotations

from agents.flights import FlightsAgent


def test_build_flight_search_call_parses_relative_friday() -> None:
    agent = FlightsAgent()
    call = agent._build_flight_search_call("one-way flights from London to TRV for coming friday")

    assert call is not None
    assert call.tool_name == "search_flights"
    assert call.parameters["origin"] == "London"
    assert call.parameters["destination"] == "TRV"
    assert call.parameters["departure_date"]


def test_build_flight_search_call_ignores_non_flight_queries() -> None:
    agent = FlightsAgent()
    assert agent._build_flight_search_call("Find me a nice hotel in Paris") is None
