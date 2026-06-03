"""Travel Hacking Toolkit MCP adapter — used by Flights and Stay agents."""

from adapters.base import BaseMCPAdapter
from tools.flights import FlightResult, FlightSearchParams, RouteComparison
from tools.stay import AvailabilityResult, HotelResult, HotelSearchParams


class TravelHackingAdapter(BaseMCPAdapter):
    """MCP adapter for the travel-hacking-toolkit server.

    Provides flight search, route comparison, hotel search, and availability checking.
    """

    base_url = "http://localhost:8100/mcp"

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        super().__init__(base_url=base_url, auth_token=auth_token)

    async def search_flights(self, params: FlightSearchParams) -> list[FlightResult]:
        """Search for flights matching the given parameters."""
        result = await self.call("search_flights", params, FlightSearchResult)
        return result.flights

    async def compare_routes(self, route_ids: list[str]) -> RouteComparison:
        """Compare multiple routes by cost and duration."""
        from pydantic import BaseModel

        class CompareParams(BaseModel):
            routes: list[str]

        return await self.call("compare_routes", CompareParams(routes=route_ids), RouteComparison)

    async def search_hotels(self, params: HotelSearchParams) -> list[HotelResult]:
        """Search for hotels matching the given parameters."""
        result = await self.call("search_hotels", params, HotelSearchResult)
        return result.hotels

    async def check_availability(
        self, hotel_id: str, check_in: str, check_out: str
    ) -> AvailabilityResult:
        """Check real-time availability for a specific hotel."""
        from pydantic import BaseModel

        class AvailParams(BaseModel):
            hotel_id: str
            check_in: str
            check_out: str

        return await self.call(
            "check_availability",
            AvailParams(hotel_id=hotel_id, check_in=check_in, check_out=check_out),
            AvailabilityResult,
        )


# Wrapper models for list responses from MCP
from pydantic import BaseModel


class FlightSearchResult(BaseModel):
    flights: list[FlightResult]


class HotelSearchResult(BaseModel):
    hotels: list[HotelResult]

