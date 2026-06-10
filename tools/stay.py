"""Stay/hotel tool implementations.

These functions are invoked by the Stay agent via the MCP adapter.
"""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class HotelSearchParams(BaseModel):
    """Parameters for hotel search."""

    location: str
    check_in: str
    check_out: str
    guests: int = 1
    max_price_per_night: float | None = None


class HotelResult(BaseModel):
    """A single hotel search result."""

    model_config = ConfigDict(populate_by_name=True)

    hotel_id: str
    name: str
    location: str
    price_per_night_usd: float
    rating: float | None = None
    amenities: list[str] = []
    booking_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("booking_url", "url", "bookingLink", "booking_link", "link"),
    )


class AvailabilityResult(BaseModel):
    """Availability check for a specific hotel."""

    hotel_id: str
    available: bool
    rooms_left: int | None = None
    price_per_night_usd: float | None = None


async def search_hotels(params: HotelSearchParams) -> list[HotelResult]:
    """Search hotels via MCP adapter. Must be called through adapters/travel_hacking.py."""
    raise NotImplementedError("Must be called through TravelHackingAdapter")


async def check_availability(hotel_id: str, check_in: str, check_out: str) -> AvailabilityResult:
    """Check availability via MCP adapter. Must be called through adapters/travel_hacking.py."""
    raise NotImplementedError("Must be called through TravelHackingAdapter")
