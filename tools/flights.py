"""Flight search tool implementations.

These functions are invoked by the Flights agent via the MCP adapter.
They must remain pure — no direct external API calls.
"""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class FlightSearchParams(BaseModel):
    """Parameters for searching flights."""

    origin: str
    destination: str
    departure_date: str
    return_date: str | None = None


class FlightResult(BaseModel):
    """A single flight search result."""

    model_config = ConfigDict(populate_by_name=True)

    airline: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    price_usd: float
    stops: int
    booking_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("booking_url", "url", "bookingLink", "booking_link"),
    )


class RouteComparison(BaseModel):
    """Comparison of multiple routes."""

    routes: list[FlightResult]
    cheapest: FlightResult | None = None
    fastest: FlightResult | None = None


async def search_flights(params: FlightSearchParams) -> list[FlightResult]:
    """Search flights via MCP adapter. Must be called through adapters/travel_hacking.py."""
    raise NotImplementedError("Must be called through TravelHackingAdapter")


async def compare_routes(route_ids: list[str]) -> RouteComparison:
    """Compare multiple routes. Must be called through adapters/travel_hacking.py."""
    raise NotImplementedError("Must be called through TravelHackingAdapter")
